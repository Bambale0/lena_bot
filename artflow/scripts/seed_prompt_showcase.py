from __future__ import annotations

import asyncio
import io
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import httpx
from sqlalchemy import select, update

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api.public_files import save_public_file
from db import repository as repo
from db.models import (
    Generation,
    GenerationStatus,
    GenerationType,
    ImageGenerationAction,
    PromptCategory,
    PromptStatus,
    User,
    UserPrompt,
)
from db.prompt_repository import create_prompt, get_prompt_by_id
from db.session import AsyncSessionLocal


SEED_AUTHOR_TG_ID = 9900001001
SEED_AUTHOR_USERNAME = "apix_showcase"
SUPPORTED_MODEL = "nano-banana-pro"
DEFAULT_ASPECT_RATIO = "16:9"
DEFAULT_QUALITY = "2K"
DEFAULT_COUNT = 1
POLLINATIONS_MODEL = "flux"
POLLINATIONS_SIZE = (1280, 720)
POLLINATION_TIMEOUT = httpx.Timeout(35.0, connect=12.0)
LEGACY_PROMPT_IDS_TO_DELETE = [1]


@dataclass(frozen=True)
class ShowcaseItem:
    key: str
    title: str
    description: str
    category: PromptCategory
    prompt_text: str
    tags: list[str]
    seed: int


SHOWCASE_ITEMS: list[ShowcaseItem] = [
    ShowcaseItem(
        key="best",
        title="Закатная магия для топовой обложки",
        description="Сочный вау-кадр для витрины и красивых обоев.",
        category=PromptCategory.art,
        prompt_text=(
            "Golden sunset over a futuristic coastal city, glowing clouds, shimmering water reflections, "
            "premium laptop wallpaper, breathtaking composition, ultra detailed, cinematic atmosphere"
        ),
        tags=["best"],
        seed=101,
    ),
    ShowcaseItem(
        key="best",
        title="Люксовый skyline для best prompts",
        description="Премиальная витринная сцена с ощущением дорогого визуала.",
        category=PromptCategory.art,
        prompt_text=(
            "Luxury skyline above the clouds, glowing horizon, elegant architecture, rich color depth, "
            "high-end wallpaper aesthetics, award winning composition"
        ),
        tags=["best"],
        seed=111,
    ),
    ShowcaseItem(
        key="characters",
        title="3D герой с ярким характером",
        description="Выразительный персонаж для карточек, постеров и историй.",
        category=PromptCategory.art,
        prompt_text=(
            "Expressive stylized 3D character, young inventor in a bright jacket holding a glowing gadget, "
            "confident pose, clean background, vibrant lighting, highly detailed character design"
        ),
        tags=["characters"],
        seed=102,
    ),
    ShowcaseItem(
        key="characters",
        title="Фэнтези-персонаж для коллекции",
        description="Харизматичный герой с сильным силуэтом и атмосферой приключения.",
        category=PromptCategory.art,
        prompt_text=(
            "Fantasy character portrait, determined young ranger with luminous cape and ornate bow, "
            "heroic stance, expressive face, detailed costume, stylized premium illustration"
        ),
        tags=["characters"],
        seed=112,
    ),
    ShowcaseItem(
        key="cyberpunk",
        title="Неоновый киберпанк мегаполис",
        description="Ночной город, дождь, неон и плотная атмосфера будущего.",
        category=PromptCategory.art,
        prompt_text=(
            "Cyberpunk city street at night, neon signs in the rain, reflective pavement, holograms, "
            "dense futuristic atmosphere, cinematic composition, richly detailed"
        ),
        tags=["cyberpunk"],
        seed=103,
    ),
    ShowcaseItem(
        key="cyberpunk",
        title="Киберпанк-байкер под неоном",
        description="Динамичная сцена будущего с дождём, скоростью и электрическим светом.",
        category=PromptCategory.art,
        prompt_text=(
            "Cyberpunk biker on a glowing street bike, rainy alley, neon reflections, holographic billboards, "
            "electric blue and magenta palette, cinematic action shot"
        ),
        tags=["cyberpunk"],
        seed=113,
    ),
    ShowcaseItem(
        key="realism",
        title="Фотореалистичный travel-кадр",
        description="Реалистичная сцена с мягким светом и живой фактурой.",
        category=PromptCategory.photo,
        prompt_text=(
            "Photorealistic travel scene, stylish woman on a European rooftop terrace at golden hour, "
            "natural skin texture, soft wind in hair, realistic lens depth, premium editorial photography"
        ),
        tags=["realism"],
        seed=104,
    ),
    ShowcaseItem(
        key="realism",
        title="Реалистичный lifestyle-портрет",
        description="Чистая коммерческая фотография с естественным светом и живой фактурой.",
        category=PromptCategory.photo,
        prompt_text=(
            "Photoreal lifestyle portrait, confident man in a beige coat near modern glass architecture, "
            "natural daylight, realistic skin texture, premium magazine photography"
        ),
        tags=["realism"],
        seed=114,
    ),
    ShowcaseItem(
        key="cinematic",
        title="Кинематографичный кадр на постер",
        description="Широкий драматичный план, будто кадр из фильма.",
        category=PromptCategory.art,
        prompt_text=(
            "Cinematic film still, lone explorer walking through monumental desert ruins, dramatic light rays, "
            "epic scale, anamorphic look, atmospheric haze, movie-poster composition"
        ),
        tags=["cinematic"],
        seed=105,
    ),
    ShowcaseItem(
        key="cinematic",
        title="Ночной фильм-нуар",
        description="Тёмный городской кадр с напряжением и киношной драмой.",
        category=PromptCategory.art,
        prompt_text=(
            "Cinematic noir scene, detective under a street lamp in a rainy city, smoke, dramatic shadows, "
            "film still, moody composition, theatrical lighting"
        ),
        tags=["cinematic"],
        seed=115,
    ),
    ShowcaseItem(
        key="nsfw",
        title="Смелая fashion-сцена",
        description="Эстетичная взрослая подача без откровенной наготы.",
        category=PromptCategory.photo,
        prompt_text=(
            "Luxury boudoir editorial, elegant adult woman in red silk robe, moody warm lighting, "
            "tasteful sensual pose, premium fashion photography, no explicit nudity"
        ),
        tags=["nsfw"],
        seed=106,
    ),
    ShowcaseItem(
        key="nsfw",
        title="Глянцевая boudoir-редакционка",
        description="Взрослая эстетика с дорогим светом и fashion-подачей.",
        category=PromptCategory.photo,
        prompt_text=(
            "Editorial boudoir scene, elegant adult woman in black satin dress on a velvet sofa, tasteful sensuality, "
            "luxury interior, glossy magazine style, no explicit nudity"
        ),
        tags=["nsfw"],
        seed=116,
    ),
    ShowcaseItem(
        key="music",
        title="Музыкальная обложка в synthwave-стиле",
        description="Яркий визуал для трека, альбома или музыкального поста.",
        category=PromptCategory.other,
        prompt_text=(
            "Album cover for a synthwave music release, singer under neon lights with headphones, "
            "retro-futuristic stage haze, bold typography space, high-energy color palette"
        ),
        tags=["music"],
        seed=107,
    ),
    ShowcaseItem(
        key="music",
        title="Обложка для инди-альбома",
        description="Атмосферный арт для музыкального релиза с местом под название трека.",
        category=PromptCategory.other,
        prompt_text=(
            "Indie album artwork, vocalist under stage spotlights with floating dust and backlit microphone, "
            "emotional concert mood, textured poster design, cover art composition"
        ),
        tags=["music"],
        seed=117,
    ),
]


def _font(size: int, *, bold: bool = False):
    from PIL import ImageFont

    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def _theme_palette(key: str) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    return {
        "best": ((247, 120, 76), (38, 56, 110), (255, 221, 150)),
        "characters": ((69, 120, 255), (255, 120, 168), (255, 235, 153)),
        "cyberpunk": ((255, 54, 162), (23, 27, 74), (56, 233, 255)),
        "realism": ((214, 170, 132), (94, 126, 160), (255, 245, 223)),
        "cinematic": ((201, 123, 52), (33, 23, 41), (245, 211, 108)),
        "nsfw": ((130, 24, 49), (32, 10, 19), (240, 185, 168)),
        "music": ((84, 43, 171), (23, 16, 66), (255, 106, 77)),
    }[key]


def _vertical_gradient(width: int, height: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    from PIL import Image

    image = Image.new("RGB", (width, height))
    pixels = image.load()
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = tuple(
            int(top[i] * (1.0 - ratio) + bottom[i] * ratio)
            for i in range(3)
        )
        for x in range(width):
            pixels[x, y] = color
    return image


def _draw_glow_circle(draw: ImageDraw.ImageDraw, center: tuple[int, int], radius: int, color: tuple[int, int, int, int]) -> None:
    x, y = center
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)


def _render_local_fallback(item: ShowcaseItem) -> str:
    from PIL import Image, ImageDraw, ImageFilter

    width, height = POLLINATIONS_SIZE
    top, bottom, accent = _theme_palette(item.key)
    image = _vertical_gradient(width, height, top, bottom).convert("RGBA")

    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    _draw_glow_circle(glow_draw, (int(width * 0.78), int(height * 0.22)), 160, (*accent, 120))
    _draw_glow_circle(glow_draw, (int(width * 0.18), int(height * 0.78)), 220, (*top, 60))
    glow = glow.filter(ImageFilter.GaussianBlur(60))
    image = Image.alpha_composite(image, glow)

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    title_font = _font(54, bold=True)
    body_font = _font(24)
    label_font = _font(28, bold=True)

    draw.rounded_rectangle((70, 70, width - 70, height - 70), radius=36, outline=(255, 255, 255, 80), width=2)
    draw.rounded_rectangle((90, 90, width - 90, height - 90), radius=30, fill=(8, 12, 24, 36))

    if item.key == "best":
        draw.rectangle((0, int(height * 0.62), width, height), fill=(24, 34, 68, 180))
        for i, h in enumerate([220, 280, 190, 310, 250, 330, 210, 290]):
            x = 90 + i * 140
            draw.rectangle((x, height - h, x + 90, height), fill=(17, 22, 38, 230))
    elif item.key == "characters":
        draw.ellipse((320, 170, 580, 430), fill=(255, 222, 176, 220))
        draw.rounded_rectangle((300, 370, 600, 640), radius=120, fill=(44, 74, 178, 220))
        draw.ellipse((525, 340, 635, 450), fill=(*accent, 220))
    elif item.key == "cyberpunk":
        for x in range(120, width - 120, 130):
            draw.rectangle((x, 230, x + 80, height - 110), fill=(18, 20, 32, 230))
            draw.rectangle((x + 18, 260, x + 30, 275), fill=(255, 84, 185, 220))
            draw.rectangle((x + 42, 310, x + 54, 325), fill=(90, 238, 255, 220))
        for x in range(110, width - 110, 36):
            draw.line((x, 130, x - 60, height), fill=(130, 220, 255, 40), width=2)
    elif item.key == "realism":
        draw.rectangle((0, int(height * 0.68), width, height), fill=(170, 133, 103, 170))
        draw.ellipse((220, 180, 460, 420), fill=(255, 224, 190, 220))
        draw.rounded_rectangle((180, 360, 520, 700), radius=120, fill=(232, 217, 203, 210))
        draw.line((650, 180, 1100, 180), fill=(255, 250, 240, 180), width=6)
        draw.line((720, 240, 1120, 240), fill=(255, 250, 240, 100), width=4)
    elif item.key == "cinematic":
        draw.polygon([(0, height), (220, 430), (400, height)], fill=(69, 44, 31, 230))
        draw.polygon([(260, height), (560, 320), (760, height)], fill=(95, 61, 38, 220))
        draw.polygon([(620, height), (920, 370), (width, height)], fill=(48, 31, 27, 230))
        draw.rectangle((610, 230, 690, 520), fill=(33, 20, 17, 220))
    elif item.key == "nsfw":
        draw.ellipse((320, 160, 520, 360), fill=(241, 190, 176, 215))
        draw.rounded_rectangle((280, 320, 560, 680), radius=140, fill=(138, 24, 59, 215))
        draw.polygon([(530, 350), (760, 250), (900, 420), (650, 540)], fill=(189, 35, 73, 170))
    elif item.key == "music":
        for i, h in enumerate([120, 220, 180, 270, 150, 240, 210, 160]):
            x = 180 + i * 90
            draw.rounded_rectangle((x, height - 170 - h, x + 48, height - 170), radius=16, fill=(*accent, 210))
        draw.arc((780, 210, 1080, 510), start=210, end=330, fill=(255, 255, 255, 200), width=18)
        draw.arc((840, 250, 1140, 550), start=210, end=330, fill=(255, 255, 255, 200), width=18)

    label = item.key.upper()
    draw.text((120, 118), label, font=label_font, fill=(255, 255, 255, 220))
    draw.text((120, 168), item.title, font=title_font, fill=(255, 255, 255, 255))
    draw.multiline_text(
        (120, 246),
        item.description + "\n\n" + item.prompt_text[:110] + "...",
        font=body_font,
        fill=(240, 240, 245, 220),
        spacing=8,
    )

    image = Image.alpha_composite(image, overlay).convert("RGB")
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=92)
    return save_public_file(output.getvalue(), "image/jpeg")


async def _ensure_seed_author() -> User:
    async with AsyncSessionLocal() as session:
        existing = await repo.get_user_by_tg_id(session, SEED_AUTHOR_TG_ID)
        if existing:
            return existing
        return await repo.create_user(
            session=session,
            tg_id=SEED_AUTHOR_TG_ID,
            username=SEED_AUTHOR_USERNAME,
            full_name="APIX Showcase",
            welcome_credits=1000,
        )


async def _delete_legacy_prompts() -> None:
    async with AsyncSessionLocal() as session:
        for prompt_id in LEGACY_PROMPT_IDS_TO_DELETE:
            prompt = await get_prompt_by_id(session, prompt_id)
            if not prompt:
                continue
            if prompt.preview_url or prompt.model or prompt.tags:
                continue
            await session.delete(prompt)
        await session.commit()


async def _generate_image(item: ShowcaseItem) -> str:
    width, height = POLLINATIONS_SIZE
    prompt_variants = [item.prompt_text, item.prompt_text[:180]]

    for attempt, prompt_variant in enumerate(prompt_variants, start=1):
        encoded_prompt = quote(prompt_variant, safe="")
        url = (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            f"?width={width}&height={height}&seed={item.seed + attempt - 1}&model={POLLINATIONS_MODEL}"
        )
        try:
            async with httpx.AsyncClient(timeout=POLLINATION_TIMEOUT, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                return save_public_file(response.content, response.headers.get("content-type"))
        except Exception:
            await asyncio.sleep(2)
    return _render_local_fallback(item)


async def _find_prompt(session, author_id: int, title: str) -> UserPrompt | None:
    result = await session.execute(
        select(UserPrompt)
        .where(UserPrompt.author_id == author_id, UserPrompt.title == title)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _find_generation(session, user_id: int, prompt_text: str) -> Generation | None:
    result = await session.execute(
        select(Generation)
        .where(
            Generation.user_id == user_id,
            Generation.gen_type == GenerationType.image,
            Generation.prompt == prompt_text,
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _upsert_prompt(author: User, item: ShowcaseItem, preview_url: str) -> UserPrompt:
    async with AsyncSessionLocal() as session:
        existing = await _find_prompt(session, author.id, item.title)
        if existing:
            await session.execute(
                update(UserPrompt)
                .where(UserPrompt.id == existing.id)
                .values(
                    description=item.description,
                    category=item.category,
                    prompt_text=item.prompt_text,
                    preview_url=preview_url,
                    model=SUPPORTED_MODEL,
                    tags=item.tags,
                    is_public=True,
                    status=PromptStatus.approved,
                    reject_reason=None,
                )
            )
            await session.commit()
            refreshed = await get_prompt_by_id(session, existing.id)
            if refreshed:
                return refreshed

        prompt = await create_prompt(
            session=session,
            author_id=author.id,
            title=item.title,
            description=item.description,
            category=item.category,
            prompt_text=item.prompt_text,
            preview_url=preview_url,
            model=SUPPORTED_MODEL,
            tags=item.tags,
            is_public=True,
        )
        await session.execute(
            update(UserPrompt)
            .where(UserPrompt.id == prompt.id)
            .values(status=PromptStatus.approved)
        )
        await session.commit()
        refreshed = await get_prompt_by_id(session, prompt.id)
        return refreshed or prompt


async def _upsert_feed_generation(author: User, item: ShowcaseItem, result_url: str) -> None:
    async with AsyncSessionLocal() as session:
        existing = await _find_generation(session, author.id, item.prompt_text)
        if existing:
            await session.execute(
                update(Generation)
                .where(Generation.id == existing.id)
                .values(
                    model=SUPPORTED_MODEL,
                    result_url=result_url,
                    is_public_feed=True,
                    status=GenerationStatus.done,
                    error_msg=None,
                )
            )
            await session.commit()
            return

        image_session = await repo.create_image_session(
            session=session,
            user_id=author.id,
            model=SUPPORTED_MODEL,
            mode="text",
            aspect_ratio=DEFAULT_ASPECT_RATIO,
            quality=DEFAULT_QUALITY,
            count=DEFAULT_COUNT,
            base_prompt=item.prompt_text,
            reference_file_id=None,
            reference_url=None,
        )
        generation = await repo.create_generation(
            session=session,
            user_id=author.id,
            model=SUPPORTED_MODEL,
            gen_type=GenerationType.image,
            prompt=item.prompt_text,
            credits_spent=0,
            image_session_id=image_session.id,
            parent_generation_id=None,
            action_type=ImageGenerationAction.initial,
        )
        await repo.finish_generation(session, generation.id, result_url)
        await repo.update_image_session_last_result(session, image_session.id, result_url, generation.id)


async def main() -> None:
    await _delete_legacy_prompts()
    author = await _ensure_seed_author()
    print(f"Seed author id={author.id} tg_id={author.tg_id}")
    success = 0
    failures: list[tuple[str, str]] = []
    for idx, item in enumerate(SHOWCASE_ITEMS, start=1):
        print(f"[{idx}/{len(SHOWCASE_ITEMS)}] {item.key}: generating image")
        try:
            preview_url = await _generate_image(item)
            prompt = await _upsert_prompt(author, item, preview_url)
            await _upsert_feed_generation(author, item, preview_url)
            success += 1
            print(f"  prompt_id={prompt.id} preview={preview_url}")
        except Exception as exc:
            failures.append((item.key, str(exc)))
            print(f"  failed={exc}")

    print("")
    print(f"Done: {success}/{len(SHOWCASE_ITEMS)}")
    for key, error in failures:
        print(f"  {key}: {error}")


if __name__ == "__main__":
    asyncio.run(main())
