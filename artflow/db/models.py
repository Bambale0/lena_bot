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


class ImageSessionStatus(str, enum.Enum):
    active = "active"
    archived = "archived"


class ImageGenerationAction(str, enum.Enum):
    initial = "initial"
    remix = "remix"
    repeat = "repeat"
    reference_update = "reference_update"
    animate = "animate"


class TransactionStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"
    failed = "failed"
    refunded = "refunded"


class PaymentProvider(str, enum.Enum):
    yookassa = "yookassa"
    cryptobot = "cryptobot"
    tbank = "tbank"


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
    task_id: Mapped[str | None] = mapped_column(String(256), index=True)  # KIE task id
    image_session_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("image_sessions.id"),
        nullable=True,
        index=True,
    )
    parent_generation_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("generations.id"),
        nullable=True,
    )
    action_type: Mapped[ImageGenerationAction | None] = mapped_column(
        Enum(ImageGenerationAction),
        nullable=True,
    )
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



class ImageSession(Base):
    """Saved image generation settings for iterative Syntx-like workflow."""

    __tablename__ = "image_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    model: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), default="text", nullable=False)
    aspect_ratio: Mapped[str | None] = mapped_column(String(32))
    quality: Mapped[str] = mapped_column(String(32), default="basic", nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    base_prompt: Mapped[str | None] = mapped_column(Text)
    last_prompt: Mapped[str | None] = mapped_column(Text)
    reference_file_id: Mapped[str | None] = mapped_column(Text)
    last_result_url: Mapped[str | None] = mapped_column(Text)
    last_generation_id: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[ImageSessionStatus] = mapped_column(
        Enum(ImageSessionStatus),
        default=ImageSessionStatus.active,
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship(lazy="noload")


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


# ── Marketplace промптов ───────────────────────────────────────────────────────

class PromptCategory(str, enum.Enum):
    art = "art"
    business = "business"
    marketing = "marketing"
    photo = "photo"
    other = "other"

    def label(self) -> str:
        return {
            "art": "🎨 Арт",
            "business": "💼 Бизнес",
            "marketing": "📣 Маркетинг",
            "photo": "📸 Фото",
            "other": "🗂 Разное",
        }[self.value]


class PromptStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    deactivated = "deactivated"


class UserPrompt(Base):
    __tablename__ = "user_prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[PromptCategory] = mapped_column(Enum(PromptCategory), nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[PromptStatus] = mapped_column(
        Enum(PromptStatus), default=PromptStatus.pending, nullable=False, index=True
    )
    reject_reason: Mapped[str | None] = mapped_column(String(500))
    uses_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    author: Mapped["User"] = relationship(lazy="noload")
