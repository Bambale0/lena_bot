# db/models.py
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class GenerationType(str, enum.Enum):
    image = "image"
    video = "video"
    music = "music"


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
    telegram_stars = "telegram_stars"
    lava = "lava"


class PromoRewardType(str, enum.Enum):
    credits = "credits"
    discount_percent = "discount_percent"
    discount_amount = "discount_amount"
    free_generation = "free_generation"


class WithdrawalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    full_name: Mapped[str | None] = mapped_column(String(256))
    email: Mapped[str | None] = mapped_column(String(256), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    photo_url: Mapped[str | None] = mapped_column(Text)
    credits: Mapped[float] = mapped_column(Float, default=0, nullable=False)

    # Subscription (prepared, not active in v1)
    is_subscribed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    subscription_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 3-level referral
    referrer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    referrer_l2_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    referrer_l3_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    referral_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    referral_balance: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, server_default="0")

    language: Mapped[str] = mapped_column(String(8), default="ru", nullable=False, server_default="ru")

    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    generations: Mapped[list[Generation]] = relationship(back_populates="user", lazy="noload")
    transactions: Mapped[list[Transaction]] = relationship(back_populates="user", lazy="noload")
    withdrawal_requests: Mapped[list[ReferralWithdrawalRequest]] = relationship(back_populates="user", lazy="noload")


class WebAuthCode(Base):
    __tablename__ = "web_auth_codes"
    __table_args__ = (
        UniqueConstraint("contact_type", "contact", "code_hash", name="uq_web_auth_codes_contact_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contact_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    contact: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
    result_urls: Mapped[str | None] = mapped_column(Text)
    is_public_feed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_prompt_library: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_feed_gen_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("generations.id"), nullable=True
    )
    likes_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    shares_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    credits_spent: Mapped[float] = mapped_column(Float, default=0, nullable=False)
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
    reference_file_ids: Mapped[str | None] = mapped_column(Text)
    reference_url: Mapped[str | None] = mapped_column(Text)
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
    credits: Mapped[float] = mapped_column(Float, nullable=False)
    provider: Mapped[PaymentProvider] = mapped_column(Enum(PaymentProvider), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(256), unique=True)  # payment provider id
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus), default=TransactionStatus.pending, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="transactions", lazy="noload")


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    reward_type: Mapped[PromoRewardType] = mapped_column(Enum(PromoRewardType), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    credits: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    max_uses: Mapped[int | None] = mapped_column(Integer)
    max_redemptions: Mapped[int | None] = mapped_column(Integer)
    per_user_limit: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    uses_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    redeemed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_tg_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PromoRedemption(Base):
    __tablename__ = "promo_redemptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    promo_code_id: Mapped[int] = mapped_column(Integer, ForeignKey("promo_codes.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    transaction_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("transactions.id"), nullable=True, index=True)
    reward_type: Mapped[PromoRewardType] = mapped_column(Enum(PromoRewardType), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    promo_code: Mapped[PromoCode] = relationship(lazy="noload")
    user: Mapped[User] = relationship(lazy="noload")
    transaction: Mapped[Transaction | None] = relationship(lazy="noload")


class CreditLedgerEntry(Base):
    __tablename__ = "credit_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    delta: Mapped[float] = mapped_column(Float, nullable=False)
    balance_after: Mapped[float] = mapped_column(Float, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_type: Mapped[str | None] = mapped_column(String(64), index=True)
    source_id: Mapped[str | None] = mapped_column(String(128), index=True)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class ReferralWithdrawalRequest(Base):
    __tablename__ = "referral_withdrawal_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount_rub: Mapped[float] = mapped_column(Float, nullable=False)
    payout_details: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[WithdrawalStatus] = mapped_column(
        Enum(WithdrawalStatus),
        default=WithdrawalStatus.pending,
        nullable=False,
        index=True,
    )
    admin_tg_id: Mapped[int | None] = mapped_column(BigInteger)
    admin_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="withdrawal_requests", lazy="noload")


class PricePlan(Base):
    """Редактируемый прайс-лист — управляется через /admin."""

    __tablename__ = "price_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # e.g. "credits_100"
    label: Mapped[str] = mapped_column(String(128), nullable=False)            # "100 кредитов"
    credits: Mapped[float] = mapped_column(Float, nullable=False)
    price_rub: Mapped[float] = mapped_column(Float, nullable=False)
    price_stars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ModelCost(Base):
    """Стоимость генерации в кредитах — редактируется через /admin."""

    __tablename__ = "model_costs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    gen_type: Mapped[GenerationType] = mapped_column(Enum(GenerationType), nullable=False)
    credits: Mapped[float] = mapped_column(Float, nullable=False)
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
    preview_url: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(64))
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    likes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[PromptStatus] = mapped_column(
        Enum(PromptStatus), default=PromptStatus.pending, nullable=False, index=True
    )
    reject_reason: Mapped[str | None] = mapped_column(String(500))
    ai_moderation_decision: Mapped[str | None] = mapped_column(String(32))
    ai_moderation_risk: Mapped[str | None] = mapped_column(String(16))
    ai_moderation_reason: Mapped[str | None] = mapped_column(String(500))
    ai_moderation_recommendation: Mapped[str | None] = mapped_column(String(500))
    ai_moderation_raw: Mapped[str | None] = mapped_column(Text)
    ai_moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uses_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    author: Mapped["User"] = relationship(lazy="noload")


class PromptLike(Base):
    __tablename__ = "prompt_likes"
    __table_args__ = (
        UniqueConstraint("user_id", "prompt_id", name="uq_prompt_likes_user_prompt"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    prompt_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_prompts.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(lazy="noload")
    prompt: Mapped["UserPrompt"] = relationship(lazy="noload")
