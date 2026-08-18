# Gemini Omni Telegram regression checklist

- The `Видео` mode opens a dedicated Gemini Omni collector, not the Seedance collector.
- `✅ Готово` is visible before the first upload.
- A `.MOV` sent as a Telegram document is accepted as the single video input.
- `.PNG`/`.JPG`/`.WEBP` documents and normal Telegram photos are accepted as image references.
- One video plus three images reports 5/7 media slots.
- Media that would exceed the 7-slot quota is rejected before provider submission.
- `Готово` requires a video in video-input mode and preserves all collected image references.
- Character ID entry is checked against the same media quota.
- The flow returns to the standard Gemini Omni parameter screen and then uses the existing generation lifecycle.
