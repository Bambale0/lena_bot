from __future__ import annotations

import argparse
import asyncio
import mimetypes
import secrets
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import delete, select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api import kieai_client
from api.image_service import ImageModel, generate_image, poll_kieai_status
from api.public_files import ensure_public_image_url
from bot.handlers.image_gen import _supports_img2img
from bot.handlers.marketplace import (
    DEFAULT_PROMPT_MODEL,
    _default_count_for_model,
    _default_quality_for_model,
)
from db import repository as repo
from db.models import (
    Generation,
    GenerationType,
    ImageGenerationAction,
    ImageSession,
    PromptStatus,
    User,
    UserPrompt,
)
from db.prompt_repository import use_prompt
from db.session import AsyncSessionLocal


@dataclass
class PromptRunResult:
    prompt_id: int
    title: str
    model: str
    mode: str
    status: str
    result_url: str | None = None
    saved_path: str | None = None
    task_id: str | None = None
    details: str | None = None


async def _poll_result_url(task_id: str, timeout_seconds: int, interval_seconds: int) -> str:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        result_url = await poll_kieai_status(task_id)
        if result_url:
            return result_url
        await asyncio.sleep(interval_seconds)
    raise TimeoutError(f"Timed out waiting for task {task_id} after {timeout_seconds}s")


def _guess_extension(url: str, content_type: str | None) -> str:
    from_url = Path(url.split("?", 1)[0]).suffix.lower()
    if from_url in {".jpg", ".jpeg", ".png", ".webp"}:
        return from_url
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";", 1)[0].strip())
        if guessed:
            return ".jpg" if guessed == ".jpe" else guessed
    return ".png"


async def _download_result(url: str, out_path: Path) -> None:
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        ext = _guess_extension(url, response.headers.get("content-type"))
        final_path = out_path.with_suffix(ext)
        final_path.write_bytes(response.content)


async def _create_temp_user() -> User:
    async with AsyncSessionLocal() as session:
        user = await repo.create_user(
            session=session,
            tg_id=int(f"9{datetime.now(timezone.utc).strftime('%m%d%H%M%S')}"),
            username=f"chaincheck_{secrets.token_hex(4)}",
            full_name="Prompt Library Chain Check",
            welcome_credits=500,
        )
        return user


async def _cleanup_temp_user(user_id: int) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Generation).where(Generation.user_id == user_id))
        await session.execute(delete(ImageSession).where(ImageSession.user_id == user_id))
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


async def _load_prompts() -> list[UserPrompt]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserPrompt)
            .where(
                UserPrompt.status == PromptStatus.approved,
                UserPrompt.is_public.is_(True),
            )
            .order_by(UserPrompt.id)
        )
        return list(result.scalars().all())


async def _run_prompt(
    prompt: UserPrompt,
    *,
    user_id: int,
    mutate_marketplace: bool,
    out_dir: Path,
    timeout_seconds: int,
    interval_seconds: int,
) -> PromptRunResult:
    model_key = prompt.model or DEFAULT_PROMPT_MODEL
    quality = _default_quality_for_model(model_key)
    count = _default_count_for_model(model_key)
    preview_url = ensure_public_image_url(prompt.preview_url)
    mode = "image" if preview_url and _supports_img2img(model_key) else "text"
    details: list[str] = []

    if prompt.model is None:
        details.append("model fallback -> DEFAULT_PROMPT_MODEL")
    if not prompt.preview_url:
        details.append("preview missing")
    elif mode == "text":
        details.append("preview present but model runs in text mode")

    async with AsyncSessionLocal() as session:
        model_cost = await repo.get_model_cost(session, model_key)
        if not model_cost:
            return PromptRunResult(
                prompt_id=prompt.id,
                title=prompt.title,
                model=model_key,
                mode=mode,
                status="failed",
                details="model cost not found",
            )

        if mutate_marketplace:
            await use_prompt(session, prompt.id, user_id, credits_spent=model_cost.credits)

        image_session = await repo.create_image_session(
            session=session,
            user_id=user_id,
            model=model_key,
            mode=mode,
            aspect_ratio=None,
            quality=quality,
            count=count,
            base_prompt=prompt.prompt_text,
            reference_file_id=None,
            reference_url=preview_url if mode == "image" else None,
        )

        ok = await repo.spend_credits(session, user_id, model_cost.credits)
        if not ok:
            return PromptRunResult(
                prompt_id=prompt.id,
                title=prompt.title,
                model=model_key,
                mode=mode,
                status="failed",
                details="not enough credits on temp user",
            )

        generation = await repo.create_generation(
            session=session,
            user_id=user_id,
            model=model_key,
            gen_type=GenerationType.image,
            prompt=prompt.prompt_text,
            credits_spent=model_cost.credits,
            image_session_id=image_session.id,
            action_type=ImageGenerationAction.initial,
        )
        await repo.update_image_session_last_prompt(session, image_session.id, prompt.prompt_text)

        try:
            result = await generate_image(
                ImageModel(model_key),
                prompt.prompt_text,
                image_url=preview_url if mode == "image" else None,
                aspect_ratio=image_session.aspect_ratio,
                n=image_session.count,
                quality=image_session.quality,
                callback_url=None,
            )
            await repo.update_generation_task(session, generation.id, result.task_id or "")
            result_url = await _poll_result_url(result.task_id or "", timeout_seconds, interval_seconds)
            await repo.finish_generation(session, generation.id, result_url)
            await repo.update_image_session_last_result(session, image_session.id, result_url, generation.id)
        except Exception as exc:
            await repo.fail_generation(session, generation.id, str(exc))
            await repo.add_credits(session, user_id, model_cost.credits)
            return PromptRunResult(
                prompt_id=prompt.id,
                title=prompt.title,
                model=model_key,
                mode=mode,
                status="failed",
                task_id=generation.task_id,
                details=str(exc),
            )

    out_path = out_dir / f"prompt_{prompt.id}"
    await _download_result(result_url, out_path)
    actual_path = next(out_dir.glob(f"prompt_{prompt.id}.*"))
    return PromptRunResult(
        prompt_id=prompt.id,
        title=prompt.title,
        model=model_key,
        mode=mode,
        status="ok",
        result_url=result_url,
        saved_path=str(actual_path),
        task_id=result.task_id,
        details="; ".join(details) if details else "exact prompt settings",
    )


async def _amain(args: argparse.Namespace) -> int:
    prompts = await _load_prompts()
    if not prompts:
        print("No approved public prompts found in library.")
        return 1

    run_dir = Path(args.output_dir) / datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    temp_user = await _create_temp_user()

    print(f"Approved prompts: {len(prompts)}")
    print(f"Artifacts dir: {run_dir}")
    print(f"Temp user id: {temp_user.id}")
    print("")

    results: list[PromptRunResult] = []
    try:
        for idx, prompt in enumerate(prompts, start=1):
            print(f"[{idx}/{len(prompts)}] prompt_id={prompt.id} title={prompt.title!r}")
            result = await _run_prompt(
                prompt,
                user_id=temp_user.id,
                mutate_marketplace=args.mutate_marketplace,
                out_dir=run_dir,
                timeout_seconds=args.timeout_seconds,
                interval_seconds=args.interval_seconds,
            )
            results.append(result)
            print(f"  -> {result.status} | model={result.model} | mode={result.mode}")
            if result.saved_path:
                print(f"  -> saved={result.saved_path}")
            if result.details:
                print(f"  -> details={result.details}")
            if result.result_url:
                print(f"  -> url={result.result_url}")
            print("")
    finally:
        if args.cleanup_temp_user:
            await _cleanup_temp_user(temp_user.id)
            print(f"Temp user {temp_user.id} cleaned up.")
            print("")
        await kieai_client.close_client()

    ok_count = sum(1 for item in results if item.status == "ok")
    print("Summary")
    print(f"  success={ok_count}/{len(results)}")
    for item in results:
        print(
            f"  prompt_id={item.prompt_id} status={item.status} model={item.model} "
            f"saved={item.saved_path or '-'} details={item.details or '-'}"
        )
    return 0 if ok_count == len(results) else 2


def main() -> None:
    parser = argparse.ArgumentParser(description="Check prompt library generation chain.")
    parser.add_argument(
        "--output-dir",
        default="static/prompt_library_checks",
        help="Directory for generated images.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=600,
        help="Max wait time per generation task.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=10,
        help="Polling interval for task status.",
    )
    parser.add_argument(
        "--mutate-marketplace",
        action="store_true",
        help="Call use_prompt() and update marketplace usage counters.",
    )
    parser.add_argument(
        "--keep-temp-user",
        dest="cleanup_temp_user",
        action="store_false",
        help="Keep temporary user and generated DB records for debugging.",
    )
    parser.set_defaults(cleanup_temp_user=True)
    raise SystemExit(asyncio.run(_amain(parser.parse_args())))


if __name__ == "__main__":
    main()
