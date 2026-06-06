from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from api.public_files import public_url_is_available


def enum_value(value: Any, default: str = "") -> str:
    raw = getattr(value, "value", value)
    return str(raw if raw is not None else default)


def iso_datetime(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def generation_result_urls(generation: Any) -> list[str]:
    raw = getattr(generation, "result_urls", None)
    urls: list[str] = []
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                urls = [str(url) for url in parsed if url]
        except (TypeError, ValueError):
            urls = []
    urls = [url for url in urls if public_url_is_available(url)]
    result_url = getattr(generation, "result_url", None)
    if not urls and result_url and public_url_is_available(str(result_url)):
        urls = [str(result_url)]
    return urls


def generation_result_url(generation: Any) -> str | None:
    result_url = getattr(generation, "result_url", None)
    if result_url and public_url_is_available(str(result_url)):
        return str(result_url)
    urls = generation_result_urls(generation)
    return urls[0] if urls else None


class UserMe(BaseModel):
    id: int
    tg_id: int
    username: str | None
    full_name: str | None
    email: str | None = None
    phone: str | None = None
    photo_url: str | None = None
    credits: float
    referral_code: str
    referral_link: str = ""
    language: str = "ru"
    created_at: str = ""
    is_admin: bool = False
    connected_surfaces: list[str] = Field(default_factory=lambda: ["web", "telegram"])

    @classmethod
    def from_user(
        cls,
        user: Any,
        *,
        admin_ids: list[int] | None = None,
        referral_link: str = "",
    ) -> "UserMe":
        tg_id = int(getattr(user, "tg_id", 0))
        has_telegram = tg_id > 0
        surfaces = ["web"]
        if has_telegram:
            surfaces.append("telegram")
        return cls(
            id=int(getattr(user, "id", 0)),
            tg_id=tg_id,
            username=getattr(user, "username", None),
            full_name=getattr(user, "full_name", None),
            email=getattr(user, "email", None),
            phone=getattr(user, "phone", None),
            photo_url=getattr(user, "photo_url", None),
            credits=float(getattr(user, "credits", 0) or 0),
            referral_code=str(getattr(user, "referral_code", "") or ""),
            referral_link=referral_link,
            language=str(getattr(user, "language", "ru") or "ru"),
            created_at=iso_datetime(getattr(user, "created_at", None)),
            is_admin=tg_id in set(admin_ids or []),
            connected_surfaces=surfaces,
        )


class ModelCostCard(BaseModel):
    model_key: str
    display_name: str
    technical_key: str
    gen_type: str
    credits: float
    capabilities: list[str]
    is_active: bool

    @classmethod
    def from_model_cost(cls, model_cost: Any) -> "ModelCostCard":
        gen_type = enum_value(getattr(model_cost, "gen_type", None))
        capabilities: list[str] = []
        if gen_type == "image":
            capabilities.extend(["text", "image"])
        elif gen_type == "video":
            capabilities.extend(["text", "image", "video"])
        elif gen_type == "music":
            capabilities.extend(["text", "audio"])
        return cls(
            model_key=str(getattr(model_cost, "model_key", "")),
            display_name=str(getattr(model_cost, "display_name", "") or getattr(model_cost, "model_key", "")),
            technical_key=str(getattr(model_cost, "model_key", "")),
            gen_type=gen_type,
            credits=float(getattr(model_cost, "credits", 0) or 0),
            capabilities=capabilities,
            is_active=bool(getattr(model_cost, "is_active", False)),
        )


class PricePlanCard(BaseModel):
    key: str
    label: str
    credits: float
    price_rub: float
    price_stars: int | None = None
    is_active: bool
    sort_order: int

    @classmethod
    def from_price_plan(cls, plan: Any) -> "PricePlanCard":
        return cls(
            key=str(getattr(plan, "key", "")),
            label=str(getattr(plan, "label", "")),
            credits=float(getattr(plan, "credits", 0) or 0),
            price_rub=float(getattr(plan, "price_rub", 0) or 0),
            price_stars=getattr(plan, "price_stars", None),
            is_active=bool(getattr(plan, "is_active", False)),
            sort_order=int(getattr(plan, "sort_order", 0) or 0),
        )


class FeedCard(BaseModel):
    id: int
    type: str = "image"
    result_url: str
    result_urls: list[str] = Field(default_factory=list)
    prompt: str
    prompt_visibility: str = "excerpt"
    model: str
    author: str
    likes: int
    remix_count: int
    shares: int
    aspect_ratio: str | None = None
    quality: str | None = None
    created_at: str
    can_remix: bool = True
    can_use_reference: bool = False

    @classmethod
    def from_feed_card(cls, card: Any) -> "FeedCard":
        generation = getattr(card, "generation", card)
        username = getattr(card, "username", None)
        full_name = getattr(card, "full_name", None)
        author = f"@{username}" if username else (full_name or "anon")
        gen_type = enum_value(getattr(generation, "gen_type", None), "image")
        result_urls = generation_result_urls(generation)
        result_url = generation_result_url(generation) or ""
        return cls(
            id=int(getattr(generation, "id", 0)),
            type=gen_type,
            result_url=result_url,
            result_urls=result_urls,
            prompt=str(getattr(generation, "prompt", "") or ""),
            model=str(getattr(generation, "model", "") or ""),
            author=author,
            likes=int(getattr(generation, "likes_count", 0) or 0),
            remix_count=int(getattr(card, "remix_count", 0) or 0),
            shares=int(getattr(generation, "shares_count", 0) or 0),
            aspect_ratio=getattr(card, "aspect_ratio", None),
            quality=getattr(card, "quality", None),
            created_at=iso_datetime(getattr(generation, "created_at", None)),
            can_remix=bool(result_url),
            can_use_reference=gen_type == "image" and bool(result_url),
        )


class PromptCard(BaseModel):
    id: int
    title: str
    description: str
    prompt_text: str
    preview_url: str | None = None
    model: str | None = None
    tags: list[str]
    likes: int
    uses_count: int
    status: str
    category: str = "other"
    created_at: str = ""
    is_mine: bool = False
    reject_reason: str | None = None
    ai_moderation_decision: str | None = None
    ai_moderation_risk: str | None = None
    ai_moderation_reason: str | None = None
    ai_moderation_recommendation: str | None = None

    @classmethod
    def from_prompt(cls, prompt: Any, *, current_user_id: int | None = None) -> "PromptCard":
        author_id = getattr(prompt, "author_id", None)
        return cls(
            id=int(getattr(prompt, "id", 0)),
            title=str(getattr(prompt, "title", "") or ""),
            description=str(getattr(prompt, "description", "") or ""),
            prompt_text=str(getattr(prompt, "prompt_text", "") or ""),
            preview_url=getattr(prompt, "preview_url", None),
            model=getattr(prompt, "model", None),
            tags=list(getattr(prompt, "tags", None) or []),
            likes=int(getattr(prompt, "likes", 0) or 0),
            uses_count=int(getattr(prompt, "uses_count", 0) or 0),
            status=enum_value(getattr(prompt, "status", None), "pending"),
            category=enum_value(getattr(prompt, "category", None), "other"),
            created_at=iso_datetime(getattr(prompt, "created_at", None)),
            is_mine=bool(current_user_id is not None and author_id == current_user_id),
            reject_reason=getattr(prompt, "reject_reason", None),
            ai_moderation_decision=getattr(prompt, "ai_moderation_decision", None),
            ai_moderation_risk=getattr(prompt, "ai_moderation_risk", None),
            ai_moderation_reason=getattr(prompt, "ai_moderation_reason", None),
            ai_moderation_recommendation=getattr(prompt, "ai_moderation_recommendation", None),
        )


class PromptCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    prompt_text: str = Field(..., min_length=10, max_length=4000)
    tags: list[str] = Field(default_factory=list)
    preview_url: str | None = Field(default=None, max_length=2048)
    model: str | None = Field(default=None, max_length=64)


class GenerationCard(BaseModel):
    id: int
    model: str
    gen_type: str
    prompt: str
    prompt_hidden: bool = False
    prompt_actions_allowed: bool = True
    status: str
    result_url: str | None = None
    result_urls: list[str]
    credits_spent: float
    is_public_feed: bool
    is_prompt_library: bool
    error: str | None = None
    created_at: str
    finished_at: str = ""

    @classmethod
    def from_generation(cls, generation: Any) -> "GenerationCard":
        prompt_hidden = bool(getattr(generation, "source_feed_gen_id", None))
        return cls(
            id=int(getattr(generation, "id", 0)),
            model=str(getattr(generation, "model", "") or ""),
            gen_type=enum_value(getattr(generation, "gen_type", None)),
            prompt="" if prompt_hidden else str(getattr(generation, "prompt", "") or ""),
            prompt_hidden=prompt_hidden,
            prompt_actions_allowed=not prompt_hidden,
            status=enum_value(getattr(generation, "status", None)),
            result_url=generation_result_url(generation),
            result_urls=generation_result_urls(generation),
            credits_spent=float(getattr(generation, "credits_spent", 0) or 0),
            is_public_feed=bool(getattr(generation, "is_public_feed", False)),
            is_prompt_library=bool(getattr(generation, "is_prompt_library", False)),
            error=getattr(generation, "error_msg", None),
            created_at=iso_datetime(getattr(generation, "created_at", None)),
            finished_at=iso_datetime(getattr(generation, "finished_at", None)),
        )


class ImageSessionCard(BaseModel):
    id: int
    model: str
    mode: str
    aspect_ratio: str | None = None
    quality: str
    count: int
    base_prompt: str | None = None
    last_prompt: str | None = None
    reference_url: str | None = None
    last_result_url: str | None = None
    last_generation_id: int | None = None
    status: str
    created_at: str
    updated_at: str

    @classmethod
    def from_image_session(cls, image_session: Any) -> "ImageSessionCard":
        return cls(
            id=int(getattr(image_session, "id", 0)),
            model=str(getattr(image_session, "model", "") or ""),
            mode=str(getattr(image_session, "mode", "") or ""),
            aspect_ratio=getattr(image_session, "aspect_ratio", None),
            quality=str(getattr(image_session, "quality", "") or ""),
            count=int(getattr(image_session, "count", 0) or 0),
            base_prompt=getattr(image_session, "base_prompt", None),
            last_prompt=getattr(image_session, "last_prompt", None),
            reference_url=getattr(image_session, "reference_url", None),
            last_result_url=getattr(image_session, "last_result_url", None),
            last_generation_id=getattr(image_session, "last_generation_id", None),
            status=enum_value(getattr(image_session, "status", None)),
            created_at=iso_datetime(getattr(image_session, "created_at", None)),
            updated_at=iso_datetime(getattr(image_session, "updated_at", None)),
        )


class ImageSessionCreateRequest(BaseModel):
    model: str = Field(default="flux-pro", min_length=1, max_length=64)
    mode: str = Field(default="text", min_length=1, max_length=32)
    aspect_ratio: str | None = Field(default=None, max_length=32)
    quality: str = Field(default="basic", min_length=1, max_length=32)
    count: int = Field(default=1, ge=1, le=6)
    base_prompt: str | None = Field(default=None, max_length=4000)
    reference_url: str | None = Field(default=None, max_length=2048)


class TransactionCard(BaseModel):
    id: int
    amount_rub: float
    credits: float
    provider: str
    status: str
    external_id: str | None = None
    created_at: str

    @classmethod
    def from_transaction(cls, transaction: Any) -> "TransactionCard":
        return cls(
            id=int(getattr(transaction, "id", 0)),
            amount_rub=float(getattr(transaction, "amount_rub", 0) or 0),
            credits=float(getattr(transaction, "credits", 0) or 0),
            provider=enum_value(getattr(transaction, "provider", None)),
            status=enum_value(getattr(transaction, "status", None), "pending"),
            external_id=getattr(transaction, "external_id", None),
            created_at=iso_datetime(getattr(transaction, "created_at", None)),
        )


class ReferralChildCard(BaseModel):
    id: int
    username: str | None
    full_name: str | None
    generations_count: int
    paid_rub: float


class ReferralWithdrawalCard(BaseModel):
    id: int
    amount_rub: float
    payout_details: str
    status: str
    created_at: str

    @classmethod
    def from_withdrawal(cls, withdrawal: Any) -> "ReferralWithdrawalCard":
        return cls(
            id=int(getattr(withdrawal, "id", 0) or 0),
            amount_rub=float(getattr(withdrawal, "amount_rub", 0) or 0),
            payout_details=str(getattr(withdrawal, "payout_details", "") or ""),
            status=enum_value(getattr(withdrawal, "status", None), "pending"),
            created_at=iso_datetime(getattr(withdrawal, "created_at", None)),
        )


class ReferralStatsCard(BaseModel):
    referral_code: str
    referral_link: str
    bonus_l1_credits: float
    commission_l1: float
    commission_l2: float
    commission_l3: float
    withdraw_min_rub: float
    counts: dict[str, int]
    balance: dict[str, float]
    feed_remix_reward_rub: float
    children: dict[str, list[ReferralChildCard]]
    withdrawals: list[ReferralWithdrawalCard]


class ReferralWithdrawalRequest(BaseModel):
    amount_rub: float = Field(..., gt=0)
    payout_details: str = Field(..., min_length=5, max_length=500)


class PromptRejectRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
