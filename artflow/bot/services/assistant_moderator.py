from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from aiogram import Bot
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.assistant_service import generate_prompt_moderation_review
from db import prompt_repository
from db import repository as repo
from db.models import (
    CreditLedgerEntry,
    Generation,
    GenerationStatus,
    Transaction,
    TransactionStatus,
    User,
    WithdrawalStatus,
)
from db.repository import InsufficientReferralBalanceError

logger = logging.getLogger(__name__)
_MSK_TZ = ZoneInfo("Europe/Moscow")
_REPORT_USER_SKIP_TOKENS = {
    "user",
    "tg",
    "id",
    "db",
    "db_id",
    "telegram",
    "report",
    "summary",
}


@dataclass(frozen=True)
class AdminAssistantOutcome:
    text: str


def is_admin_tg_id(tg_id: int) -> bool:
    from core.config import settings

    return tg_id in settings.ADMIN_IDS


def _normalize_text(text: str) -> str:
    return " ".join((text or "").strip().lower().replace("ё", "е").split())


def _extract_amount(raw: str) -> float | None:
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def _clean_reason(raw: str | None) -> str | None:
    if not raw:
        return None
    reason = raw.strip(" -:;,")
    return reason or None


def _format_msk_datetime(value) -> str:
    if not value:
        return "—"
    if getattr(value, "tzinfo", None):
        return value.astimezone(_MSK_TZ).strftime("%d.%m.%Y %H:%M")
    if hasattr(value, "strftime"):
        return value.strftime("%d.%m.%Y %H:%M")
    return str(value)


def _format_credits(value: float | int | None) -> str:
    return f"{float(value or 0):g}"


def _format_rub(value: float | int | None) -> str:
    amount = float(value or 0)
    return f"{amount:.0f}₽" if amount.is_integer() else f"{amount:.2f}₽"


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


async def _resolve_user(session: AsyncSession, token: str) -> User | None:
    cleaned = token.strip()
    if not cleaned:
        return None
    if cleaned.startswith("@"):
        return await repo.get_user_by_username(session, cleaned)
    if cleaned.isdigit():
        return await repo.get_user_by_tg_id(session, int(cleaned))
    if re.fullmatch(r"[A-Za-z0-9_]{3,64}", cleaned):
        return await repo.get_user_by_username(session, cleaned)
    return None


async def _resolve_user_for_report(
    session: AsyncSession,
    token: str,
    *,
    prefer_db_id: bool = False,
) -> User | None:
    cleaned = token.strip()
    if not cleaned:
        return None
    if prefer_db_id and cleaned.isdigit():
        user = await repo.get_user_by_id(session, int(cleaned))
        if user:
            return user
    if cleaned.isdigit():
        user = await repo.get_user_by_tg_id(session, int(cleaned))
        if user:
            return user
        return await repo.get_user_by_id(session, int(cleaned))
    return await _resolve_user(session, cleaned)


def _has_user_report_intent(normalized: str) -> bool:
    return (
        any(word in normalized for word in ("сводк", "отчет", "отчёт", "инф", "карточк", "профил", "детал"))
        or "любимая ии" in normalized
        or "любимый ии" in normalized
        or "любимую ии" in normalized
        or ("оплат" in normalized and ("реферал" in normalized or "приглаш" in normalized or "ии" in normalized))
        or ("статист" in normalized and any(word in normalized for word in ("пользовател", "юзер", "user")))
    )


def _extract_report_user_token(source: str, normalized: str) -> tuple[str, bool] | None:
    if not _has_user_report_intent(normalized):
        return None

    db_match = re.search(
        r"(?:db(?:[_\s-]*id)?|database\s*id|внутренн(?:ий|его)?\s+id)\s*[:#]?\s*(\d+)",
        source,
        re.I,
    )
    if db_match:
        return db_match.group(1), True

    tg_match = re.search(r"(?:tg(?:\s*id)?|тг(?:\s*id)?|telegram(?:\s*id)?)\s*[:#]?\s*(\d+)", source, re.I)
    if tg_match:
        return tg_match.group(1), False

    username_match = re.search(r"@[A-Za-z0-9_]{3,64}", source)
    if username_match:
        return username_match.group(0), False

    tokens = re.findall(r"\b\d{3,20}\b|\b[A-Za-z][A-Za-z0-9_]{2,63}\b", source)
    for token in tokens:
        if token.lower() not in _REPORT_USER_SKIP_TOKENS:
            return token, False
    return None


def _format_user_brief_report(
    *,
    user: User,
    paid_transactions: list[Transaction],
    direct_referrals_count: int,
    second_line_referrals_count: int,
    direct_referrals_paid_total: float,
    signup_bonus_credits: float,
    generations_total: int,
    generations_done: int,
    generations_failed: int,
    credits_spent: float,
    favorite_model: tuple[str, int, float] | None,
) -> str:
    name = f"@{user.username}" if user.username else (user.full_name or f"TG {user.tg_id}")
    full_name = user.full_name or "—"
    paid_total = sum(float(tx.amount_rub or 0) for tx in paid_transactions)
    status = "забанен" if user.is_banned else "активен"
    subscription = "есть" if user.is_subscribed else "нет"

    lines = [
        "Сводка по пользователю",
        f"{name} / {full_name}",
        f"TG ID: {user.tg_id}",
        f"Регистрация: {_format_msk_datetime(user.created_at)} MSK",
        f"Статус: {status}, подписка {subscription}",
        f"Баланс: {_format_credits(user.credits)} 💋",
        f"Реф. баланс: {float(user.referral_balance or 0):.2f}₽",
        "",
        "Оплаты",
        f"Всего paid: {_format_rub(paid_total)} ({len(paid_transactions)} платежа)",
    ]
    if paid_transactions:
        for tx in paid_transactions:
            provider = _enum_value(tx.provider)
            lines.append(
                f"• {_format_rub(tx.amount_rub)} → {_format_credits(tx.credits)} кр., "
                f"{provider}, {_format_msk_datetime(tx.created_at)}, tx {tx.id}"
            )
    else:
        lines.append("• успешных оплат нет")

    lines.extend(
        [
            "",
            "Приглашённые",
            f"Прямых: {direct_referrals_count}, 2-я линия: {second_line_referrals_count}",
            f"Оплат от прямых: {_format_rub(direct_referrals_paid_total)}",
            f"Бонусов за регистрации: {_format_credits(signup_bonus_credits)} 💋",
            "",
            "Активность и ИИ",
            f"Генерации: {generations_total} всего, {generations_done} успешных, {generations_failed} failed",
            f"Потрачено: {_format_credits(credits_spent)} 💋",
        ]
    )
    if favorite_model:
        model, count, model_spent = favorite_model
        lines.append(f"Любимая ИИ: {model} ({count} запусков, {_format_credits(model_spent)} 💋)")
    else:
        lines.append("Любимая ИИ: пока нет запусков")
    return "\n".join(lines)


async def _build_user_brief_report(session: AsyncSession, user: User) -> str:
    paid_transactions = (
        await session.execute(
            select(Transaction)
            .where(Transaction.user_id == user.id, Transaction.status == TransactionStatus.paid)
            .order_by(Transaction.created_at.asc(), Transaction.id.asc())
        )
    ).scalars().all()
    generations_by_status = (
        await session.execute(
            select(
                Generation.status,
                func.count(Generation.id),
                func.coalesce(func.sum(Generation.credits_spent), 0),
            )
            .where(Generation.user_id == user.id)
            .group_by(Generation.status)
        )
    ).all()
    generations_total = sum(int(count or 0) for _, count, _ in generations_by_status)
    generations_done = sum(
        int(count or 0)
        for status, count, _ in generations_by_status
        if _enum_value(status) == GenerationStatus.done.value
    )
    generations_failed = sum(
        int(count or 0)
        for status, count, _ in generations_by_status
        if _enum_value(status) == GenerationStatus.failed.value
    )
    credits_spent = sum(float(spent or 0) for _, _, spent in generations_by_status)
    model_count = func.count(Generation.id)
    model_spent = func.coalesce(func.sum(Generation.credits_spent), 0)
    favorite_row = (
        await session.execute(
            select(
                Generation.model,
                model_count,
                model_spent,
            )
            .where(Generation.user_id == user.id)
            .group_by(Generation.model)
            .order_by(model_count.desc(), model_spent.desc())
            .limit(1)
        )
    ).one_or_none()
    favorite_model = (
        (str(favorite_row[0]), int(favorite_row[1] or 0), float(favorite_row[2] or 0))
        if favorite_row
        else None
    )
    direct_referrals_count = int(
        (
            await session.execute(select(func.count(User.id)).where(User.referrer_id == user.id))
        ).scalar_one()
        or 0
    )
    second_line_referrals_count = int(
        (
            await session.execute(select(func.count(User.id)).where(User.referrer_l2_id == user.id))
        ).scalar_one()
        or 0
    )
    direct_referrals_paid_total = float(
        (
            await session.execute(
                select(func.coalesce(func.sum(Transaction.amount_rub), 0))
                .join(User, User.id == Transaction.user_id)
                .where(User.referrer_id == user.id, Transaction.status == TransactionStatus.paid)
            )
        ).scalar_one()
        or 0
    )
    signup_bonus_credits = float(
        (
            await session.execute(
                select(func.coalesce(func.sum(CreditLedgerEntry.delta), 0)).where(
                    CreditLedgerEntry.user_id == user.id,
                    CreditLedgerEntry.entry_type == "referral_signup_bonus",
                )
            )
        ).scalar_one()
        or 0
    )
    return _format_user_brief_report(
        user=user,
        paid_transactions=list(paid_transactions),
        direct_referrals_count=direct_referrals_count,
        second_line_referrals_count=second_line_referrals_count,
        direct_referrals_paid_total=direct_referrals_paid_total,
        signup_bonus_credits=signup_bonus_credits,
        generations_total=generations_total,
        generations_done=generations_done,
        generations_failed=generations_failed,
        credits_spent=credits_spent,
        favorite_model=favorite_model,
    )


def _user_title(user: User) -> str:
    username = f"@{user.username}" if user.username else "без username"
    full_name = user.full_name or "Без имени"
    return f"{full_name} ({username}, tg_id {user.tg_id})"


async def try_handle_admin_request(
    text: str,
    *,
    session: AsyncSession,
    bot: Bot,
    admin_tg_id: int,
) -> AdminAssistantOutcome | None:
    if not is_admin_tg_id(admin_tg_id):
        logger.warning("assistant moderator access denied for tg_id=%s", admin_tg_id)
        return None

    source = " ".join((text or "").strip().replace("ё", "е").split())
    normalized = _normalize_text(text)
    if not normalized:
        return AdminAssistantOutcome("Напиши, что нужно проверить или сделать.")

    if any(phrase in normalized for phrase in ("что ты умеешь", "что умееш", "помощь", "команды модератора", "что можно")):
        return AdminAssistantOutcome(
            "Я могу помогать как модератор: показывать статистику, очередь промптов и выводов, "
            "искать пользователя, банить и разбанивать, начислять 💋, "
            "одобрять и отклонять промпты, а также разбирать спорный промпт через ИИ.\n\n"
            "Примеры:\n"
            "• статистика\n"
            "• промпты на модерации\n"
            "• заявки на вывод\n"
            "• найди пользователя 123456789\n"
            "• забань 123456789\n"
            "• разбань @username\n"
            "• начисли 50 123456789\n"
            "• сводка @username\n"
            "• одобри промпт 42\n"
            "• отклони промпт 42: причина\n"
            "• проверь промпт 42\n"
            "• подтверди вывод 15\n"
            "• отклони вывод 15: причина"
        )

    report_token = _extract_report_user_token(source, normalized)
    if report_token:
        token, prefer_db_id = report_token
        user = await _resolve_user_for_report(session, token, prefer_db_id=prefer_db_id)
        if not user:
            return AdminAssistantOutcome(f"Пользователь {token} не найден.")
        return AdminAssistantOutcome(await _build_user_brief_report(session, user))
    if _has_user_report_intent(normalized):
        return AdminAssistantOutcome(
            "Укажи пользователя для сводки: username, TG ID или DB ID.\n"
            "Примеры: сводка @username, отчет tg id 6006348428, отчет db id 273."
        )

    if (
        "статист" in normalized
        or "сколько пользователей" in normalized
        or "выручка" in normalized
        or "генерац" in normalized
    ):
        users = await repo.count_users(session)
        gens_today = await repo.count_generations_today(session)
        revenue = await repo.get_revenue_today(session)
        pending_prompts = await prompt_repository.get_pending_prompts(session)
        pending_withdrawals = await repo.get_pending_withdrawal_requests(session, limit=20)
        return AdminAssistantOutcome(
            "Статистика APIX:\n"
            f"• Пользователей: {int(users)}\n"
            f"• Генераций сегодня: {int(gens_today)}\n"
            f"• Выручка сегодня: {revenue:.2f}₽\n"
            f"• Промптов на модерации: {len(pending_prompts)}\n"
            f"• Заявок на вывод: {len(pending_withdrawals)}"
        )

    if "промпт" in normalized and any(word in normalized for word in ("модерац", "очеред", "pending", "на проверке")):
        pending = await prompt_repository.get_pending_prompts(session)
        if not pending:
            return AdminAssistantOutcome("Сейчас нет промптов на модерации.")
        lines = ["Промпты на модерации:"]
        for prompt in pending[:8]:
            author = await repo.get_user_by_id(session, prompt.author_id)
            author_label = f"@{author.username}" if author and author.username else str(prompt.author_id)
            lines.append(f"• #{prompt.id} — {prompt.title} · {author_label}")
        lines.append("\nНапиши, например: одобри промпт 42 или проверь промпт 42.")
        return AdminAssistantOutcome("\n".join(lines))

    if "заяв" in normalized and "вывод" in normalized:
        requests = await repo.get_pending_withdrawal_requests(session, limit=8)
        if not requests:
            return AdminAssistantOutcome("Сейчас нет ожидающих заявок на вывод.")
        lines = ["Заявки на вывод:"]
        for view in requests:
            req = view.request
            user = view.user
            username = f"@{user.username}" if user.username else str(user.tg_id)
            lines.append(f"• #{req.id} — {req.amount_rub:.0f}₽ · {username}")
        lines.append("\nНапиши, например: подтверди вывод 15 или отклони вывод 15: причина.")
        return AdminAssistantOutcome("\n".join(lines))

    review_match = re.search(r"(?:проверь|разбери|оцени|review)\s+(?:промпт|prompt)\s*#?\s*(\d+)", source, re.I)
    if review_match:
        prompt_id = int(review_match.group(1))
        prompt = await prompt_repository.get_prompt_by_id(session, prompt_id)
        if not prompt:
            return AdminAssistantOutcome(f"Промпт #{prompt_id} не найден.")
        review = await generate_prompt_moderation_review(
            prompt_id=prompt.id,
            title=prompt.title,
            description=prompt.description,
            prompt_text=prompt.prompt_text,
            tags=list(prompt.tags or []),
            model=prompt.model,
        )
        return AdminAssistantOutcome(f"Разбор промпта #{prompt.id} «{prompt.title}»:\n\n{review}")

    approve_prompt_match = re.search(r"(?:одобри|approve)\s+(?:промпт|prompt)\s*#?\s*(\d+)", source, re.I)
    if approve_prompt_match:
        prompt_id = int(approve_prompt_match.group(1))
        prompt = await prompt_repository.approve_prompt(session, prompt_id)
        if not prompt:
            return AdminAssistantOutcome(f"Промпт #{prompt_id} не найден.")
        author = await repo.get_user_by_id(session, prompt.author_id)
        if author:
            try:
                await bot.send_message(
                    author.tg_id,
                    f"🎉 Ваш промпт «<b>{prompt.title}</b>» опубликован в витрине.\n"
                    "Теперь пользователи могут запускать генерацию прямо из карточки.",
                )
            except Exception as exc:
                logger.warning("assistant moderator: failed to notify prompt author %s: %s", author.tg_id, exc)
        return AdminAssistantOutcome(f"Промпт #{prompt.id} «{prompt.title}» одобрен.")

    reject_prompt_match = re.search(r"(?:отклони|reject)\s+(?:промпт|prompt)\s*#?\s*(\d+)(.*)$", source, re.I)
    if reject_prompt_match:
        prompt_id = int(reject_prompt_match.group(1))
        reason = _clean_reason(reject_prompt_match.group(2))
        if not reason:
            return AdminAssistantOutcome("Для отклонения укажи причину. Пример: отклони промпт 42: спам и слишком мало смысла.")
        prompt = await prompt_repository.reject_prompt(session, prompt_id, reason)
        if not prompt:
            return AdminAssistantOutcome(f"Промпт #{prompt_id} не найден.")
        author = await repo.get_user_by_id(session, prompt.author_id)
        if author:
            try:
                await bot.send_message(
                    author.tg_id,
                    f"❌ Промпт «<b>{prompt.title}</b>» отклонён.\nПричина: {reason}",
                )
            except Exception as exc:
                logger.warning("assistant moderator: failed to notify rejected prompt author %s: %s", author.tg_id, exc)
        return AdminAssistantOutcome(f"Промпт #{prompt.id} «{prompt.title}» отклонён.\nПричина: {reason}")

    deactivate_prompt_match = re.search(r"(?:деактивируй|скрой|hide)\s+(?:промпт|prompt)\s*#?\s*(\d+)", source, re.I)
    if deactivate_prompt_match:
        prompt_id = int(deactivate_prompt_match.group(1))
        prompt = await prompt_repository.deactivate_prompt(session, prompt_id)
        if not prompt:
            return AdminAssistantOutcome(f"Промпт #{prompt_id} не найден.")
        author = await repo.get_user_by_id(session, prompt.author_id)
        if author:
            try:
                await bot.send_message(author.tg_id, f"⚠️ Ваш промпт «<b>{prompt.title}</b>» скрыт администратором.")
            except Exception as exc:
                logger.warning("assistant moderator: failed to notify deactivated prompt author %s: %s", author.tg_id, exc)
        return AdminAssistantOutcome(f"Промпт #{prompt.id} «{prompt.title}» деактивирован.")

    approve_withdrawal_match = re.search(r"(?:подтверди|одобри|approve)\s+(?:заявку\s+)?(?:на\s+)?вывод\s*#?\s*(\d+)", source, re.I)
    if approve_withdrawal_match:
        request_id = int(approve_withdrawal_match.group(1))
        try:
            view = await repo.set_withdrawal_status(
                session,
                request_id,
                status=WithdrawalStatus.approved,
                admin_tg_id=admin_tg_id,
            )
        except InsufficientReferralBalanceError as exc:
            return AdminAssistantOutcome(
                f"Не могу подтвердить вывод #{request_id}: у пользователя доступно только {exc.available_amount:.2f}₽ реферального баланса."
            )
        if not view:
            return AdminAssistantOutcome(f"Заявка на вывод #{request_id} уже обработана или не найдена.")
        req = view.request
        user = view.user
        try:
            await bot.send_message(
                user.tg_id,
                f"💸 Заявка на вывод #{req.id} подтверждена.\n"
                f"Сумма: <b>{req.amount_rub:.2f}₽</b>",
            )
        except Exception as exc:
            logger.warning("assistant moderator: failed to notify withdrawal approval user %s: %s", user.tg_id, exc)
        return AdminAssistantOutcome(f"Заявка на вывод #{req.id} подтверждена для {_user_title(user)}.")

    reject_withdrawal_match = re.search(r"(?:отклони|reject)\s+(?:заявку\s+)?(?:на\s+)?вывод\s*#?\s*(\d+)(.*)$", source, re.I)
    if reject_withdrawal_match:
        request_id = int(reject_withdrawal_match.group(1))
        reason = _clean_reason(reject_withdrawal_match.group(2))
        view = await repo.set_withdrawal_status(
            session,
            request_id,
            status=WithdrawalStatus.rejected,
            admin_tg_id=admin_tg_id,
            admin_note=reason,
        )
        if not view:
            return AdminAssistantOutcome(f"Заявка на вывод #{request_id} уже обработана или не найдена.")
        req = view.request
        user = view.user
        notify_text = (
            f"💸 Заявка на вывод #{req.id} отклонена.\n"
            f"Сумма: <b>{req.amount_rub:.2f}₽</b>"
        )
        if reason:
            notify_text += f"\nПричина: {reason}"
        try:
            await bot.send_message(user.tg_id, notify_text)
        except Exception as exc:
            logger.warning("assistant moderator: failed to notify withdrawal rejection user %s: %s", user.tg_id, exc)
        response = f"Заявка на вывод #{req.id} отклонена для {_user_title(user)}."
        if reason:
            response += f"\nПричина: {reason}"
        return AdminAssistantOutcome(response)

    add_credits_match = re.search(
        r"(?:начисли|добавь|выдай)\s+(-?\d+(?:[.,]\d+)?)\s*(?:💋|поцелу[йяев]*|кредит[а-я]*|credits?)?(?:\s+(?:пользователю\s+)?)?(@?[a-z0-9_]+|\d+)",
        source,
        re.I,
    )
    if add_credits_match:
        amount = _extract_amount(add_credits_match.group(1))
        token = add_credits_match.group(2)
        if amount is None:
            return AdminAssistantOutcome("Не понял сумму начисления. Пример: начисли 50 123456789.")
        user = await _resolve_user(session, token)
        if not user:
            return AdminAssistantOutcome(f"Пользователь {token} не найден.")
        new_balance = await repo.add_credits(session, user.id, amount)
        return AdminAssistantOutcome(
            f"Изменил баланс пользователя {_user_title(user)} на {amount:g} 💋.\n"
            f"Новый баланс: {new_balance:g} 💋"
        )

    unban_match = re.search(r"(?:разбань|unban)\s+(@?[a-z0-9_]+|\d+)", source, re.I)
    if unban_match:
        token = unban_match.group(1)
        user = await _resolve_user(session, token)
        if not user:
            return AdminAssistantOutcome(f"Пользователь {token} не найден.")
        ok = await repo.unban_user(session, user.tg_id)
        if not ok:
            return AdminAssistantOutcome(f"Не удалось разбанить {token}.")
        return AdminAssistantOutcome(f"Пользователь {_user_title(user)} разбанен.")

    ban_match = re.search(r"(?:забань|бан|ban)\s+(@?[a-z0-9_]+|\d+)", source, re.I)
    if ban_match:
        token = ban_match.group(1)
        user = await _resolve_user(session, token)
        if not user:
            return AdminAssistantOutcome(f"Пользователь {token} не найден.")
        ok = await repo.ban_user(session, user.tg_id)
        if not ok:
            return AdminAssistantOutcome(f"Не удалось забанить {token}.")
        return AdminAssistantOutcome(f"Пользователь {_user_title(user)} забанен.")

    user_lookup_match = re.search(r"(?:найди|покажи|пользователь|user)\s+(@?[a-z0-9_]+|\d+)", source, re.I)
    if user_lookup_match:
        token = user_lookup_match.group(1)
        user = await _resolve_user(session, token)
        if not user:
            return AdminAssistantOutcome(f"Пользователь {token} не найден.")
        snapshot = await repo.get_user_referral_balance_snapshot(session, user.id)
        available_ref = snapshot.available_to_withdraw if snapshot else float(user.referral_balance or 0.0)
        pending_ref = snapshot.pending_withdrawals if snapshot else 0.0
        return AdminAssistantOutcome(
            f"Пользователь: {_user_title(user)}\n"
            f"• Баланс: {user.credits:g} 💋\n"
            f"• Реферальный баланс: {float(user.referral_balance or 0.0):.2f}₽\n"
            f"• Доступно к выводу: {available_ref:.2f}₽\n"
            f"• В pending-выводах: {pending_ref:.2f}₽\n"
            f"• Подписка: {'активна' if user.is_subscribed else 'не активна'}\n"
            f"• Бан: {'да' if user.is_banned else 'нет'}"
        )

    return None
