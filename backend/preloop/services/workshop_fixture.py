"""Bounded internal capability used only after the existing governed MCP wrapper."""

from uuid import UUID
from typing import Any
from preloop.models.models.mcp_server import MCPServer
from sqlalchemy.orm import Session
from preloop.models.crud import workshop_customer

VERSION = "yubination-v2"
URL = "http://workshop.internal/bounded"
TOOLS = {
    "get_customer_status": ("Workshop Customer Read", {"email": {"type": "string"}}),
    "set_customer_status": (
        "Workshop Customer Change",
        {
            "email": {"type": "string"},
            "expected_status": {"type": "string", "enum": ["standard", "vip"]},
            "status": {"type": "string", "enum": ["standard", "vip"]},
        },
    ),
}


def schema(tool: str) -> dict[str, Any]:
    properties = TOOLS[tool][1]
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def is_source(source: MCPServer) -> bool:
    config = getattr(source, "auth_config", None)
    marker = config.get("workshop_onboarding") if isinstance(config, dict) else None
    return isinstance(marker, dict) and marker.get("version") == VERSION


def execute(
    db: Session,
    *,
    source: MCPServer,
    account_id: str,
    tool: str,
    arguments: dict[str, Any],
    completion_request_id: UUID | None = None,
    source_id: str | None = None,
) -> dict[str, str]:
    """Authenticate scope from wrapper context/source, never from tool arguments."""
    from fastmcp.exceptions import ToolError

    marker = source.auth_config["workshop_onboarding"]
    if (
        str(source.account_id) != account_id
        or source.url != URL
        or source.auth_type != "none"
        or source.status != "active"
        or marker.get("tool") != tool
        or tool not in TOOLS
    ):
        raise ToolError("Workshop source is not ready for this account.")
    if set(arguments) != set(TOOLS[tool][1]):
        raise ToolError("Unexpected workshop operation arguments.")
    fixture = workshop_customer.get(db, account_id=UUID(account_id))
    if fixture is None or arguments["email"] != fixture["email"]:
        raise ToolError("Workshop customer is unavailable for this account.")
    if tool == "get_customer_status":
        return fixture
    if arguments["expected_status"] == arguments["status"] or (
        arguments["expected_status"],
        arguments["status"],
    ) not in {("standard", "vip"), ("vip", "standard")}:
        raise ToolError(
            "Only explicit standard to vip or vip to standard workshop transitions are supported."
        )
    if completion_request_id is not None:
        attempt = approved_attempt(
            db, account_id=UUID(account_id), request_id=completion_request_id
        )
        if (
            attempt is None
            or attempt[0].status != "approved"
            or attempt[0].tool_args != arguments
            or str(attempt[1]) != source_id
        ):
            raise ToolError("Workshop approval does not match this exact execution.")
    try:
        return workshop_customer.transition(
            db,
            account_id=UUID(account_id),
            email=fixture["email"],
            expected_status=arguments["expected_status"],
            status=arguments["status"],
            completion_request_id=completion_request_id,
        )
    except ValueError as error:
        raise ToolError(str(error)) from error


def approved_attempt(db: Session, *, account_id: UUID, request_id: UUID) -> Any:
    """Return only the exact bounded operation with a currently managed source."""
    from preloop.models.crud import (
        crud_approval_request,
        crud_tool_configuration,
        crud_mcp_server,
    )

    req = crud_approval_request.get(db, id=str(request_id), account_id=account_id)
    if req is None or req.account_id != account_id or req.id != request_id:
        return None
    args = req.tool_args
    if (
        req.tool_name != "set_customer_status"
        or not isinstance(args, dict)
        or set(args) != {"email", "expected_status", "status"}
        or args.get("email") != workshop_customer.fixture_email(account_id)
        or not isinstance(args.get("expected_status"), str)
        or not isinstance(args.get("status"), str)
        or (args["expected_status"], args["status"])
        not in {("standard", "vip"), ("vip", "standard")}
    ):
        return None
    config = crud_tool_configuration.get(
        db, id=req.tool_configuration_id, account_id=account_id
    )
    if (
        config is None
        or config.account_id != account_id
        or config.tool_source != "mcp"
        or config.tool_name != req.tool_name
        or not config.mcp_server_id
    ):
        return None
    source = crud_mcp_server.get(
        db, id=str(config.mcp_server_id), account_id=str(account_id)
    )
    if (
        source is None
        or not is_source(source)
        or str(source.account_id) != str(account_id)
        or source.url != URL
        or source.auth_type != "none"
        or source.status != "active"
        or source.auth_config["workshop_onboarding"].get("tool") != req.tool_name
    ):
        return None
    return req, config.mcp_server_id


def is_managed_request(db: Session, *, account_id: UUID, request: Any) -> bool:
    """Identify historical workshop ownership without trusting operation arguments."""
    from preloop.models.crud import crud_tool_configuration, crud_mcp_server

    config = crud_tool_configuration.get(
        db, id=request.tool_configuration_id, account_id=account_id
    )
    if config is None or str(config.account_id) != str(account_id):
        return False
    if config.tool_source != "mcp" or not config.mcp_server_id:
        return False
    source = crud_mcp_server.get(
        db, id=str(config.mcp_server_id), account_id=str(account_id)
    )
    return (
        source is not None
        and str(source.account_id) == str(account_id)
        and is_source(source)
    )
