from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from api.assistant_service import _generate_text_reply
from core.config import settings

logger = logging.getLogger(__name__)

READ_ONLY_ACTIONS = {
    "stats",
    "user_info",
    "maintenance_status",
    "list_promos",
    "bot_report",
    "analyze_logs",
    "research_ai",
    "clear_context",
    "help",
}
MUTATING_ACTIONS = {
    "add_credits",
    "deduct_credits",
    "ban_user",
    "unban_user",
    "maintenance_set",
    "create_promo",
    "deactivate_promo",
}
SENSITIVE_ACTIONS = {"export_users"}
ALL_ACTIONS = READ_ONLY_ACTIONS | MUTATING_ACTIONS | SENSITIVE_ACTIONS | {"unknown"}
CONFIRMATION_ACTIONS = MUTATING_ACTIONS | SENSITIVE_ACTIONS
MAX_ACTIONS = 6

LOG_PATHS = (
    Path("logs/bot.log"),
    Path("logs/bot_output.log"),
    Path("logs/watchdog.log"),
)

_KIE_BASE = "https://api.kie.ai"

_PLANNER_PROMPT = """Ты планировщик админ-действий Telegram-бота.
Верни строго один JSON без markdown.

Доступные action:
stats, user_info, add_credits, deduct_credits, ban_user, unban_user,
maintenance_status, maintenance_set, create_promo, deactivate_promo,
list_promos, export_users, bot_report, analyze_logs, research_ai,
clear_context, help, unknown.

Формат:
{"action":"stats","params":{},"actions":[],"summary":"Коротко","confidence":0.8}

Для сложных запросов верни actions со списком шагов.
Не придумывай ID, суммы, коды и даты.
Если данных не хватает, action=unknown.
Массовую рассылку не выполняй через ИИ.
Любые изменения данных только планируются: backend сам потребует подтверждение.
"""

_LOG_ANALYSIS_PROMPT = """Проанализируй логи Telegram-бота для админа.
Дай краткий отчёт: что происходит, ошибки/риски, вероятная причина, что проверить дальше.
Если критичных ошибок нет, скажи это явно.
Не раскрывай секреты, токены, API keys и Authorization-заголовки.
"""

_RESEARCH_PROMPT = """Сделай актуальный research для админа Telegram-бота генерации контента.
Найди новые/важные AI-модели, API и провайдеров для image/video generation.
Оцени полезность для продукта, качество, стоимость/риски, что стоит протестировать.
Отделяй проверенные факты от рекомендаций.
Итог держи кратким: факты, риски, рекомендации.
"""


async def plan_action(
    request: str,
    *,
    context: dict[str, Any] | None = None,
    use_llm: bool | None = None,
) -> dict[str, Any]:
    """Return a normalized, backend-validated action plan shape."""
    fallback = fallback_plan(request)
    if not _llm_enabled(use_llm):
        return fallback

    try:
        raw = await _call_planner_llm(request, context=context or {})
        payload = extract_json(raw)
        plan = normalize_plan(payload, request=request)
    except Exception as exc:
        logger.warning("admin_ai planner fallback: %s", exc)
        return fallback

    if plan.get("action") == "unknown" and fallback.get("action") != "unknown":
        return fallback
    return plan


async def _call_planner_llm(request: str, *, context: dict[str, Any]) -> str:
    safe_context = {
        "admin_id": context.get("admin_id"),
        "maintenance_mode": context.get("maintenance_mode"),
        "session_memory": _compact_session_memory(context.get("session_memory")),
    }
    content = (
        f"Запрос администратора:\n{request}\n\n"
        f"Контекст сессии JSON:\n{json.dumps(safe_context, ensure_ascii=False)}"
    )
    return await _generate_text_reply(
        [{"role": "user", "content": content}],
        system_prompt=_PLANNER_PROMPT,
    )


def extract_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("planner JSON must be an object")
    return parsed


def normalize_plan(payload: dict[str, Any], *, request: str = "") -> dict[str, Any]:
    actions_payload = payload.get("actions") or []
    actions: list[dict[str, Any]] = []
    if isinstance(actions_payload, list):
        actions = [
            _normalize_action(item)
            for item in actions_payload
            if isinstance(item, dict)
        ]

    raw_action = payload.get("action") or ("bot_report" if actions else "unknown")
    action = _clean_action(raw_action)
    params = sanitize_params(action, payload.get("params") or {})
    summary = _clean_summary(payload.get("summary")) or _default_summary(action, params)
    confidence = _clean_confidence(payload.get("confidence"))
    plan = {
        "action": action,
        "params": params,
        "actions": actions,
        "summary": summary,
        "confidence": confidence,
    }
    if request:
        plan["request"] = request[:1000]
    plan["requires_confirmation"] = plan_requires_confirmation(plan)
    return plan


def _normalize_action(payload: dict[str, Any]) -> dict[str, Any]:
    action = _clean_action(payload.get("action"))
    params = sanitize_params(action, payload.get("params") or {})
    item = {
        "action": action,
        "params": params,
        "summary": _clean_summary(payload.get("summary")) or _default_summary(action, params),
        "confidence": _clean_confidence(payload.get("confidence")),
        "actions": [],
    }
    item["requires_confirmation"] = action in CONFIRMATION_ACTIONS
    return item


def fallback_plan(request: str) -> dict[str, Any]:
    source = " ".join((request or "").strip().replace("ё", "е").split())
    normalized = source.lower()
    lines = _extract_lines_limit(normalized)

    if not normalized:
        return _unknown("Напиши задачу для ИИ-админа.", request=request)

    if "очист" in normalized and "контекст" in normalized:
        return _single("clear_context", {}, "Очистить контекст ИИ-админа", request=request)

    if any(word in normalized for word in ("помощь", "инструкц", "что умеешь", "что умееш")):
        return _single("help", {}, "Показать инструкцию ИИ-админа", request=request)

    if "рассыл" in normalized:
        return _unknown("Массовую рассылку через ИИ-админа не выполняю. Используй штатный раздел рассылки.", request=request)

    if "экспорт" in normalized and "польз" in normalized:
        return _single("export_users", {}, "Экспорт пользователей", request=request)

    if _looks_like_bot_report(normalized):
        return normalize_plan(
            {
                "action": "bot_report",
                "actions": [
                    {"action": "stats", "params": {}, "summary": "Собрать статистику"},
                    {"action": "maintenance_status", "params": {}, "summary": "Проверить техрежим"},
                    {"action": "list_promos", "params": {}, "summary": "Показать промокоды"},
                    {"action": "analyze_logs", "params": {"lines": lines or 250}, "summary": "Разобрать логи"},
                ],
                "summary": "Сделать отчёт по состоянию бота",
                "confidence": 0.9,
            },
            request=request,
        )

    if _looks_like_research(normalized):
        return _single("research_ai", {"query": source[:500]}, "Research по новым AI-инструментам", request=request)

    if (
        "лог" in normalized
        or "ошиб" in normalized
        or "webhook" in normalized
        or ("пад" in normalized and "генерац" in normalized)
        or ("failed" in normalized and "generation" in normalized)
    ):
        return _single("analyze_logs", {"lines": lines or 250}, "Проанализировать последние логи", request=request)

    add_match = re.search(
        r"(?:начисли|добавь|выдай)\s+(\d+(?:[.,]\d+)?)\s*(?:банан[а-я]*|кредит[а-я]*|💋|credits?)?(?:\s+(?:пользователю|юзеру|user)\s*)?(\d{3,20})",
        source,
        re.I,
    )
    if add_match:
        return _single(
            "add_credits",
            {"amount": _clean_number(add_match.group(1)), "telegram_id": int(add_match.group(2))},
            "Начислить баланс пользователю",
            request=request,
        )

    deduct_match = re.search(
        r"(?:спиши|сними|вычти)\s+(\d+(?:[.,]\d+)?)\s*(?:банан[а-я]*|кредит[а-я]*|💋|credits?)?(?:\s+(?:у|с|пользователя|юзера|user)\s*)?(\d{3,20})",
        source,
        re.I,
    )
    if deduct_match:
        return _single(
            "deduct_credits",
            {"amount": _clean_number(deduct_match.group(1)), "telegram_id": int(deduct_match.group(2))},
            "Списать баланс у пользователя",
            request=request,
        )

    unban_match = re.search(r"(?:разбань|разблокируй|unban)\s+(?:пользователя\s+)?(\d{3,20})", source, re.I)
    if unban_match:
        return _single("unban_user", {"telegram_id": int(unban_match.group(1))}, "Разбанить пользователя", request=request)

    ban_match = re.search(r"(?:забань|заблокируй|ban)\s+(?:пользователя\s+)?(\d{3,20})", source, re.I)
    if ban_match:
        return _single("ban_user", {"telegram_id": int(ban_match.group(1))}, "Забанить пользователя", request=request)

    user_match = re.search(r"(?:проверь|найди|покажи|посмотри)\s+(?:пользователя|юзера|user)?\s*(\d{3,20})", source, re.I)
    if user_match:
        return _single("user_info", {"telegram_id": int(user_match.group(1))}, "Показать пользователя", request=request)

    deactivate_promo_match = re.search(
        r"(?:отключи|деактивируй|выключи)\s+промокод\s+([A-Za-z0-9_-]{2,64})",
        source,
        re.I,
    )
    if deactivate_promo_match:
        return _single(
            "deactivate_promo",
            {"code": _clean_promo_code(deactivate_promo_match.group(1))},
            "Отключить промокод",
            request=request,
        )

    promo_plan = _fallback_create_promo(source)
    if promo_plan:
        promo_plan["request"] = request[:1000]
        return normalize_plan(promo_plan, request=request)

    if "промокод" in normalized or "промокоды" in normalized:
        return _single("list_promos", {}, "Показать промокоды", request=request)

    if "техрежим" in normalized or "техническ" in normalized:
        if any(word in normalized for word in ("включи", "включить", "on", "enable")):
            return _single("maintenance_set", {"enabled": True}, "Включить техрежим", request=request)
        if any(word in normalized for word in ("выключи", "отключи", "off", "disable")):
            return _single("maintenance_set", {"enabled": False}, "Выключить техрежим", request=request)
        return _single("maintenance_status", {}, "Показать статус техрежима", request=request)

    if "статист" in normalized or "выручк" in normalized or "генерац" in normalized:
        return _single("stats", {}, "Показать статистику", request=request)

    return _unknown("Не понял действие. Уточни задачу или открой инструкцию ИИ-админа.", request=request)


def _fallback_create_promo(source: str) -> dict[str, Any] | None:
    match = re.search(r"(?:создай|создать|сделай)\s+промокод\s+([A-Za-z0-9_-]{2,64})(.*)$", source, re.I)
    if not match:
        return None
    code = _clean_promo_code(match.group(1))
    tail = match.group(2) or ""
    limit_match = re.search(r"(?:лимит|max|uses?)\s+(\d+)", tail, re.I)
    value_match = re.search(
        r"(?:скидк[а-я]*|discount|банан[а-я]*|кредит[а-я]*|credits?|free|бесплатн[а-я]*)\s+(\d+(?:[.,]\d+)?)",
        tail,
        re.I,
    )
    if not code or not limit_match or not value_match:
        return {
            "action": "unknown",
            "params": {},
            "summary": "Для промокода нужны код, значение и лимит. Пример: создай промокод VIP20 скидка 20 лимит 100",
            "confidence": 0.4,
        }
    reward_type = "discount_percent"
    if re.search(r"банан|кредит|credits?", tail, re.I):
        reward_type = "credits"
    if re.search(r"free|бесплат", tail, re.I):
        reward_type = "free_generation"
    return {
        "action": "create_promo",
        "params": {
            "code": code,
            "reward_type": reward_type,
            "value": _clean_number(value_match.group(1)),
            "max_uses": int(limit_match.group(1)),
        },
        "summary": "Создать промокод",
        "confidence": 0.85,
    }


def validate_plan(plan: dict[str, Any]) -> str | None:
    action = _clean_action(plan.get("action"))
    if action == "unknown":
        return _clean_summary(plan.get("summary")) or "Не понял действие."
    if action not in ALL_ACTIONS:
        return "Действие не входит в allowlist ИИ-админа."

    actions = plan.get("actions") or []
    if actions:
        if not isinstance(actions, list):
            return "Некорректный список шагов."
        if len(actions) > MAX_ACTIONS:
            return f"Слишком длинная цепочка: максимум {MAX_ACTIONS} шагов."
        for item in actions:
            if not isinstance(item, dict):
                return "Некорректный шаг в плане."
            error = validate_plan(item)
            if error:
                return error
        if plan_requires_confirmation(plan) and plan.get("requires_confirmation") is not True:
            return "План содержит изменение данных и требует подтверждения."
        return None

    params = plan.get("params") or {}
    if not isinstance(params, dict):
        return "Некорректные параметры действия."

    if action in {"user_info", "add_credits", "deduct_credits", "ban_user", "unban_user"}:
        if not _coerce_positive_int(params.get("telegram_id")):
            return "Нужен Telegram ID пользователя."

    if action in {"add_credits", "deduct_credits"}:
        amount = _coerce_positive_float(params.get("amount"))
        if amount is None:
            return "Нужна положительная сумма."

    if action == "maintenance_set" and not isinstance(params.get("enabled"), bool):
        return "Нужно указать: включить или выключить техрежим."

    if action == "create_promo":
        if not params.get("code"):
            return "Нужен код промокода."
        reward_type = params.get("reward_type")
        if reward_type not in {"credits", "discount_percent", "discount_amount", "free_generation"}:
            return "Нужен тип промокода: credits, discount_percent, discount_amount или free_generation."
        value = _coerce_positive_float(params.get("value"))
        if value is None:
            return "Нужно значение промокода."
        if reward_type == "discount_percent" and value > 100:
            return "Процент скидки должен быть от 1 до 100."
        max_uses = params.get("max_uses")
        if max_uses is not None and not _coerce_positive_int(max_uses):
            return "Лимит промокода должен быть положительным целым числом."
        expires_at = params.get("expires_at")
        if expires_at and not _valid_date(str(expires_at)):
            return "Дата промокода должна быть в формате YYYY-MM-DD."

    if action == "deactivate_promo" and not params.get("code"):
        return "Нужен код промокода."

    if action == "analyze_logs":
        lines_value = _coerce_positive_int(params.get("lines") or 250)
        if lines_value is None or lines_value > 2000:
            return "Количество строк логов должно быть от 1 до 2000."

    if action in CONFIRMATION_ACTIONS and plan.get("requires_confirmation") is not True:
        return "Действие меняет данные и требует подтверждения."

    return None


def plan_requires_confirmation(plan: dict[str, Any]) -> bool:
    action = _clean_action(plan.get("action"))
    if action in CONFIRMATION_ACTIONS:
        return True
    return any(plan_requires_confirmation(item) for item in plan.get("actions") or [] if isinstance(item, dict))


def sanitize_params(action: str, params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        return {}
    action = _clean_action(action)
    cleaned: dict[str, Any] = {}

    telegram_id = _first_value(params, "telegram_id", "tg_id", "user_id", "id")
    if action in {"user_info", "add_credits", "deduct_credits", "ban_user", "unban_user"}:
        value = _coerce_positive_int(telegram_id)
        if value is not None:
            cleaned["telegram_id"] = value

    if action in {"add_credits", "deduct_credits"}:
        amount = _coerce_positive_float(_first_value(params, "amount", "credits", "value"))
        if amount is not None:
            cleaned["amount"] = _clean_number(amount)

    if action == "maintenance_set":
        enabled = _coerce_bool(_first_value(params, "enabled", "value", "state", "mode"))
        if enabled is not None:
            cleaned["enabled"] = enabled

    if action == "create_promo":
        code = _clean_promo_code(_first_value(params, "code", "promo_code"))
        if code:
            cleaned["code"] = code
        reward_type = _normalize_reward_type(_first_value(params, "reward_type", "type", "kind"))
        if reward_type:
            cleaned["reward_type"] = reward_type
        value = _coerce_positive_float(_first_value(params, "value", "amount", "discount", "credits"))
        if value is not None:
            cleaned["value"] = _clean_number(value)
        max_uses = _coerce_positive_int(_first_value(params, "max_uses", "limit", "max_redemptions"))
        if max_uses is not None:
            cleaned["max_uses"] = max_uses
        per_user_limit = _coerce_positive_int(params.get("per_user_limit"))
        if per_user_limit is not None:
            cleaned["per_user_limit"] = per_user_limit
        expires_at = params.get("expires_at") or params.get("valid_until")
        if expires_at and _valid_date(str(expires_at)):
            cleaned["expires_at"] = str(expires_at)

    if action == "deactivate_promo":
        code = _clean_promo_code(_first_value(params, "code", "promo_code"))
        if code:
            cleaned["code"] = code

    if action == "analyze_logs":
        lines = _coerce_positive_int(params.get("lines"))
        cleaned["lines"] = max(20, min(lines or 250, 2000))

    if action == "research_ai":
        query = str(_first_value(params, "query", "topic", "prompt") or "").strip()
        if query:
            cleaned["query"] = query[:500]

    if action == "export_users":
        limit = _coerce_positive_int(params.get("limit"))
        if limit:
            cleaned["limit"] = min(limit, 100000)

    return cleaned


async def analyze_logs(lines: int = 250, *, use_llm: bool | None = None) -> str:
    snapshot = collect_log_snapshot(lines=lines)
    fallback = format_log_fallback(snapshot)
    if not snapshot["files"]:
        return fallback
    if not _llm_enabled(use_llm):
        return fallback
    try:
        content = json.dumps(snapshot, ensure_ascii=False)
        return await _generate_text_reply(
            [{"role": "user", "content": content[:16000]}],
            system_prompt=_LOG_ANALYSIS_PROMPT,
        )
    except Exception as exc:
        logger.warning("admin_ai log analysis fallback: %s", exc)
        return fallback


def collect_log_snapshot(*, lines: int = 250) -> dict[str, Any]:
    limit = max(20, min(int(lines or 250), 2000))
    files: list[dict[str, Any]] = []
    metrics = {"ERROR": 0, "WARNING": 0, "WEBHOOK": 0, "RESTART": 0}
    highlights: list[str] = []

    for path in LOG_PATHS:
        if not path.exists() or not path.is_file():
            continue
        raw_lines = _tail_lines(path, limit)
        redacted_lines = [_redact_secrets(line) for line in raw_lines]
        for line in redacted_lines:
            upper = line.upper()
            for key in metrics:
                if key in upper:
                    metrics[key] += 1
            if "ERROR" in upper or "WARNING" in upper:
                highlights.append(f"{path.name}: {line[-500:]}")
        files.append(
            {
                "path": str(path),
                "lines": len(redacted_lines),
                "tail": redacted_lines[-80:],
            }
        )

    return {
        "requested_lines": limit,
        "files": files,
        "metrics": metrics,
        "highlights": highlights[-20:],
    }


def format_log_fallback(snapshot: dict[str, Any]) -> str:
    if not snapshot.get("files"):
        return "Логи не найдены в разрешённых файлах: " + ", ".join(str(path) for path in LOG_PATHS)
    metrics = snapshot.get("metrics") or {}
    lines = [
        "Анализ логов (fallback)",
        f"Файлы: {', '.join(item['path'] for item in snapshot.get('files', []))}",
        (
            "Счётчики: "
            f"ERROR={int(metrics.get('ERROR') or 0)}, "
            f"WARNING={int(metrics.get('WARNING') or 0)}, "
            f"WEBHOOK={int(metrics.get('WEBHOOK') or 0)}, "
            f"RESTART={int(metrics.get('RESTART') or 0)}"
        ),
    ]
    highlights = snapshot.get("highlights") or []
    if highlights:
        lines.append("\nПоследние ERROR/WARNING:")
        lines.extend(f"• {item}" for item in highlights[-12:])
    else:
        lines.append("\nКритичных ERROR/WARNING в хвосте логов не найдено.")
    return "\n".join(lines)


async def research_ai(query: str | None = None, *, use_llm: bool | None = None) -> str:
    if not _llm_enabled(use_llm) or not settings.KIE_AI_KEY:
        return (
            "Research сейчас недоступен: не настроен LLM с web search. "
            "Настрой KIE_AI_KEY или провайдера, совместимого с Responses web_search."
        )
    prompt = _RESEARCH_PROMPT
    if query:
        prompt += f"\n\nФокус запроса администратора: {query[:500]}"
    try:
        return await _call_kie_responses_with_web_search(prompt)
    except Exception as exc:
        logger.warning("admin_ai research web search failed: %s", exc)
        return "Не удалось выполнить web research прямо сейчас. Попробуй позже или проверь ключ LLM/web search."


async def _call_kie_responses_with_web_search(prompt: str) -> str:
    models = _kie_models()
    last_error: Exception | None = None
    for model in models:
        try:
            payload = {
                "model": model,
                "stream": False,
                "tools": [{"type": "web_search"}],
                "tool_choice": "auto",
                "input": [
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": prompt}],
                    }
                ],
                "reasoning": {"effort": "medium"},
            }
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{_KIE_BASE}/codex/v1/responses",
                    headers={
                        "Authorization": f"Bearer {settings.KIE_AI_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                return _extract_responses_text(resp.json())
        except Exception as exc:
            last_error = exc
            logger.warning("admin_ai research failed for %s: %s", model, exc)
    if last_error:
        raise last_error
    raise RuntimeError("No KIE models configured")


def _extract_responses_text(data: dict[str, Any]) -> str:
    if data.get("code") and data.get("code") != 200:
        raise RuntimeError(f"{data!r}")
    parts: list[str] = []
    for item in data.get("output") or []:
        if item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if content.get("type") == "output_text" and content.get("text"):
                parts.append(str(content["text"]).strip())
    text = "\n".join(part for part in parts if part).strip()
    if not text:
        raise RuntimeError(f"Responses output did not contain output_text: {data!r}")
    return text


def _single(action: str, params: dict[str, Any], summary: str, *, request: str) -> dict[str, Any]:
    return normalize_plan(
        {
            "action": action,
            "params": params,
            "actions": [],
            "summary": summary,
            "confidence": 0.9,
        },
        request=request,
    )


def _unknown(summary: str, *, request: str) -> dict[str, Any]:
    return normalize_plan(
        {
            "action": "unknown",
            "params": {},
            "actions": [],
            "summary": summary,
            "confidence": 0.2,
        },
        request=request,
    )


def _looks_like_bot_report(normalized: str) -> bool:
    return (
        "отчет по боту" in normalized
        or "отчёт по боту" in normalized
        or "сводк" in normalized and ("бот" in normalized or "состоян" in normalized)
        or "дай сводку по состоянию" in normalized
    )


def _looks_like_research(normalized: str) -> bool:
    return (
        ("найди" in normalized or "research" in normalized or "сравни" in normalized)
        and any(word in normalized for word in ("ии", "ai", "модел", "провайдер", "image-to-image", "video", "видео", "фото"))
    )


def _extract_lines_limit(normalized: str) -> int | None:
    match = re.search(r"(\d{2,4})\s*(?:строк|lines)", normalized)
    if not match:
        return None
    return max(20, min(int(match.group(1)), 2000))


def _clean_action(value: Any) -> str:
    action = str(value or "unknown").strip().lower()
    action = re.sub(r"[^a-z0-9_]", "", action)
    return action if action in ALL_ACTIONS else "unknown"


def _clean_summary(value: Any) -> str:
    return " ".join(str(value or "").strip().split())[:500]


def _clean_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(confidence, 1.0))


def _default_summary(action: str, params: dict[str, Any]) -> str:
    if action == "unknown":
        return "Не понял действие."
    if params:
        return f"Выполнить {action}"
    return f"Выполнить {action}"


def _first_value(params: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = params.get(key)
        if value not in (None, ""):
            return value
    return None


def _coerce_positive_int(value: Any) -> int | None:
    try:
        if isinstance(value, float) and not value.is_integer():
            return None
        text = str(value).strip()
        number = int(float(text))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _coerce_positive_float(value: Any) -> float | None:
    try:
        number = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on", "enable", "enabled", "вкл", "включи", "включить", "включен"}:
        return True
    if text in {"0", "false", "no", "off", "disable", "disabled", "выкл", "выключи", "отключи", "выключить", "отключить"}:
        return False
    return None


def _clean_number(value: Any) -> float | int:
    number = float(str(value).replace(",", "."))
    return int(number) if number.is_integer() else number


def _clean_promo_code(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", str(value or "").strip()).upper()[:64]


def _normalize_reward_type(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    mapping = {
        "credit": "credits",
        "credits": "credits",
        "banana": "credits",
        "bananas": "credits",
        "бананы": "credits",
        "банан": "credits",
        "discount": "discount_percent",
        "discount_percent": "discount_percent",
        "скидка": "discount_percent",
        "percent": "discount_percent",
        "discount_amount": "discount_amount",
        "rub": "discount_amount",
        "free": "free_generation",
        "free_generation": "free_generation",
    }
    return mapping.get(text)


def _valid_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _llm_enabled(use_llm: bool | None) -> bool:
    if use_llm is not None:
        return use_llm
    if str(getattr(settings, "ENV", "")).lower() == "test":
        return False
    return bool(getattr(settings, "KIE_AI_KEY", "") or getattr(settings, "COMET_API_KEY", ""))


def _compact_session_memory(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    compact: list[dict[str, Any]] = []
    for item in value[-6:]:
        if not isinstance(item, dict):
            continue
        compact.append(
            {
                "request": str(item.get("request") or "")[:300],
                "plan": item.get("plan"),
                "result": str(item.get("result") or "")[:500],
            }
        )
    return compact


def _tail_lines(path: Path, limit: int) -> list[str]:
    max_bytes = 512_000
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - max_bytes))
        data = handle.read()
    text = data.decode("utf-8", errors="replace")
    return text.splitlines()[-limit:]


def _redact_secrets(line: str) -> str:
    text = re.sub(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b", "[REDACTED_BOT_TOKEN]", line)
    text = re.sub(
        r"(?i)(authorization\s*[:=]\s*bearer\s+)[A-Za-z0-9._~+/=-]+",
        r"\1[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)((?:api[_-]?key|token|secret|password)\s*[:=]\s*)[A-Za-z0-9._~+/=-]{8,}",
        r"\1[REDACTED]",
        text,
    )
    return text


def _kie_models() -> list[str]:
    seen: set[str] = set()
    models: list[str] = []
    for model in (settings.KIE_ASSISTANT_MODEL, settings.KIE_ASSISTANT_FALLBACK):
        value = str(model or "").strip()
        if value and not value.startswith("claude-") and value not in seen:
            seen.add(value)
            models.append(value)
    return models
