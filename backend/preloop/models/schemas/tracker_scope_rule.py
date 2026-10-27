"""Pydantic schemas for TrackerScopeRule."""

from pydantic import BaseModel, ConfigDict
from ..models.tracker_scope_rule import ScopeType, RuleType


class TrackerScopeRuleBase(BaseModel):
    scope_type: ScopeType
    rule_type: RuleType
    identifier: str


class TrackerScopeRuleCreate(TrackerScopeRuleBase):
    pass


class TrackerScopeRule(TrackerScopeRuleBase):
    id: str
    tracker_id: str

    model_config = ConfigDict(from_attributes=True)
