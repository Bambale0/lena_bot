from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBAPP = ROOT / "webapp" / "src"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_uses_pre_category_home_full_runtime() -> None:
    main = read(WEBAPP / "main.jsx")
    assert 'import "./style.css";' in main
    assert "20260731-compact-feed-v3" in main
    assert "trend-category-home-v4" not in main
    assert "function Studio(" in main
    assert "function Feed(" in main
    assert "function Trends(" in main
    assert "function Music(" in main
    assert "function MidjourneyModule(" in main
    assert "function Profile(" in main
    assert "function Referrals(" in main
    assert "function Prompts(" in main
    assert "function AdminDashboard(" in main
    assert 'api("/trends?limit=80")' in main
    assert 'api("/models/music")' in main
    assert 'api("/public/midjourney")' in main
    assert 'api("/referrals")' in main
    assert "realtimeWsUrl" in main
    assert "generationFromRealtimeEvent" in main


def test_generation_payment_and_admin_contracts_are_kept() -> None:
    main = read(WEBAPP / "main.jsx")
    assert 'const endpoint = kind === "video" ? "/generate/video" : "/generate/image"' in main
    assert 'api("/generate/music"' in main
    assert 'api(`/feed/${genId}/remix`' in main
    assert 'api(`/generations/${genId}/share`' in main
    assert '"/topup/tbank"' in main
    assert '"/topup/stars"' in main
    assert '"/topup/crypto"' in main
    assert '"/topup/lava"' in main
    assert 'api("/admin/overview")' in main
    assert 'api(`/admin/users/${selectedUserId}/credits`' in main
    assert 'api(`/admin/users/${selectedUserId}/ban`' in main
    assert 'api(`/admin/withdrawals/${item.id}/review`' in main
    assert 'X-Telegram-Init-Data' in main


def test_concept_skin_is_layered_over_legacy_css() -> None:
    style = read(WEBAPP / "style.css")
    skin = read(WEBAPP / "legacy-concept.css")
    assert '@import "./style-legacy-base.css";' in style
    assert '@import "./legacy-concept.css";' in style
    assert (WEBAPP / "style-legacy-base.css").exists()
    assert "APIX legacy runtime concept skin" in skin
    assert "--concept-purple:#8b2cff" in skin
    assert "--concept-cyan:#00f0ff" in skin
    assert "--concept-pink:#ff4d90" in skin
    assert "--concept-gold:#ffd700" in skin
    assert ".feedCompactCard" in skin
    assert ".profileHero" in skin
    assert ".nav button.navCreate" in skin
    assert "env(safe-area-inset-bottom)" in skin
    assert "prefers-reduced-motion" in skin


def test_v4_and_v5_experimental_entrypoints_are_not_used() -> None:
    main = read(WEBAPP / "main.jsx")
    assert "./apix/AppV4.jsx" not in main
    assert "./apix-v5/App.jsx" not in main
    assert "apix.v4.css" not in main
    assert "apix-v5/styles" not in main
