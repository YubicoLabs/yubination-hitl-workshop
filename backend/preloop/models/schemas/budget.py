import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from preloop.models.models.budget import BudgetPeriod


class BudgetPolicyBase(BaseModel):
    account_id: uuid.UUID
    subject_type: str = Field(..., description="E.g. account, flows, api_key")
    subject_id: Optional[uuid.UUID] = None
    model_alias: Optional[str] = None
    period: BudgetPeriod
    hard_limit_usd: Optional[float] = None
    soft_limit_usd: Optional[float] = None
    notify_on_hard: bool = True
    notify_on_soft: bool = True


class BudgetPolicyCreate(BudgetPolicyBase):
    pass


class BudgetPolicyUpdate(BaseModel):
    hard_limit_usd: Optional[float] = None
    soft_limit_usd: Optional[float] = None
    notify_on_hard: Optional[bool] = None
    notify_on_soft: Optional[bool] = None


class BudgetPolicyInDBBase(BudgetPolicyBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BudgetPolicy(BudgetPolicyInDBBase):
    pass
