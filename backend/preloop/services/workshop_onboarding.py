"""Opt-in, account-scoped provisioning of the two workshop capabilities.

Schemas are pinned contracts, not an unrestricted upstream discovery catalog.
Sources remain inactive until their policy is complete. Retries validate existing
objects and never overwrite participant-authored policy or customer data.
"""

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import logging
import os
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from preloop.models import crud
from preloop.models.db.session import get_session_factory
from preloop.models.schemas.tool_configuration import (
    ToolConfigurationCreate,
)
from preloop.services import workshop_fixture
from preloop.services.mcp_client_pool import MCPClient

logger = logging.getLogger(__name__)
MARKER = "workshop_onboarding"
VERSION = "yubination-v1"
WORKFLOW_NAME = "Workshop hardware approval"
TOOLS = {
    "execute_sql": ("Workshop Database", "WORKSHOP_DATABASE_MCP_URL", "sql"),
    "get_customer_status": (
        "Workshop Customer Read",
        "WORKSHOP_CUSTOMER_READ_MCP_URL",
        "email",
    ),
}


def managed_tool_name(server) -> str | None:
    """Return a durable managed-source allowlist; names alone confer no ownership."""
    metadata = server.auth_config or {}
    if not isinstance(metadata, dict) or MARKER not in metadata:
        return None
    marker = metadata[MARKER]
    if isinstance(marker, dict) and marker.get("version") == workshop_fixture.VERSION:
        tool = marker.get("tool")
        if (
            tool not in workshop_fixture.TOOLS
            or server.auth_type != "none"
            or server.url != workshop_fixture.URL
        ):
            raise ValueError("Invalid bounded workshop source configuration")
        return tool
    if not isinstance(marker, dict) or marker.get("version") != VERSION:
        raise ValueError("Unrecognized workshop source marker")
    tool = marker.get("tool")
    if tool not in TOOLS or server.auth_type != "none":
        raise ValueError("Invalid workshop source configuration")
    return tool


def _matches(obj, expected: dict) -> bool:
    for field, value in expected.items():
        actual = getattr(obj, field, None)
        if isinstance(value, UUID) or field == "mcp_server_id":
            if str(actual) != str(value):
                return False
        elif field == "approver_user_ids":
            if [str(item) for item in (actual or [])] != [str(item) for item in value]:
                return False
        elif actual != value:
            return False
    return True


def _previous_bounded_schema(tool: str) -> dict[str, object] | None:
    if tool != "set_customer_status":
        return None
    return {
        "type": "object",
        "properties": {
            "email": {"type": "string"},
            "expected_status": {"type": "string", "enum": ["standard"]},
            "status": {"type": "string", "enum": ["vip"]},
        },
        "required": ["email", "expected_status", "status"],
        "additionalProperties": False,
    }


def _is_reconcilable_bounded_schema(schema: object, tool: str) -> bool:
    """Allow only the exact managed schema or the exact previous managed schema."""
    previous = _previous_bounded_schema(tool)
    return schema == workshop_fixture.schema(tool) or (
        previous is not None and schema == previous
    )


@contextmanager
def _account_lock(db: Session, account_id: UUID) -> Iterator[Session]:
    """Use one connection for session lock and CRUD, surviving CRUD commits."""
    key = int.from_bytes(
        hashlib.sha256(f"workshop:{account_id}".encode()).digest()[:8],
        "big",
        signed=True,
    )
    engine = db.get_bind()
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Workshop provisioning requires PostgreSQL account locks")
    with engine.connect() as connection:
        acquired = False
        try:
            connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": key})
            acquired = True
            connection.commit()
            with Session(bind=connection) as locked_db:
                yield locked_db
        finally:
            if acquired:
                try:
                    connection.execute(
                        text("SELECT pg_advisory_unlock(:key)"), {"key": key}
                    )
                    connection.commit()
                except Exception:
                    # Never return a potentially locked session to the pool.
                    connection.invalidate()
                    raise


async def _probe_upstreams(urls: dict) -> None:
    for tool, url in urls.items():
        client = MCPClient(url=url, auth_type="none", transport="http-streaming")
        try:
            async with asyncio.timeout(20):
                await client.connect()
                catalog = await client.list_tools()
                matches = [item for item in catalog if item.name == tool]
                if len(matches) != 1:
                    raise ValueError(
                        f"Workshop upstream must expose exactly one {tool}"
                    )
                schema = matches[0].inputSchema
                parameter = TOOLS[tool][2]
                if (
                    schema.get("type") != "object"
                    or schema.get("properties", {}).get(parameter, {}).get("type")
                    != "string"
                    or parameter not in schema.get("required", [])
                    or set(schema.get("required", [])) != {parameter}
                ):
                    raise ValueError(
                        f"Workshop upstream {tool} has an incompatible schema"
                    )
        finally:
            await client.close()


def provision_workshop_account(
    db, account_id: UUID, user_id: UUID, urls: dict, *, bounded: bool = False
) -> None:
    """Serialize retries across processes for one account, without resetting data."""
    with _account_lock(db, account_id) as locked_db:
        _provision_workshop_account(
            locked_db, account_id, user_id, urls, bounded=bounded
        )


def _provision_workshop_account(
    db, account_id: UUID, user_id: UUID, urls: dict, *, bounded: bool = False
) -> None:
    """Provision or resume sequential retries; conflicting custom objects fail closed."""
    account = str(account_id)
    user = crud.crud_user.get(db, id=user_id, account_id=account)
    if user is None or not user.is_active:
        raise ValueError("Workshop approver must be an active user in this account")
    definitions = (
        {
            tool: (definition[0], "", "email")
            for tool, definition in workshop_fixture.TOOLS.items()
        }
        if bounded
        else TOOLS
    )
    version = workshop_fixture.VERSION if bounded else VERSION
    if bounded:
        # Existing v1 sources require an explicit operator migration, never overwrite.
        existing = crud.crud_mcp_server.get_multi_by_account(db, account_id=account)
        if any(
            isinstance(source.auth_config, dict)
            and isinstance(source.auth_config.get(MARKER), dict)
            and source.auth_config[MARKER].get("version") == VERSION
            for source in existing
        ):
            raise ValueError(
                "Legacy workshop account requires explicit migration review"
            )
        from preloop.models.crud import workshop_customer

        workshop_customer.provision(db, account_id=account_id)
    sources = []
    try:
        for tool, (name, _, _) in definitions.items():
            source = crud.crud_mcp_server.get_by_name(db, account_id=account, name=name)
            if source:
                if managed_tool_name(source) != tool or source.url != urls[tool]:
                    raise ValueError(f"Existing {name} conflicts with workshop setup")
            else:
                source = crud.crud_mcp_server.create(
                    db,
                    obj_in={
                        "account_id": account_id,
                        "name": name,
                        "url": urls[tool],
                        "auth_type": "none",
                        "transport": "http-streaming",
                        "auth_config": {MARKER: {"version": version, "tool": tool}},
                        "status": "pending",
                    },
                )
            sources.append((tool, source))
            crud.crud_mcp_server.update(db, db_obj=source, obj_in={"status": "pending"})

        workflow_values = {
            "approval_type": "manual",
            "workflow_type": "simple",
            "async_approval_enabled": False,
            "approval_mode": "standard",
            "approvals_required": 1,
            "approver_user_ids": [user_id],
            "timeout_seconds": 900,
            "step_up_protocol": "webauthn_discoverable",
        }
        workflow = crud.crud_approval_workflow.get_by_name(
            db, account_id=account, name=WORKFLOW_NAME
        )
        if workflow is None:
            workflow = crud.crud_approval_workflow.create(
                db,
                account_id=account,
                obj_in={"name": WORKFLOW_NAME, **workflow_values},
            )
        elif not _matches(workflow, workflow_values):
            raise ValueError(
                "Existing workshop workflow differs; manual review required"
            )

        for tool, source in sources:
            parameter = definitions[tool][2]
            schema = {
                "type": "object",
                "properties": {parameter: {"type": "string"}},
                "required": [parameter],
                "additionalProperties": False,
            }
            if bounded:
                schema = workshop_fixture.schema(tool)
            write = tool in {"execute_sql", "set_customer_status"}
            config_values = {
                "mcp_server_id": str(source.id),
                "is_enabled": True,
                "approval_workflow_id": workflow.id if write else None,
                "justification_mode": "required" if write else None,
                "tool_schema": schema,
            }
            config = crud.crud_tool_configuration.get_by_tool_name_and_source(
                db, account_id=account, tool_name=tool, tool_source="mcp"
            )
            if config is None:
                config = crud.crud_tool_configuration.create(
                    db,
                    config_in=ToolConfigurationCreate(
                        account_id=account,
                        tool_name=tool,
                        tool_source="mcp",
                        **config_values,
                    ),
                )
            elif not _matches(config, config_values):
                raise ValueError(
                    f"Existing {tool} configuration differs; manual review required"
                )
            rule_values = {
                "action": "require_approval" if write else "allow",
                "condition_type": "cel",
                "condition_expression": "true",
                "priority": 0,
                "is_enabled": True,
                "approval_workflow_id": workflow.id if write else None,
            }
            rules = crud.crud_tool_access_rule.get_multi_by_config(
                db, config_id=str(config.id), account_id=account
            )
            if not rules:
                crud.crud_tool_access_rule.create(
                    db,
                    obj_in={
                        "account_id": account_id,
                        "tool_configuration_id": config.id,
                        **rule_values,
                    },
                )
            elif len(rules) != 1 or not _matches(rules[0], rule_values):
                raise ValueError(
                    f"Existing {tool} policy differs; manual review required"
                )
            cached = crud.crud_mcp_tool.get_by_server_and_name(
                db, server_id=source.id, name=tool
            )
            if cached is None:
                crud.crud_mcp_tool.create(
                    db,
                    obj_in={
                        "mcp_server_id": source.id,
                        "name": tool,
                        "description": "Workshop governed database action"
                        if write
                        else "Read one workshop customer's status",
                        "input_schema": schema,
                        "discovered_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            elif cached.input_schema != schema:
                raise ValueError(
                    f"Existing {tool} schema differs; manual review required"
                )
        if not bounded:
            asyncio.run(_probe_upstreams(urls))
        for _, source in sources:
            crud.crud_mcp_server.update(
                db,
                db_obj=source,
                obj_in={
                    "status": "active",
                    "last_error": None,
                },
            )
    except Exception:
        db.rollback()
        for _, source in sources:
            crud.crud_mcp_server.update(
                db,
                db_obj=source,
                obj_in={
                    "status": "error",
                    "last_error": "Workshop setup incomplete. Administrator must review setup logs and retry.",
                },
            )
        logger.exception("Workshop setup failed for account %s", account)
        raise


def workshop_upstream_urls() -> dict:
    """One validation contract shared by provisioning and readiness reporting."""
    urls = {}
    for tool, (_, env_name, _) in TOOLS.items():
        value = os.getenv(env_name, "")
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            raise ValueError(
                f"{env_name} must be an explicit upstream HTTP(S) URL without credentials"
            )
        urls[tool] = value
    return urls


def setup_workshop_account(account_id: UUID, user_id: UUID) -> None:
    """Deployment switch defaults off; provision only the bounded account fixture."""
    if os.getenv("WORKSHOP_ONBOARDING_ENABLED", "").lower() != "true":
        return
    urls = {tool: workshop_fixture.URL for tool in workshop_fixture.TOOLS}
    with get_session_factory()() as db:
        provision_workshop_account(db, account_id, user_id, urls, bounded=True)


def reconcile_bounded_workshop_account(
    db: Session, account_id: UUID, user_id: UUID
) -> None:
    """Reconcile exact existing v2 schemas without provisioning or history changes."""
    with _account_lock(db, account_id) as locked_db:
        _reconcile_bounded_workshop_account(locked_db, account_id, user_id)


def _reconcile_bounded_workshop_account(
    db: Session, account_id: UUID, user_id: UUID
) -> None:
    account = str(account_id)
    user = crud.crud_user.get(db, id=user_id, account_id=account)
    if user is None or not user.is_active:
        raise ValueError("Workshop approver must be an active user in this account")

    sources = crud.crud_mcp_server.get_multi_by_account(db, account_id=account)
    managed_sources: dict[str, Any] = {}
    for source in sources:
        metadata = source.auth_config or {}
        marker = metadata.get(MARKER) if isinstance(metadata, dict) else None
        if not isinstance(marker, dict):
            continue
        if marker.get("version") != workshop_fixture.VERSION:
            raise ValueError(
                "Legacy or unrecognized workshop sources cannot be reconciled"
            )
        tool = marker.get("tool")
        if tool not in workshop_fixture.TOOLS or tool in managed_sources:
            raise ValueError("Existing bounded workshop sources differ")
        expected_name = workshop_fixture.TOOLS[tool][0]
        expected_source = {
            "account_id": account_id,
            "name": expected_name,
            "url": workshop_fixture.URL,
            "auth_type": "none",
            "transport": "http-streaming",
            "auth_config": {
                MARKER: {"version": workshop_fixture.VERSION, "tool": tool}
            },
            "status": "active",
            "last_error": None,
        }
        if not _matches(source, expected_source):
            raise ValueError(f"Existing {tool} source differs")
        managed_sources[tool] = source
    if set(managed_sources) != set(workshop_fixture.TOOLS):
        raise ValueError("Existing bounded workshop source is missing")

    workflow_values = {
        "approval_type": "manual",
        "workflow_type": "simple",
        "async_approval_enabled": False,
        "approval_mode": "standard",
        "approvals_required": 1,
        "approver_user_ids": [user_id],
        "timeout_seconds": 900,
        "step_up_protocol": "webauthn_discoverable",
    }
    workflow = crud.crud_approval_workflow.get_by_name(
        db, account_id=account, name=WORKFLOW_NAME
    )
    if workflow is None or not _matches(workflow, workflow_values):
        raise ValueError("Existing workshop workflow differs")

    configuration_updates: list[tuple[Any, dict[str, Any]]] = []
    cache_updates: list[tuple[Any, dict[str, Any]]] = []
    for tool, source in managed_sources.items():
        write = tool == "set_customer_status"
        current_schema = workshop_fixture.schema(tool)
        config = crud.crud_tool_configuration.get_by_tool_name_and_source(
            db, account_id=account, tool_name=tool, tool_source="mcp"
        )
        config_values = {
            "mcp_server_id": str(source.id),
            "is_enabled": True,
            "approval_workflow_id": workflow.id if write else None,
            "justification_mode": "required" if write else None,
        }
        if (
            config is None
            or not _matches(config, config_values)
            or not _is_reconcilable_bounded_schema(config.tool_schema, tool)
        ):
            raise ValueError(f"Existing {tool} configuration differs")
        rule_values = {
            "action": "require_approval" if write else "allow",
            "condition_type": "cel",
            "condition_expression": "true",
            "priority": 0,
            "is_enabled": True,
            "approval_workflow_id": workflow.id if write else None,
        }
        rules = crud.crud_tool_access_rule.get_multi_by_config(
            db, config_id=str(config.id), account_id=account
        )
        if len(rules) != 1 or not _matches(rules[0], rule_values):
            raise ValueError(f"Existing {tool} policy differs")
        cached = crud.crud_mcp_tool.get_by_server_and_name(
            db, server_id=source.id, name=tool
        )
        if cached is None:
            raise ValueError(f"Existing {tool} cache is missing")
        if not _is_reconcilable_bounded_schema(cached.input_schema, tool):
            raise ValueError(f"Existing {tool} cache differs")
        if config.tool_schema != current_schema:
            configuration_updates.append((config, current_schema))
        if cached.input_schema != current_schema:
            cache_updates.append((cached, current_schema))

    from preloop.models.crud import workshop_customer

    workshop_customer.reconcile_bounded_schemas(
        db,
        configuration_updates=configuration_updates,
        cache_updates=cache_updates,
    )
