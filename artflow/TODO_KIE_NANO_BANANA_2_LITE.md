# KIE Nano Banana 2 Lite Integration Plan

## Implementation Checklist

- [x] Analyze existing project structure
- [x] 1. Add `nano-banana-2-lite` model spec to `kie_model_specs.py`
- [x] 2. Add `NANO_BANANA_2_LITE` enum to `image_service.py` ImageModel
- [x] 3. Add model capabilities to `bot/keyboards/models.py` (IMAGE_CAPS, IMAGE_MODEL_DESC, _IMAGE_MODEL_ORDER)
- [x] 4. Add aspect ratios to `MODEL_ASPECT_RATIOS` in `image_service.py`
- [x] 5. Add `KIE_WEBHOOK_HMAC_KEY` config to `core/config.py`
- [x] 6. Create `bot/services/kie_market_service.py` — full KIE Market service
- [x] 7. Update `main.py` — HMAC webhook verification already exists via `kie_webhook.py` + `_verify_kie_webhook_secret`
- [x] 8. Add "🔥 NEW" badge to model display name in seed data
- [x] 9. Add weekly promo button to main menu keyboard
- [x] 10. Verify all changes are consistent

## Files Modified

1. **`api/kie_model_specs.py`** — Added `nano-banana-2-lite` spec with `image_urls` reference field, `auto` aspect ratio default
2. **`api/image_service.py`** — Added `NANO_BANANA_2_LITE` enum, aspect ratios, quality handling in `_build_input`
3. **`bot/keyboards/models.py`** — Added IMAGE_CAPS entry, description with 🔥 badge, ordering position
4. **`core/config.py`** — Added `KIE_WEBHOOK_HMAC_KEY` setting
5. **`bot/services/kie_market_service.py`** — New file: full KIE Market adapter
6. **`db/seed.py`** — Added seed entry with 🔥 badge, 1.0 credit cost
7. **`bot/keyboards/main_menu.py`** — Added weekly promo button for Nano Banana 2 Lite

## New Service File

**`bot/services/kie_market_service.py`** implements:
- `create_task()` — create generation task via KIE Market flow
- `get_task_details()` — get task status/result
- `parse_result_urls()` — extract resultUrls from response
- `verify_webhook_signature()` — HMAC-SHA256 verification
- `upload_file_base64()` / `upload_file_stream()` / `upload_file_url()` — file upload
- `get_remaining_credits()` — check credit balance
- `get_download_url()` — get temporary download link
- `build_create_task_payload()` — build payload without API call
- `is_kie_market_model()` — check if model uses Market flow