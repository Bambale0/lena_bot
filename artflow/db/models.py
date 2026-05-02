# db/models.py
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class GenerationType(str, enum.Enum):
    image = "image"
    video = "video"


class GenerationStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"


class TransactionStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    failed = "failed"
    refunded = "refunded"


class PaymentProvider(str, enum.Enum):
    yookassa = "yookassa"
    cryptobot = "cryptobot"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    full_name: Mapped[str | None] = mapped_column(String(256))
    credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Subscription (prepared, not active in v1)
    is_subscribed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    subscription_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 2-level referral
    referrer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    referrer_l2_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    referral_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)

    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    generations: Mapped[list[Generation]] = relationship(back_populates="user", lazy="noload")
    transactions: Mapped[list[Transaction]] = relationship(back_populates="user", lazy="noload")


class Generation(Base):
    __tablename__ = "generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    task_id: Mapped[str | None] = mapped_column(String(256))  # CometAPI task id
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    gen_type: Mapped[GenerationType] = mapped_column(Enum(GenerationType), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    result_url: Mapped[str | None] = mapped_column(Text)
    credits_spent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[GenerationStatus] = mapped_column(
        Enum(GenerationStatus), default=GenerationStatus.pending, nullable=False
    )
    error_msg: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="generations", lazy="noload")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount_rub: Mapped[float] = mapped_column(Float, nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[PaymentProvider] = mapped_column(Enum(PaymentProvider), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(256), unique=True)  # payment provider id
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus), default=TransactionStatus.pending, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="transactions", lazy="noload")


class PricePlan(Base):
    """Редактируемый прайс-лист — управляется через /admin."""

    __tablename__ = "price_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # e.g. "credits_100"
    label: Mapped[str] = mapped_column(String(128), nullable=False)            # "100 кредитов"
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    price_rub: Mapped[float] = mapped_column(Float, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ModelCost(Base):
    """Стоимость генерации в кредитах — редактируется через /admin."""

    __tablename__ = "model_costs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    gen_type: Mapped[GenerationType] = mapped_column(Enum(GenerationType), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
