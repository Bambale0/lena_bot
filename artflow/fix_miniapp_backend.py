from pathlib import Path
import re

# ── 1. Fix repository.create_image_session signature ──────────────────────────

p = Path("db/repository.py")
s = p.read_text(encoding="utf-8")

s = s.replace(
    "    reference_file_id: str | None,\n    reference_file_ids: list[str] | None = None,\n    reference_url: str | None = None,\n) -> ImageSession:",
    "    reference_file_id: str | None = None,\n    reference_file_ids: list[str] | None = None,\n    reference_url: str | None = None,\n) -> ImageSession:",
)

p.write_text(s, encoding="utf-8")


# ── 2. Fix miniapp auth: add auth_date TTL ────────────────────────────────────

p = Path("api/miniapp_auth.py")
s = p.read_text(encoding="utf-8")

if "import time" not in s:
    s = s.replace("import json\n", "import json\nimport time\n")

if "TELEGRAM_INIT_DATA_MAX_AGE_SECONDS" not in s:
    s = s.replace(
        "from db.session import get_session\n",
        "from db.session import get_session\n\n\nTELEGRAM_INIT_DATA_MAX_AGE_SECONDS = 7 * 24 * 60 * 60\n",
    )

if "Telegram initData expired" not in s:
    s = s.replace(
        "    if not hmac.compare_digest(computed_hash, received_hash):\n"
        "        raise HTTPException(status_code=401, detail=\"Invalid Telegram initData signature\")\n\n"
        "    raw_user = params.get(\"user\")\n",
        "    if not hmac.compare_digest(computed_hash, received_hash):\n"
        "        raise HTTPException(status_code=401, detail=\"Invalid Telegram initData signature\")\n\n"
        "    try:\n"
        "        auth_date = int(params.get(\"auth_date\", \"0\"))\n"
        "    except ValueError:\n"
        "        raise HTTPException(status_code=401, detail=\"Malformed auth_date in initData\")\n"
        "    if auth_date <= 0 or time.time() - auth_date > TELEGRAM_INIT_DATA_MAX_AGE_SECONDS:\n"
        "        raise HTTPException(status_code=401, detail=\"Telegram initData expired\")\n\n"
        "    raw_user = params.get(\"user\")\n",
    )

p.write_text(s, encoding="utf-8")


# ── 3. Fix miniapp routes: motion controls, remix schema, image session call ──

p = Path("api/miniapp_routes.py")
s = p.read_text(encoding="utf-8")

# Add motion_controls to ModelInfo
s = s.replace(
    "    resolutions: list[str] = []\n",
    "    resolutions: list[str] = []\n    motion_controls: list[str] = []\n",
)

# Add FeedRemixRequest after VideoGenRequest
if "class FeedRemixRequest" not in s:
    marker = (
        "class VideoGenRequest(BaseModel):\n"
        "    model: str\n"
        "    prompt: str = Field(..., min_length=1, max_length=4000)\n"
        "    mode: str = \"text\"                    # \"text\" | \"image\"\n"
        "    duration: int = Field(default=5, ge=2, le=30)\n"
        "    aspect_ratio: str | None = None\n"
        "    resolution: str | None = None\n"
        "    image_url: str | None = None\n"
        "    grok_mode: str = \"normal\"\n\n\n"
    )
    insert = marker + (
        "class FeedRemixRequest(BaseModel):\n"
        "    model: str\n"
        "    mode: str = \"text\"                    # \"text\" | \"image\"\n"
        "    duration: int = Field(default=5, ge=2, le=30)\n"
        "    aspect_ratio: str | None = None\n"
        "    resolution: str | None = None\n"
        "    image_url: str | None = None\n"
        "    grok_mode: str = \"normal\"\n"
        "    quality: str = \"basic\"\n"
        "    count: int = Field(default=1, ge=1, le=6)\n\n\n"
    )
    s = s.replace(marker, insert)

# Add motion_controls field in list_video_models response
s = s.replace(
    "            durations=caps.get(\"duration_options\", []),\n"
    "            resolutions=caps.get(\"resolutions\") or [],\n"
    "        ))",
    "            durations=caps.get(\"duration_options\", []),\n"
    "            resolutions=caps.get(\"resolutions\") or [],\n"
    "            motion_controls=caps.get(\"motion_controls\", []),\n"
    "        ))",
)

# Add reference_file_id=None to miniapp image session call
if "reference_file_id=None," not in s:
    s = s.replace(
        "        base_prompt=body.prompt,\n"
        "        reference_url=body.reference_url,\n",
        "        base_prompt=body.prompt,\n"
        "        reference_file_id=None,\n"
        "        reference_url=body.reference_url,\n",
    )

# Replace remix body type
s = s.replace(
    "    body: VideoGenRequest,\n",
    "    body: FeedRemixRequest,\n",
    1 if "body: FeedRemixRequest" not in s else 0
)

# The replace above may hit create_video_generation first if schema wasn't present.
# Ensure only remix endpoint uses FeedRemixRequest and video endpoint stays VideoGenRequest.
s = re.sub(
    r'(@router\.post\("/generate/video"[\s\S]*?async def create_video_generation\(\n\s+body: )FeedRemixRequest(,)',
    r'\1VideoGenRequest\2',
    s,
)
s = re.sub(
    r'(@router\.post\("/feed/\{gen_id\}/remix"[\s\S]*?async def remix_feed_post\(\n\s+gen_id: int,\n\s+body: )VideoGenRequest(,)',
    r'\1FeedRemixRequest\2',
    s,
)

# Fix image remix generate n=1 to n=body.count
s = s.replace(
    "                aspect_ratio=body.aspect_ratio, n=1,\n"
    "                quality=body.quality or \"basic\",\n",
    "                aspect_ratio=body.aspect_ratio, n=body.count,\n"
    "                quality=body.quality or \"basic\",\n",
)

p.write_text(s, encoding="utf-8")


# ── 4. Add motion controls to VIDEO_CAPS where possible ───────────────────────

p = Path("bot/keyboards/models.py")
if p.exists():
    s = p.read_text(encoding="utf-8")
    # Do not try to deeply parse. Add default helper near VIDEO_CAPS if missing.
    if "DEFAULT_MOTION_CONTROLS" not in s:
        s = s.replace(
            "VIDEO_CAPS",
            "DEFAULT_MOTION_CONTROLS = [\"auto\", \"pan_left\", \"pan_right\", \"zoom_in\", \"zoom_out\", \"orbit\", \"dolly_in\", \"dolly_out\", \"handheld\", \"cinematic\"]\n\nVIDEO_CAPS",
            1,
        )
    # The API also has fallback if caps has no motion_controls, so this is non-critical.
    p.write_text(s, encoding="utf-8")

print("OK: backend miniapp fixes applied")
