# Gemini Omni Telegram mixed-media flow

## Production bug

The Seedance video-reference router was registered before the legacy video router and matched every `vid_mode:video:*` callback whose model exposed `supports_video_input`. Gemini Omni therefore entered `VideoGenFSM.video_upload`, but the upload handler itself accepted only Seedance model keys and returned silently for Gemini Omni. The screen told the user to press `Готово`, while the initial keyboard contained only `Главное меню`.

Telegram also commonly sends `.MOV` and full-resolution `.PNG` attachments as `Document` rather than `Video` / `Photo`, while the old Gemini flow only handled native Telegram video/photo updates.

## Fixed contract

The Gemini Omni Telegram flow now has its own router, registered before generic video-reference handlers. In video-input mode it accepts:

- exactly one MP4/MOV video, including Telegram `Document` uploads;
- JPG/JPEG/PNG/WEBP image references, including Telegram `Document` uploads;
- mixed video + image references in one generation;
- a visible `✅ Готово` action from the first media-collection screen;
- slot accounting before accepting media and before applying Character IDs.

The existing backend Gemini Omni builder remains the source of truth for provider payload construction. Telegram only collects and validates the inputs, then hands the state back to the normal parameter/prompt/generation lifecycle.

## Slot accounting

The existing APIX Gemini Omni contract is preserved:

- image: 1 slot;
- video: 2 slots;
- Character ID: 1 slot;
- total: at most 7 slots;
- at most one video.

Audio ID and seed stay on the normal parameter screen.

## Regression scenario

The regression test reproduces the user-reported sequence:

1. select Gemini Omni `video` mode;
2. send `IMG_5888.MOV` as a Telegram document;
3. send three `.PNG` files as Telegram documents;
4. verify the flow stores one video + three images and reports `5/7` slots;
5. press `Готово` and continue to the normal parameter screen.
