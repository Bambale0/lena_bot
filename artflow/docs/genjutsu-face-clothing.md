# Genjutsu: face, clothing and number replacement

Telegram: Create → Genjutsu → 🎭 Замена лица / одежды.

1. Upload the original video (4–30 seconds).
2. Add 1–3 photos of the same person, or skip identity replacement.
3. Add an outfit photo, text, or a captioned photo, or skip.
4. Enter the exact number/digits, or keep the original.
5. Choose Seedance 2.5 resolution, 480p or 720p.
6. Review source, reference counts, requested changes, resolution and current ROX cost; confirm.

Back preserves the draft at every step. Skip removes the optional change explicitly. Cancel returns to Genjutsu. Each displayed keyboard is bound to its current draft confirmation. Existing Genjutsu motion/object tools retain their provider and controls; the new flow is independent of Trends and uses real `bytedance/seedance-2-5`.

`core/seedance_repeat_overrides.py` contains the shared deterministic role planner. Identity references are first (primary, then supporting), clothing is last. Duplicate identities are aligned with roles before deduplication; an image cannot simultaneously define face and clothes. The provider prompt makes the source video authoritative for motion/pose/camera/timing/scene, while editing only the selected attributes. Users never enter reference tokens.

`api/video_runtime_fixes.py` is the actual Seedance provider boundary. Explicit content-edit metadata takes precedence over legacy Identity Transfer control tokens, validates the real source URL and prepared reference count, builds role instructions and checks the final prompt length before createTask. It sends source video as `reference_video_urls`, ordered images as `reference_image_urls`, provider duration `-1`, adaptive geometry and selected resolution. No provider integration is duplicated.

Generation input_params store `flow_id=genjutsu_face_clothing`, `flow_version=1`, `seedance_content_edit` (number/clothing text), `seedance_reference_roles`, ordered `image_url`, `reference_video_url`, source-derived billing duration and resolution. Telegram history actions restore this exact original-input snapshot into confirmation without charging. Old identity generations without roles remain supported via their explicit identity control token; old content-edit repeats remove both stale identity token and FSM flag before sending clothing references.

Costs use the existing ModelCost resolution rates multiplied by the probed source duration (rounded up by existing edit billing logic). Quote is checked again before charging. Existing generation/refund transaction path handles failures; a rejected launch restores the draft with a new confirmation. No migrations or prices changed.

Scope: Telegram entry/FSM only as explicitly requested. Existing site and Mini App Seedance/Identity Transfer interfaces continue using the same provider primitives and pricing; no new UI entry was added there.

Verification uses mocked Telegram, database and createTask boundaries, including real video_service.generate_video; no paid generation is required. Visual similarity/identity quality depends on the provider and has not been established by unit tests or non-billable smoke.
