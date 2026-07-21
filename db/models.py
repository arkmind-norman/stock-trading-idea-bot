from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import List, Optional

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.database import Base


class Direction(PyEnum):
    long = "long"
    short = "short"


class IdeaStatus(PyEnum):
    pending = "pending"
    open = "open"
    closed = "closed"
    rejected = "rejected"


class PositionStatus(PyEnum):
    open = "open"
    closed = "closed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(128))
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    first_idea_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    photo_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    ideas: Mapped[List[Idea]] = relationship(back_populates="user")
    equity_history: Mapped[List[DailyEquity]] = relationship(back_populates="user")


class Idea(Base):
    __tablename__ = "ideas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    ticker: Mapped[Optional[str]] = mapped_column(String(16))
    company_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    direction: Mapped[Optional[Direction]] = mapped_column(Enum(Direction))
    target_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    stop_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    submitted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[IdeaStatus] = mapped_column(Enum(IdeaStatus), default=IdeaStatus.pending)

    user: Mapped[User] = relationship(back_populates="ideas")
    position: Mapped[Optional[Position]] = relationship(back_populates="idea", uselist=False)


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    idea_id: Mapped[int] = mapped_column(ForeignKey("ideas.id"), unique=True, nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    entry_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    exit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    exit_time: Mapped[Optional[datetime]] = mapped_column(DateTime)
    notional: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    status: Mapped[PositionStatus] = mapped_column(Enum(PositionStatus), default=PositionStatus.open)
    pnl: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))

    idea: Mapped[Idea] = relationship(back_populates="position")


class DailyEquity(Base):
    __tablename__ = "daily_equity"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    cumulative_pnl: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    cumulative_equity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)

    user: Mapped[User] = relationship(back_populates="equity_history")


class PriceTick(Base):
    __tablename__ = "price_ticks"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
