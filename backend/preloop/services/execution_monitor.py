"""Background service to monitor and clean up stale flow executions."""

import asyncio
import logging
import os
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from uuid import UUID
from datetime import datetime, timedelta, timezone

from preloop.agents import create_agent_executor, AgentStatus
from preloop.models.db.session import get_db_session as get_db
from preloop.models.crud import crud_flow, crud_flow_execution

logger = logging.getLogger(__name__)


@dataclass
class ExecutionSnapshot:
    """Plain values crossing the database-worker/event-loop boundary."""

    id: UUID
    flow_id: UUID
    status: str
    start_time: datetime
    agent_session_reference: str | None
    error_message: str | None
    end_time: datetime | None


@dataclass(frozen=True)
class FlowSnapshot:
    agent_type: str
    agent_config: dict[str, Any]


class ExecutionMonitor:
    """
    Background service that monitors active flow executions.

    Periodically checks for stale executions (e.g., RUNNING/PENDING for too long)
    and verifies if their containers are still alive. If not, updates status to FAILED.
    """

    def __init__(
        self,
        check_interval_seconds: int = 60,
        stale_threshold_minutes: int = 60,
    ):
        """
        Initialize execution monitor.

        Args:
            check_interval_seconds: How often to check for stale executions
            stale_threshold_minutes: How long an execution can be in RUNNING/PENDING
                                    before being considered potentially stale
        """
        self.check_interval = check_interval_seconds
        self.stale_threshold = timedelta(minutes=stale_threshold_minutes)
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self):
        """Start the monitoring background task."""
        if self._running:
            logger.warning("Execution monitor is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(
            f"Execution monitor started (check_interval={self.check_interval}s, "
            f"stale_threshold={self.stale_threshold.total_seconds() / 60}m)"
        )

    async def stop(self):
        """Stop the monitoring background task."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Execution monitor stopped")

    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_stale_executions()
            except Exception as e:
                logger.error(f"Error in execution monitor loop: {e}", exc_info=True)

            # Wait before next check
            try:
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break

    def _load_candidates(self) -> list[tuple[ExecutionSnapshot, FlowSnapshot | None]]:
        """Own and close the entire read transaction in one worker thread."""
        sessions = get_db()
        db = next(sessions)
        try:
            executions = crud_flow_execution.get_by_statuses(
                db, statuses=["RUNNING", "PENDING", "INITIALIZING", "STARTING"]
            )
            candidates = []
            now = datetime.now(timezone.utc)
            for execution in executions:
                if (
                    now - execution.start_time.replace(tzinfo=timezone.utc)
                    < self.stale_threshold
                ):
                    continue
                snapshot = ExecutionSnapshot(
                    id=execution.id,
                    flow_id=execution.flow_id,
                    status=execution.status,
                    start_time=execution.start_time,
                    agent_session_reference=execution.agent_session_reference,
                    error_message=execution.error_message,
                    end_time=execution.end_time,
                )
                flow = (
                    crud_flow.get(db, id=execution.flow_id)
                    if execution.agent_session_reference
                    else None
                )
                flow_snapshot = (
                    FlowSnapshot(flow.agent_type, deepcopy(flow.agent_config or {}))
                    if flow
                    else None
                )
                candidates.append((snapshot, flow_snapshot))
            return candidates
        finally:
            db.close()
            if hasattr(sessions, "close"):
                sessions.close()

    def _persist_result(
        self, execution: ExecutionSnapshot, expected_status: str
    ) -> None:
        """Recheck the observed status/reference atomically before writing."""
        sessions = get_db()
        db = next(sessions)
        try:
            crud_flow_execution.update_monitor_result(
                db,
                execution_id=execution.id,
                flow_id=execution.flow_id,
                expected_status=expected_status,
                expected_reference=execution.agent_session_reference,
                status=execution.status,
                error_message=execution.error_message,
                end_time=execution.end_time,
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
            if hasattr(sessions, "close"):
                sessions.close()

    async def _check_stale_executions(self):
        """Read snapshots, await agent I/O, then persist guarded updates."""
        try:
            candidates = await asyncio.to_thread(self._load_candidates)
            for execution, flow in candidates:
                expected_status = execution.status
                await self._check_execution(flow, execution)
                if execution.status != expected_status:
                    await asyncio.to_thread(
                        self._persist_result, execution, expected_status
                    )
        except Exception as e:
            logger.error(f"Error checking stale executions: {e}", exc_info=True)

    async def _check_execution(
        self, flow: FlowSnapshot | None, execution: ExecutionSnapshot
    ):
        """Inspect agent state on the owning event loop without a DB session."""
        try:
            # Calculate how long the execution has been in current state
            now = datetime.now(timezone.utc)
            elapsed = now - execution.start_time.replace(tzinfo=timezone.utc)

            # Only check executions that have been running for a while
            if elapsed < self.stale_threshold:
                return

            # If no session reference, mark as failed (container never started)
            if not execution.agent_session_reference:
                logger.warning(
                    f"Execution {execution.id} has no session reference after "
                    f"{elapsed.total_seconds() / 60:.1f} minutes, marking as FAILED"
                )
                execution.status = "FAILED"
                execution.error_message = (
                    "Execution failed to start agent container within timeout"
                )
                execution.end_time = now
                return

            if not flow:
                logger.error(
                    f"Flow {execution.flow_id} not found for execution {execution.id}"
                )
                return

            # Create agent executor to check status
            try:
                agent_executor = create_agent_executor(
                    flow.agent_type, {"agent_config": flow.agent_config or {}}
                )
            except Exception as e:
                logger.error(
                    f"Failed to create agent executor for checking execution "
                    f"{execution.id}: {e}"
                )
                return

            # Check if container is still running
            try:
                status = await agent_executor.get_status(
                    execution.agent_session_reference
                )

                # Update execution status based on container status
                if status == AgentStatus.FAILED:
                    logger.warning(
                        f"Execution {execution.id} container failed, updating status"
                    )
                    execution.status = "FAILED"
                    execution.error_message = (
                        "Agent container failed or stopped unexpectedly"
                    )
                    execution.end_time = now

                elif status == AgentStatus.SUCCEEDED:
                    logger.info(
                        f"Execution {execution.id} container succeeded, updating status"
                    )
                    execution.status = "SUCCEEDED"
                    execution.end_time = now

                elif status == AgentStatus.STOPPED:
                    # Only update if not already in a terminal state
                    # Preserve STOPPED status if the user stopped the execution
                    if execution.status not in ("STOPPED", "FAILED", "SUCCEEDED"):
                        logger.info(
                            f"Execution {execution.id} container stopped, "
                            f"updating status to STOPPED"
                        )
                        execution.status = "STOPPED"
                        execution.error_message = "Execution was stopped"
                        execution.end_time = now
                    else:
                        logger.debug(
                            f"Execution {execution.id} already in terminal state "
                            f"({execution.status}), not updating"
                        )

                elif status in (AgentStatus.RUNNING, AgentStatus.STARTING):
                    # Container is still running, no action needed
                    logger.debug(
                        f"Execution {execution.id} container is still {status}"
                    )

            except Exception as e:
                # If we can't get status, container might be gone
                logger.warning(
                    f"Failed to get status for execution {execution.id} "
                    f"(session {execution.agent_session_reference}): {e}. "
                    f"Marking as FAILED."
                )
                execution.status = "FAILED"
                execution.error_message = (
                    f"Lost connection to agent container: {str(e)}"
                )
                execution.end_time = now

            finally:
                # Cleanup agent executor
                if hasattr(agent_executor, "cleanup"):
                    await agent_executor.cleanup()

        except Exception as e:
            logger.error(f"Error checking execution {execution.id}: {e}", exc_info=True)


# Global instance
_monitor_instance: ExecutionMonitor | None = None


def get_execution_monitor() -> ExecutionMonitor:
    """Get or create the global execution monitor instance."""
    global _monitor_instance
    if _monitor_instance is None:
        check_interval = int(os.getenv("EXECUTION_MONITOR_INTERVAL", "60"))
        stale_threshold = int(os.getenv("EXECUTION_STALE_THRESHOLD_MINUTES", "60"))
        _monitor_instance = ExecutionMonitor(
            check_interval_seconds=check_interval,
            stale_threshold_minutes=stale_threshold,
        )
    return _monitor_instance
