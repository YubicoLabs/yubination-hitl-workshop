"""
Base classes for tracker update services.
"""

import abc
import datetime

from sqlalchemy.orm import Session

from preloop.models.models import Tracker

from ..config import logger
from ..scanner.core import TrackerClient


class BaseTrackerUpdateService(abc.ABC):
    """
    Abstract base class for tracker update services.

    This class provides the framework for continuously updating
    trackers in the database.
    """

    def __init__(self, db: Session, tracker: Tracker):
        """
        Initialize the tracker update service.

        Args:
            db: Database session
            tracker: Tracker model
        """
        self.db = db
        self.tracker = tracker
        self.client = TrackerClient(tracker)
        self.running = False
        self.last_check = datetime.datetime.now(datetime.timezone.utc)

    @abc.abstractmethod
    def setup(self) -> bool:
        """
        Set up the update service.

        Returns:
            True if setup was successful, False otherwise
        """
        pass

    @abc.abstractmethod
    def update(self) -> int:
        """
        Process updates for the tracker.

        Returns:
            Number of issues updated
        """
        pass

    @abc.abstractmethod
    def cleanup(self) -> None:
        """Clean up resources when service is stopped."""
        pass

    def start(self) -> None:
        """Start the update service."""
        self.running = True

    def stop(self) -> None:
        """Stop the update service."""
        self.running = False
        self.cleanup()


class PollingTrackerUpdateService(BaseTrackerUpdateService):
    """
    Base class for tracker update services that use polling.
    The actual polling is now handled by an external scheduler (e.g., APScheduler).
    This class primarily defines the structure and the `update` method to be scheduled.
    """

    def __init__(self, db: Session, tracker: Tracker, poll_interval: int = 90):
        """
        Initialize the polling tracker update service.

        Args:
            db: Database session
            tracker: Tracker model
            poll_interval: Poll interval in seconds (default: 90).
                           Note: This interval is now informational; the actual scheduling
                           interval is managed by the external scheduler.
        """
        super().__init__(db, tracker)
        self.poll_interval = poll_interval
        # Removed self.thread initialization

    # Removed poll_loop method

    def start(self) -> None:
        """Start the polling service (sets running flag)."""
        # The actual scheduling and execution is handled externally.
        super().start()
        logger.info(
            f"Polling service for tracker {self.tracker.id} marked as started (scheduling handled externally)."
        )

    def stop(self) -> None:
        """Stop the polling service (sets running flag and cleans up)."""
        # The actual stopping of scheduled jobs is handled externally.
        super().stop()
        logger.info(f"Polling service for tracker {self.tracker.id} marked as stopped.")
