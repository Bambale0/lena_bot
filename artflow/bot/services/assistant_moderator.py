from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from api.assistant_service import generate_prompt_moderation_review
from db import prompt_repository
from db import repository as repo
from db.models import User, WithdrawalStatus
from db.repository import InsufficientReferralBalanceError

logger = logging.getLogger(__name__)


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
            "• одобри промпт 42\n"
            "• отклони промпт 42: причина\n"
            "• проверь промпт 42\n"
            "• подтверди вывод 15\n"
            "• отклони вывод 15: причина"
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
