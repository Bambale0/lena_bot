from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from api.public_files import public_url_is_available, preview_public_image_url
from core.config import settings


def _is_previewable_image(url: str | None, gen_type: str | None = None) -> bool:
    if str(gen_type or "").lower() in {"video", "music", "audio"}:
        return False
    value = str(url or "").strip().lower().split("?", 1)[0].split("#", 1)[0]
    return bool(value) and not value.endswith((".mp4", ".mov", ".webm", ".mkv", ".avi", ".mp3", ".wav", ".ogg", ".m4a"))


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


def json_url_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if item]


def generation_preview_urls(generation: Any) -> list[str]:
    gen_type = enum_value(getattr(generation, "gen_type", None))
    urls = generation_result_urls(generation)
    return [preview_public_image_url(url) if _is_previewable_image(url, gen_type) else url for url in urls]


def generation_preview_url(generation: Any) -> str | None:
    result_url = generation_result_url(generation)
    if not result_url:
        return None
    gen_type = enum_value(getattr(generation, "gen_type", None))
    return preview_public_image_url(result_url) if _is_previewable_image(result_url, gen_type) else result_url


def prompt_preview_url(prompt: Any, fallback_url: str | None = None) -> str | None:
    preview_url = getattr(prompt, "preview_url", None)
    if not public_url_is_available(preview_url):
        preview_url = fallback_url
    if not public_url_is_available(preview_url):
        return None
    return preview_public_image_url(preview_url) if _is_previewable_image(preview_url) else preview_url


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
    has_password: bool = False
    password_set_at: str = ""
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
        if getattr(user, "password_hash", None):
            surfaces.append("password")
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
            has_password=bool(getattr(user, "password_hash", None)),
            password_set_at=iso_datetime(getattr(user, "password_set_at", None)),
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
    preview_url: str | None = None
    preview_urls: list[str] = Field(default_factory=list)
    prompt: str
    prompt_visibility: str = "excerpt"
    model: str
    author: str
    author_photo_url: str | None = None
    likes: int
    remix_count: int
    shares: int
    aspect_ratio: str | None = None
    quality: str | None = None
    reference_url: str | None = None
    reference_urls: list[str] = Field(default_factory=list)
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
        reference_urls = json_url_list(getattr(card, "reference_urls", None))
        reference_url = getattr(card, "reference_url", None)
        if reference_url and reference_url not in reference_urls:
            reference_urls.insert(0, str(reference_url))
        return cls(
            id=int(getattr(generation, "id", 0)),
            type=gen_type,
            result_url=result_url,
            result_urls=result_urls,
            preview_url=generation_preview_url(generation),
            preview_urls=generation_preview_urls(generation),
            prompt=str(getattr(generation, "prompt", "") or ""),
            model=str(getattr(generation, "model", "") or ""),
            author=author,
            author_photo_url=getattr(card, "author_photo_url", None),
            likes=int(getattr(generation, "likes_count", 0) or 0),
            remix_count=int(getattr(card, "remix_count", 0) or 0),
            shares=int(getattr(generation, "shares_count", 0) or 0),
            aspect_ratio=getattr(card, "aspect_ratio", None),
            quality=getattr(card, "quality", None),
            reference_url=reference_urls[0] if reference_urls else None,
            reference_urls=reference_urls,
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
    def from_prompt(
        cls,
        prompt: Any,
        *,
        current_user_id: int | None = None,
        fallback_preview_url: str | None = None,
    ) -> "PromptCard":
        author_id = getattr(prompt, "author_id", None)
        return cls(
            id=int(getattr(prompt, "id", 0)),
            title=str(getattr(prompt, "title", "") or ""),
            description=str(getattr(prompt, "description", "") or ""),
            prompt_text=str(getattr(prompt, "prompt_text", "") or ""),
            preview_url=prompt_preview_url(prompt, fallback_preview_url),
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
    preview_url: str | None = None
    preview_urls: list[str] = Field(default_factory=list)
    image_session_id: int | None = None
    parent_generation_id: int | None = None
    source_feed_gen_id: int | None = None
    action_type: str | None = None
    reference_url: str | None = None
    reference_urls: list[str] = Field(default_factory=list)
    session_last_prompt: str | None = None
    session_last_result_url: str | None = None
    credits_spent: float
    is_public_feed: bool
    is_prompt_library: bool
    error: str | None = None
    created_at: str
    finished_at: str = ""

    @classmethod
    def from_generation(cls, generation: Any, *, image_session: Any | None = None) -> "GenerationCard":
        prompt_hidden = bool(getattr(generation, "source_feed_gen_id", None))
        reference_urls = json_url_list(getattr(image_session, "reference_urls", None)) if image_session is not None else []
        reference_url = getattr(image_session, "reference_url", None) if image_session is not None else None
        if reference_url and reference_url not in reference_urls:
            reference_urls.insert(0, str(reference_url))
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
            preview_url=generation_preview_url(generation),
            preview_urls=generation_preview_urls(generation),
            image_session_id=getattr(generation, "image_session_id", None),
            parent_generation_id=getattr(generation, "parent_generation_id", None),
            source_feed_gen_id=getattr(generation, "source_feed_gen_id", None),
            action_type=enum_value(getattr(generation, "action_type", None)) or None,
            reference_url=reference_urls[0] if reference_urls else None,
            reference_urls=reference_urls,
            session_last_prompt=(None if prompt_hidden else getattr(image_session, "last_prompt", None)) if image_session is not None else None,
            session_last_result_url=getattr(image_session, "last_result_url", None) if image_session is not None else None,
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
    prompt_hidden: bool = False
    prompt_actions_allowed: bool = True
    reference_url: str | None = None
    reference_urls: list[str] = Field(default_factory=list)
    last_result_url: str | None = None
    last_generation_id: int | None = None
    status: str
    created_at: str
    updated_at: str

    @classmethod
    def from_image_session(cls, image_session: Any, *, hide_prompt: bool = False) -> "ImageSessionCard":
        reference_urls = json_url_list(getattr(image_session, "reference_urls", None))
        reference_url = getattr(image_session, "reference_url", None)
        if reference_url and reference_url not in reference_urls:
            reference_urls.insert(0, str(reference_url))
        return cls(
            id=int(getattr(image_session, "id", 0)),
            model=str(getattr(image_session, "model", "") or ""),
            mode=str(getattr(image_session, "mode", "") or ""),
            aspect_ratio=getattr(image_session, "aspect_ratio", None),
            quality=str(getattr(image_session, "quality", "") or ""),
            count=int(getattr(image_session, "count", 0) or 0),
            base_prompt=None if hide_prompt else getattr(image_session, "base_prompt", None),
            last_prompt=None if hide_prompt else getattr(image_session, "last_prompt", None),
            prompt_hidden=hide_prompt,
            prompt_actions_allowed=not hide_prompt,
            reference_url=getattr(image_session, "reference_url", None),
            reference_urls=reference_urls,
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
    reference_urls: list[str] = Field(default_factory=list)


class TransactionCard(BaseModel):
    id: int
    amount_rub: float
    amount_credits: float | None = None
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
    amount_credits: float | None = None
    payout_details: str
    status: str
    created_at: str

    @classmethod
    def from_withdrawal(cls, withdrawal: Any) -> "ReferralWithdrawalCard":
        amount_rub = float(getattr(withdrawal, "amount_rub", 0) or 0)
        payout_details = str(getattr(withdrawal, "payout_details", "") or "")
        amount_credits = getattr(withdrawal, "amount_credits", None)
        if amount_credits is None and payout_details == "AUTO_CREDITS":
            rub_per_credit = float(getattr(settings, "REFERRAL_EXCHANGE_RUB_PER_CREDIT", 10.0) or 10.0)
            amount_credits = amount_rub / rub_per_credit
        return cls(
            id=int(getattr(withdrawal, "id", 0) or 0),
            amount_rub=amount_rub,
            amount_credits=float(amount_credits) if amount_credits is not None else None,
            payout_details=payout_details,
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
    withdraw_min_credits: float | None = None
    exchange_min_rub: float | None = None
    exchange_rate_rub_per_credit: float | None = None
    counts: dict[str, int]
    balance: dict[str, float]
    feed_remix_reward_rub: float
    children: dict[str, list[ReferralChildCard]]
    withdrawals: list[ReferralWithdrawalCard]


class ReferralWithdrawalRequest(BaseModel):
    amount_rub: float = Field(..., gt=0)
    payout_details: str = Field(default="AUTO_CREDITS", min_length=0, max_length=500)


class PromptRejectRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
