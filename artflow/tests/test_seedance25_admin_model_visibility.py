from __future__ import annotations

from pathlib import Path


def test_seedance25_model_registered_after_api_bootstrap():
    import api  # noqa: F401 - import side effects install provider adapters
    from api import kie_model_specs, video_service
    from api.seedance25_adapter import MODEL_KEY

    assert video_service.VideoModel(MODEL_KEY).value == MODEL_KEY
    spec = kie_model_specs.VIDEO_SPECS[MODEL_KEY]
    assert spec.model == MODEL_KEY
    assert spec.supported_modes == ("text", "image")
    assert spec.reference_field == "reference_image_urls"


def test_seedance25_miniapp_hook_is_installed_in_bootstrap():
    source = Path("api/__init__.py").read_text(encoding="utf-8")
    assert "install_seedance25_provider_support()" in source
    assert "install_seedance25_miniapp(module)" in source


def test_admin_model_visibility_is_not_public_admin_ids():
    backend = Path("api/admin_model_visibility.py").read_text(encoding="utf-8")
    frontend = Path("webapp/src/lib/admin-model-visibility.ts").read_text(encoding="utf-8")
    main = Path("webapp/src/main.tsx").read_text(encoding="utf-8")

    assert "/me/permissions" in backend
    assert "settings.ADMIN_IDS" in backend
    assert "ADMIN_IDS" not in frontend
    assert "html:not([data-apix-admin=\"true\"])" in frontend
    assert "installAdminModelVisibility()" in main
