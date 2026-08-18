from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HANDLERS_INIT = ROOT / "bot" / "handlers" / "__init__.py"


def test_gemini_omni_router_is_registered_before_generic_video_references() -> None:
    source = HANDLERS_INIT.read_text(encoding="utf-8")
    omni = "_video_router.include_router(_gemini_omni_references.router)"
    generic = "_video_router.include_router(_video_references.router)"
    assert omni in source
    assert generic in source
    assert source.index(omni) < source.index(generic)
