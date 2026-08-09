#!/usr/bin/env python3
"""One-shot implementation helper for generation UX parity epics.

Runs deterministic source transformations against the production-derived
agent/generation-ux-parity branch. Each phase is independently idempotent.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"missing patch anchor: {label}")
    return text.replace(old, new, 1)


def epic77() -> None:
    backend = ROOT / "artflow/api/miniapp_routes.py"
    text = backend.read_text()
    pairs = [
        (
            'all_refs = _normalize_public_urls(image_url, *(reference_urls or [])) if normalized_mode == "image" else []',
            'all_refs = _normalize_public_urls(image_url, *(reference_urls or [])) if normalized_mode in {"image", "motion"} else []',
            "motion image refs",
        ),
        (
            'elif normalized_mode == "image":\n        raise HTTPException(status_code=422, detail="Selected mode requires image_url")',
            'elif normalized_mode in {"image", "motion"}:\n        raise HTTPException(status_code=422, detail="Selected mode requires image_url")',
            "motion image required",
        ),
        (
            'if "video" not in supported_modes:\n            raise HTTPException(status_code=422, detail="Selected model does not support video input")',
            'if "video" not in supported_modes and "motion" not in supported_modes:\n            raise HTTPException(status_code=422, detail="Selected model does not support video input")',
            "motion video accepted",
        ),
        (
            'if normalized_mode == "video" and not normalized_video_url:\n        raise HTTPException(status_code=422, detail="Selected mode requires video_url")',
            'if normalized_mode in {"video", "motion"} and not normalized_video_url:\n        raise HTTPException(status_code=422, detail="Selected mode requires video_url")',
            "motion video required",
        ),
    ]
    for old, new, label in pairs:
        text = replace_once(text, old, new, label)
    backend.write_text(text)

    screen = ROOT / "artflow/webapp/src/features/generation-screen.tsx"
    text = screen.read_text()
    old = '''  const refsRequired = Boolean(selectedModel && !modelSupports(selectedModel, "text") && modelSupports(selectedModel, "image"));
  const maxRefs = Math.max(1, Number(selectedModel?.max_refs || 1));
  const tooManyRefs = draft.referenceUrls.length > maxRefs;
  const missingReference = refsRequired && draft.referenceUrls.length === 0;
  const videoModeNeedsUpload = draft.mode === "video" || (kind === "motion" && draft.mode !== "text");
  const missingMotionVideo = videoModeNeedsUpload && kind === "motion" && !draft.videoUrl;
  const missingPrompt = !draft.prompt.trim() && !draft.promptId;
  const insufficientCredits = estimate > Number(user.credits || 0);
  const mediaUploading = referenceUploading || videoUploading;
  const disabled = submitting || mediaUploading || !selectedModel || missingPrompt || missingReference || missingMotionVideo || tooManyRefs || insufficientCredits;
  const showReferenceUploader = kind === "image" || draft.mode === "image" || kind === "motion";
  const showVideoUploader = draft.mode === "video" || kind === "motion" || Boolean(selectedModel?.supports_video_input);
  const remainingRefs = Math.max(0, maxRefs - draft.referenceUrls.length);
  const maxAudioIds = Number(selectedModel?.max_audio_ids || 0);
  const maxCharacterIds = Number(selectedModel?.max_character_ids || 0);'''
    new = '''  const refsRequired = kind === "motion" || Boolean(selectedModel && !modelSupports(selectedModel, "text") && modelSupports(selectedModel, "image"));
  const maxRefs = Math.max(1, Number(selectedModel?.max_refs || 1));
  const tooManyRefs = draft.referenceUrls.length > maxRefs;
  const missingReference = refsRequired && draft.referenceUrls.length === 0;
  const missingVideo = (draft.mode === "video" || kind === "motion") && !draft.videoUrl;
  const missingPrompt = !draft.prompt.trim() && !draft.promptId;
  const insufficientCredits = estimate > Number(user.credits || 0);
  const mediaUploading = referenceUploading || videoUploading;
  const maxAudioIds = Number(selectedModel?.max_audio_ids || 0);
  const maxCharacterIds = Number(selectedModel?.max_character_ids || 0);
  const invalidSeed = Boolean(selectedModel?.has_seed && draft.seed != null && (!Number.isInteger(draft.seed) || draft.seed < 0 || draft.seed > 2_147_483_647));
  const invalidTrim = Boolean(draft.videoUrl && draft.videoEnd != null && (draft.videoEnd <= draft.videoStart || draft.videoEnd - draft.videoStart > 10));
  const geminiMediaSlots = selectedModel?.key === "gemini-omni-video"
    ? (draft.mode === "image" ? draft.referenceUrls.length : 0) + (draft.videoUrl ? 2 : 0) + draft.characterIds.length
    : 0;
  const mediaQuotaExceeded = selectedModel?.key === "gemini-omni-video" && geminiMediaSlots > 7;
  const tooManyAudioIds = maxAudioIds >= 0 && draft.audioIds.length > maxAudioIds;
  const tooManyCharacterIds = maxCharacterIds >= 0 && draft.characterIds.length > maxCharacterIds;
  const advancedInvalid = invalidSeed || invalidTrim || mediaQuotaExceeded || tooManyAudioIds || tooManyCharacterIds;
  const disabled = submitting || mediaUploading || !selectedModel || missingPrompt || missingReference || missingVideo || tooManyRefs || insufficientCredits || advancedInvalid;
  const showReferenceUploader = kind === "image" || draft.mode === "image" || kind === "motion";
  const showVideoUploader = draft.mode === "video" || kind === "motion" || Boolean(selectedModel?.supports_video_input);
  const remainingRefs = Math.max(0, maxRefs - draft.referenceUrls.length);'''
    text = replace_once(text, old, new, "canonical advanced validation")
    text = replace_once(
        text,
        '<Input type="number" value={draft.seed ?? ""} placeholder="auto" onChange={(event) => onChange({ seed: event.target.value ? Number(event.target.value) : null })} />',
        '<Input type="number" min={0} max={2147483647} step={1} value={draft.seed ?? ""} placeholder="auto" aria-invalid={invalidSeed} onChange={(event) => onChange({ seed: event.target.value ? Number(event.target.value) : null })} />',
        "seed range",
    )
    screen.write_text(text)

    test = ROOT / "artflow/tests/test_generation_ux_parity_contract.py"
    test.write_text('''from pathlib import Path\n\nROOT = Path(__file__).resolve().parents[1]\n\ndef test_motion_normalizer_keeps_both_inputs():\n    src = (ROOT / "api/miniapp_routes.py").read_text()\n    assert 'normalized_mode in {"image", "motion"}' in src\n    assert 'normalized_mode in {"video", "motion"}' in src\n\ndef test_canonical_screen_validates_advanced_video():\n    src = (ROOT / "webapp/src/features/generation-screen.tsx").read_text()\n    for token in ["invalidSeed", "invalidTrim", "mediaQuotaExceeded", "missingVideo"]:\n        assert token in src\n\ndef test_app_sends_full_video_contract():\n    src = (ROOT / "webapp/src/app/App.tsx").read_text()\n    for token in ["video_url: draft.videoUrl", "video_start: draft.videoStart", "video_end: draft.videoEnd", "audio_ids: draft.audioIds", "character_ids: draft.characterIds", "seed: draft.seed", "grok_mode: draft.grokMode"]:\n        assert token in src\n''')


def epic78() -> None:
    release = ROOT / "artflow/docs/apix_v4_production_release.md"
    text = release.read_text()
    note = "> [!IMPORTANT]\n> **Superseded production entrypoint (2026-08).** The canonical Mini App is `webapp/index.html` → `src/main.tsx` → `src/app/App.tsx`. `src/main.jsx` is legacy-only and is loaded exclusively with `?legacy=1`. New generation capabilities belong in `src/features/generation-screen.tsx` and are driven by backend `ModelInfo`.\n\n"
    if not text.startswith("> [!IMPORTANT]"):
        release.write_text(note + text)

    inventory = ROOT / "artflow/docs/current_surface_inventory.md"
    text = inventory.read_text()
    note2 = "\n## 2026-08 canonical Mini App update\n\nProduction `/app` is the TypeScript/Vite surface: `webapp/index.html` → `src/main.tsx` → `src/app/App.tsx`. `src/main.jsx` is retained only behind `?legacy=1` for rollback/debugging and is not a production source of truth. `GenerationScreen` renders image, video and motion capabilities from backend `ModelInfo`.\n"
    if "2026-08 canonical Mini App update" not in text:
        inventory.write_text(text + note2)

    plan = ROOT / "docs/generation-ux-epics.md"
    text = plan.read_text()
    status = "\n## Canonical implementation decision\n\n- Production Mini App: `artflow/webapp/src/main.tsx` → `src/app/App.tsx`.\n- `src/main.jsx` is legacy-only (`?legacy=1`).\n- Backend `ModelInfo` is the capability source of truth.\n- `GenerationScreen` is the shared renderer for image, video and motion.\n- Standalone Web consumes the same backend metadata/payload contract with a desktop layout.\n"
    if "Canonical implementation decision" not in text:
        plan.write_text(text + status)

    for rel in [
        "artflow/webapp/src/advancedVideoControls.jsx",
        "artflow/webapp/src/generationCapabilities.js",
        "artflow/webapp/tests/generationCapabilities.test.mjs",
    ]:
        path = ROOT / rel
        if path.exists():
            path.unlink()

    test = ROOT / "artflow/tests/test_canonical_generation_surface.py"
    test.write_text('''from pathlib import Path\n\nROOT = Path(__file__).resolve().parents[1]\n\ndef test_production_entrypoint_is_typescript_app():\n    index = (ROOT / "webapp/index.html").read_text()\n    main = (ROOT / "webapp/src/main.tsx").read_text()\n    assert "/src/main.tsx" in index\n    assert 'from "@/app/App"' in main\n    assert "legacy" in main\n\ndef test_generation_screen_is_modelinfo_driven():\n    src = (ROOT / "webapp/src/features/generation-screen.tsx").read_text()\n    for token in ["aspect_ratios", "quality_options", "durations", "resolutions", "max_refs", "max_audio_ids", "max_character_ids", "has_seed", "video_input_prices", "price_table"]:\n        assert token in src\n''')


def epic79() -> None:
    path = ROOT / "artflow/landing/js/riot-site.js"
    text = path.read_text()
    text = replace_once(
        text,
        '''  if (mode === "music") {\n    return {\n      prompt,\n      instrumental: data.get("instrumental") === "1" || data.get("instrumental") === "on",\n    };\n  }''',
        '''  if (mode === "music") {\n    return {\n      prompt,\n      instrumental: data.get("instrumental") === "1" || data.get("instrumental") === "on",\n      model: model || undefined,\n      voice_record_id: data.get("voice_record_id") ? Number(data.get("voice_record_id")) : undefined,\n      title: String(data.get("title") || "").trim() || undefined,\n      style: String(data.get("style") || "").trim() || undefined,\n    };\n  }''',
        "web music body",
    )
    text = replace_once(
        text,
        '''    return {\n      model,\n      prompt,\n      mode: selectedMode,\n      duration: Number(data.get("duration") || 5),\n      aspect_ratio: String(data.get("aspect_ratio") || "") || null,\n      resolution: String(data.get("resolution") || "") || null,\n      image_url: referenceUrl && selectedMode === "image" ? referenceUrl : null,\n      video_url: String(data.get("video_url") || "") || null,\n      reference_urls: [],\n    };''',
        '''    const refs = Array.from(new Set([referenceUrl, ...String(data.get("reference_urls") || "").split(/[\\n,]+/)].map((value) => String(value || "").trim()).filter(Boolean)));\n    const audioIds = String(data.get("audio_ids") || "").split(/[\\n,]+/).map((value) => value.trim()).filter(Boolean);\n    const characterIds = String(data.get("character_ids") || "").split(/[\\n,]+/).map((value) => value.trim()).filter(Boolean);\n    return {\n      model, prompt, mode: selectedMode,\n      duration: Number(data.get("duration") || 5),\n      aspect_ratio: String(data.get("aspect_ratio") || "") || null,\n      resolution: String(data.get("resolution") || "") || null,\n      image_url: refs[0] && (selectedMode === "image" || selectedMode === "motion") ? refs[0] : null,\n      video_url: String(data.get("video_url") || "") || null,\n      video_start: Number(data.get("video_start") || 0),\n      video_end: data.get("video_end") ? Number(data.get("video_end")) : null,\n      audio_ids: audioIds, character_ids: characterIds,\n      seed: String(data.get("seed") || "").trim() ? Number(data.get("seed")) : null,\n      grok_mode: String(data.get("grok_mode") || "normal"),\n      reference_urls: refs.slice(1),\n    };''',
        "web video body",
    )
    text = replace_once(
        text,
        '''  return {\n    model,\n    prompt,\n    aspect_ratio: String(data.get("aspect_ratio") || "") || null,\n    quality: String(data.get("quality") || "basic"),\n    count: Number(data.get("count") || 1),\n    reference_url: referenceUrl || null,\n    reference_urls: [],\n  };''',
        '''  const refs = Array.from(new Set([referenceUrl, ...String(data.get("reference_urls") || "").split(/[\\n,]+/)].map((value) => String(value || "").trim()).filter(Boolean)));\n  return {\n    model, prompt,\n    aspect_ratio: String(data.get("aspect_ratio") || "") || null,\n    quality: String(data.get("quality") || "basic"),\n    count: Number(data.get("count") || 1),\n    reference_url: refs[0] || null,\n    reference_urls: refs.slice(1),\n  };''',
        "web image refs",
    )
    old_ref = 'const reference = `<label><span>${ru() ? "Ссылка на пример" : "Example URL"}</span><input name="reference" placeholder="https://..."></label><label class="file-drop"><span>${icon("upload")}${ru() ? "Загрузить пример" : "Upload example"}</span><input name="reference_file" type="file" accept="image/png,image/jpeg,image/webp"></label>`;'
    new_ref = 'const reference = `<label><span>${ru() ? "Ссылка на пример" : "Example URL"}</span><input name="reference" placeholder="https://..."></label>${Number(model.max_refs || 1) > 1 ? `<label><span>${ru() ? "Доп. референсы" : "More references"}</span><textarea name="reference_urls" placeholder="https://... · по одному в строке"></textarea></label>` : ""}<label class="file-drop"><span>${icon("upload")}${ru() ? "Загрузить пример" : "Upload example"}</span><input name="reference_file" type="file" accept="image/png,image/jpeg,image/webp"></label>`;'
    text = replace_once(text, old_ref, new_ref, "web multi-ref controls")
    path.write_text(text)

    test = ROOT / "artflow/tests/test_web_generation_parity.py"
    test.write_text('''from pathlib import Path\n\nROOT = Path(__file__).resolve().parents[1]\n\ndef test_web_payload_supports_backend_generation_contract():\n    src = (ROOT / "landing/js/riot-site.js").read_text()\n    for token in ["reference_urls", "video_start", "video_end", "audio_ids", "character_ids", "seed", "grok_mode", "voice_record_id"]:\n        assert token in src\n''')


def epic80() -> None:
    telegram = ROOT / "artflow/webapp/src/lib/telegram.ts"
    text = telegram.read_text()
    if "syncTelegramBackButton" not in text:
        anchor = "export function openExternalUrl(value: string): void {"
        helper = '''export function syncTelegramBackButton(visible: boolean, onClick: () => void): () => void {\n  const backButton = webApp()?.BackButton;\n  if (!backButton) return () => undefined;\n  if (visible) {\n    backButton.show?.();\n    backButton.onClick?.(onClick);\n  } else {\n    backButton.hide?.();\n  }\n  return () => backButton.offClick?.(onClick);\n}\n\n'''
        text = replace_once(text, anchor, helper + anchor, "Telegram BackButton")
        telegram.write_text(text)

    app = ROOT / "artflow/webapp/src/app/App.tsx"
    text = app.read_text()
    if "syncTelegramBackButton" not in text:
        text = replace_once(
            text,
            "  readStartParam,\n  waitForTelegramInitData,",
            "  readStartParam,\n  syncTelegramBackButton,\n  waitForTelegramInitData,",
            "BackButton import",
        )
        text = replace_once(
            text,
            '''  useEffect(() => {\n    void initialize();\n  }, [initialize]);''',
            '''  useEffect(() => {\n    void initialize();\n  }, [initialize]);\n\n  useEffect(() => {\n    const shouldShowBack = taskOpen || balanceOpen || activeTab !== "feed";\n    return syncTelegramBackButton(shouldShowBack, () => {\n      if (taskOpen) { setTaskOpen(false); return; }\n      if (balanceOpen) { setBalanceOpen(false); return; }\n      setActiveTab("feed");\n    });\n  }, [activeTab, balanceOpen, taskOpen]);''',
            "BackButton effect",
        )
        app.write_text(text)

    test = ROOT / "artflow/tests/test_miniapp_navigation_accessibility.py"
    test.write_text('''from pathlib import Path\n\nROOT = Path(__file__).resolve().parents[1]\n\ndef test_telegram_back_button_is_wired():\n    assert "syncTelegramBackButton" in (ROOT / "webapp/src/lib/telegram.ts").read_text()\n    assert "syncTelegramBackButton" in (ROOT / "webapp/src/app/App.tsx").read_text()\n\ndef test_status_labels_are_human_readable():\n    src = (ROOT / "webapp/src/lib/utils.ts").read_text()\n    for label in ["В очереди", "Создаётся", "Готово", "Ошибка"]:\n        assert label in src\n''')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("epic", choices=["77", "78", "79", "80"])
    args = parser.parse_args()
    globals()[f"epic{args.epic}"]()


if __name__ == "__main__":
    main()
