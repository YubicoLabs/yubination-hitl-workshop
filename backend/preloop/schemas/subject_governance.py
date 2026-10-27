"""Schemas for subject-scoped governance configuration."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class SubjectGovernanceConfig(BaseModel):
    allowed_models: List[str] = Field(default_factory=list)
    model_budgets: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    tool_rules: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)
    tool_enabled_overrides: Dict[str, bool] = Field(default_factory=dict)


class SubjectGovernanceResponse(BaseModel):
    subject_type: str
    subject_id: str
    config: SubjectGovernanceConfig
