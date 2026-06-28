"""Commitment ORM (mirrors public.commitments) — recurring EMIs & subscriptions."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Commitment(Base):
    __tablename__ = "commitments"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # emi | subscription
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)  # minor units, per cycle
    cycle: Mapped[str] = mapped_column(String(12), nullable=False, default="monthly")
    due_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    months_left: Mapped[int | None] = mapped_column(Integer, nullable=True)
    icon: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
