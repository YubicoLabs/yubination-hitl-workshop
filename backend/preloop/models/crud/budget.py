"""CRUD operations for Budget models."""

from typing import Optional, Sequence
from datetime import datetime, timedelta
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from .base import CRUDBase
from ..models.budget import BudgetPolicy, BudgetSpendActivity, BudgetPeriod


class CRUDBudgetPolicy(CRUDBase[BudgetPolicy]):
    """CRUD operations for BudgetPolicy model."""

    def get_policies_for_subject(
        self,
        db: Session,
        account_id: uuid.UUID,
        subject_type: str,
        subject_id: Optional[uuid.UUID] = None,
    ) -> Sequence[BudgetPolicy]:
        """Get all budget policies configured for a specific subject."""
        query = select(self.model).where(
            self.model.account_id == account_id,
            self.model.subject_type == subject_type,
            self.model.subject_id == subject_id,
        )
        return db.execute(query).scalars().all()

    def remove(
        self, db: Session, *, id: uuid.UUID, account_id: str
    ) -> Optional[BudgetPolicy]:
        """Delete a budget policy strictly enforcing account ownership."""
        obj = (
            db.query(self.model)
            .filter(self.model.id == id, self.model.account_id == account_id)
            .first()
        )
        if obj:
            db.delete(obj)
            db.commit()
        return obj


class CRUDBudgetSpendActivity(CRUDBase[BudgetSpendActivity]):
    """CRUD operations for BudgetSpendActivity model."""

    def upsert_spend(
        self,
        db: Session,
        account_id: uuid.UUID,
        subject_type: str,
        subject_id: Optional[uuid.UUID],
        model_alias: Optional[str],
        period: BudgetPeriod,
        period_start: Optional[datetime],
        spend_increment_usd: float,
    ) -> BudgetSpendActivity:
        """Atomically upsert the spend activity logic using ON CONFLICT DO UPDATE.
        Returns the updated record.
        """
        stmt = insert(BudgetSpendActivity).values(
            id=uuid.uuid4(),
            account_id=account_id,
            subject_type=subject_type,
            subject_id=subject_id,
            model_alias=model_alias,
            period=period,
            period_start=period_start,
            spend_usd=spend_increment_usd,
        )

        # On conflict (matching the unique constraint on subject + model + period + period_start),
        # increment the spend_usd column dynamically.
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                "account_id",
                "subject_type",
                "subject_id",
                "model_alias",
                "period",
                "period_start",
            ],
            set_={"spend_usd": BudgetSpendActivity.spend_usd + stmt.excluded.spend_usd},
        ).returning(BudgetSpendActivity)

        result = db.execute(stmt).scalar_one()
        db.commit()
        return result

    def get_spend(
        self,
        db: Session,
        account_id: uuid.UUID,
        subject_type: str,
        subject_id: Optional[uuid.UUID],
        model_alias: Optional[str],
        period: BudgetPeriod,
        period_start: Optional[datetime],
    ) -> float:
        """Get the current spend for a specific bucket. Returns 0.0 if no spend recorded yet."""
        query = select(self.model.spend_usd).where(
            self.model.account_id == account_id,
            self.model.subject_type == subject_type,
            self.model.subject_id == subject_id,
            self.model.model_alias == model_alias,
            self.model.period == period,
            self.model.period_start == period_start,
        )
        result = db.execute(query).scalar_one_or_none()
        return result if result is not None else 0.0

    def get_spend_multi(
        self,
        db: Session,
        account_id: uuid.UUID,
        buckets: Sequence[
            tuple[
                str,
                Optional[uuid.UUID],
                Optional[str],
                BudgetPeriod,
                Optional[datetime],
            ]
        ],
    ) -> dict[
        tuple[
            str, Optional[uuid.UUID], Optional[str], BudgetPeriod, Optional[datetime]
        ],
        float,
    ]:
        """Fetch multiple spend buckets at once."""
        from sqlalchemy import or_, and_

        if not buckets:
            return {}

        conditions = []
        for s_type, s_id, m_alias, period, p_start in buckets:
            conds = [
                self.model.subject_type == s_type,
                self.model.period == period,
            ]
            if s_id is not None:
                conds.append(self.model.subject_id == s_id)
            else:
                conds.append(self.model.subject_id.is_(None))

            if m_alias is not None:
                conds.append(self.model.model_alias == m_alias)
            else:
                conds.append(self.model.model_alias.is_(None))

            if p_start is not None:
                conds.append(self.model.period_start == p_start)
            else:
                conds.append(self.model.period_start.is_(None))

            conditions.append(and_(*conds))

        query = select(
            self.model.subject_type,
            self.model.subject_id,
            self.model.model_alias,
            self.model.period,
            self.model.period_start,
            self.model.spend_usd,
        ).where(self.model.account_id == account_id, or_(*conditions))

        rows = db.execute(query).all()
        result = {}
        for r in rows:
            result[
                (r.subject_type, r.subject_id, r.model_alias, r.period, r.period_start)
            ] = float(r.spend_usd or 0.0)

        return result


crud_budget_policy = CRUDBudgetPolicy(BudgetPolicy)
crud_budget_spend = CRUDBudgetSpendActivity(BudgetSpendActivity)


def get_period_start(ts: datetime, period: BudgetPeriod) -> Optional[datetime]:
    """Get the truncated start datetime for a given period."""
    if period == BudgetPeriod.hourly:
        return ts.replace(minute=0, second=0, microsecond=0)
    elif period == BudgetPeriod.daily:
        return ts.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == BudgetPeriod.weekly:
        # Monday is 0, Sunday is 6. Subtracting weekday() gets us back to Monday.
        dt = ts - timedelta(days=ts.weekday())
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == BudgetPeriod.monthly:
        return ts.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == BudgetPeriod.yearly:
        return ts.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:  # BudgetPeriod.all_time
        return None


def get_period_end(ts: datetime, period: BudgetPeriod) -> Optional[datetime]:
    """Get the truncated end datetime for a given period."""
    start = get_period_start(ts, period)
    if start is None:
        return None
    from dateutil.relativedelta import relativedelta

    if period == BudgetPeriod.hourly:
        return start + relativedelta(hours=1)
    elif period == BudgetPeriod.daily:
        return start + relativedelta(days=1)
    elif period == BudgetPeriod.weekly:
        return start + relativedelta(weeks=1)
    elif period == BudgetPeriod.monthly:
        return start + relativedelta(months=1)
    elif period == BudgetPeriod.yearly:
        return start + relativedelta(years=1)
    return None


def record_spend_for_request(
    db: Session,
    account_id: uuid.UUID,
    subject_type: Optional[str],
    subject_id: Optional[str],
    model_alias: Optional[str],
    estimated_cost: float,
    timestamp: datetime,
) -> None:
    """Record spend for a gateway request across all configured granularities."""
    if estimated_cost <= 0:
        return

    periods = list(BudgetPeriod)

    # We always record at account level
    subjects = [("account", None)]
    if subject_type and subject_id:
        try:
            parsed_id = uuid.UUID(str(subject_id))
            subjects.append((subject_type, parsed_id))
        except ValueError:
            pass  # if subject_id is not a valid UUID, just don't record subject-specific spend

    models = [None]  # All models
    if model_alias:
        models.append(model_alias)

    for s_type, s_id in subjects:
        for m_alias in models:
            for p in periods:
                crud_budget_spend.upsert_spend(
                    db=db,
                    account_id=account_id,
                    subject_type=s_type,
                    subject_id=s_id,
                    model_alias=m_alias,
                    period=p,
                    period_start=get_period_start(timestamp, p),
                    spend_increment_usd=estimated_cost,
                )
