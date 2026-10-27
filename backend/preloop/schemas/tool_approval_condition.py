"""Pydantic schemas for tool approval conditions."""

import uuid
from typing import Optional, Dict, Any
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ToolApprovalConditionBase(BaseModel):
    """Base schema for tool approval condition."""

    name: Optional[str] = Field(None, description="Optional human-readable name")
    description: Optional[str] = Field(None, description="Optional description")
    is_enabled: bool = Field(True, description="Whether the condition is enabled")
    condition_type: str = Field(
        "argument",
        description="Type of condition evaluator: 'argument', 'state', 'risk'",
    )
    condition_expression: Optional[str] = Field(
        None, description="CEL expression for conditional approval"
    )
    condition_config: Optional[Dict[str, Any]] = Field(
        None, description="Additional configuration"
    )


class ToolApprovalConditionCreate(ToolApprovalConditionBase):
    """Schema for creating a tool approval condition."""

    tool_configuration_id: uuid.UUID = Field(..., description="Tool configuration ID")


class ToolApprovalConditionUpdate(BaseModel):
    """Schema for updating a tool approval condition."""

    name: Optional[str] = None
    description: Optional[str] = None
    is_enabled: Optional[bool] = None
    condition_type: Optional[str] = None
    condition_expression: Optional[str] = None
    condition_config: Optional[Dict[str, Any]] = None


class ToolApprovalConditionResponse(ToolApprovalConditionBase):
    """Schema for tool approval condition response."""

    id: uuid.UUID
    account_id: uuid.UUID
    tool_configuration_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConditionTestRequest(BaseModel):
    """Schema for testing a condition expression."""

    expression: str = Field(..., description="CEL expression to test")
    sample_args: Dict[str, Any] = Field(
        ..., description="Sample tool arguments for testing"
    )


class ConditionTestResponse(BaseModel):
    """Schema for condition test result."""

    matches: bool = Field(..., description="Whether the condition matched")
    error: Optional[str] = Field(None, description="Error message if evaluation failed")
    evaluation_context: Dict[str, Any] = Field(
        ..., description="Context used for evaluation"
    )
