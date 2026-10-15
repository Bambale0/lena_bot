# APIX audit remediation: verified slice and remaining blockers

Baseline: `1f64429dd28c26bea542b145e77a27fd9e6dc4e8`. Branch: `fix/audit-contracts-20261016`.

This is a partial remediation, not closure of the full [original audit](2026-10-16-full-project.md). No live paid generation, customer refund, balance adjustment or production database inspection was performed. Payment execution and pricing are unchanged.

## Finding status

| Finding | Status in this branch | Evidence / boundary |
|---|---|---|
| P1 T-Bank/Tribute refund transaction boundaries | OPEN | Separate unshipped draft reproduced rollback failures on disposable PostgreSQL. Its initial full-refund tests passed, but subsequent financial changes were blocked before execution; no draft payment code is included here. |
| P1 partial refunds and late payment events | OPEN | Partial, stale, concurrent referral and reordered event cases remain unresolved. Do not interpret logging-only changes in callbacks as a payment fix. |
| P1 bot photo-trend missing reference | FIXED, release pending | All bot trend callbacks open the shared Mini App runner. No direct marketplace generation or charge happens in the callback; four tests cover image/video navigation, prompt secrecy and unpublished templates. Existing shared runner owns signed assets, checkout and idempotency. Mocked-browser photo and video bot deep links both open only the shared runner, perform no generic prepare/generation request, and send one asset/quote/idempotency request after photo upload. No paid end-to-end call performed. |
| P2 full historical pytest | OPEN | Pinned-environment full run: 3305 passed, 47 failed, 13 skipped. The original report used a different run with 44 failures; the difference has not been fully classified. No failing historical tests were disabled or changed to accept incorrect behavior. |
| P2 full Ruff | FIXED, release pending | All original 27 findings plus new import-order findings fixed with safe Ruff fixes. Full `ruff check .` passes; backend CI now checks the entire application rather than selected files. |
| P2 callback log privacy | FIXED, release pending | Raw callback bodies/media URLs removed from affected callbacks and delivery warnings. Exceptions log their class, not body/traceback. Structured anomaly helper allowlists identifiers. HTTP, static-source and malicious-identifier regressions added; callback/payment subset: 47 passed. Untrusted task identifiers cannot inject a URL into diagnostics; DB lookup inputs remain unchanged. |
| P2 Tribute product mapping | OPEN | Static business mapping remains unchanged; typed audited admin configuration still required. No migration is included in this slice. |
| P2 provider exposure disagreement | FIXED, release pending | Public exposure derives from the operation registry. Catalog, JSON and Markdown consistently show 98 registered contracts. Nonbillable reads do not require a paid smoke scenario. Structural readiness is NOT proof of successful live provider generation. |
| P2 OpenAPI custom auth metadata | FIXED, release pending | Existing dependency graph documents Telegram header, web token and website cookie alternatives. Public prompt reads stay optionally authenticated; admin operations declare role/403. Runtime auth checks are unchanged. Health operation IDs remain unique. |
| Documentation drift | UPDATED for this slice | Generated OpenAPI (193 paths), provider dashboard, trend guide and this explicit open-item matrix. Original audit retained as historical evidence. |

## Verification performed locally

- New bot navigation, callback privacy and exposure tests pass; auth metadata plus existing auth tests pass.
- Maintained backend PR gate and bot-navigation suite pass locally; environment-dependent tests were skipped. GitHub CI must exercise its own disposable services before merging.
- Full Ruff and compileall pass. Provider inventory/readiness and generated dashboard checks pass without paid requests.
- Frontend: 114 unit tests passed; typecheck/build and 2 direct-link browser scenarios passed. Two independent OpenAPI exports matched byte-for-byte. Provider dry smoke manifest validation passed without execution.
- Full historical test suite remains red. The incomplete financial worktree is excluded from this branch and must not be deployed.
- Some further investigation and test-update tool calls were also blocked before execution; those proposed changes were not retried or included.

## Remaining full-suite failures (pinned local run)

Names below are recorded from the actual JUnit output; they are not all proven production defects. Review current UI/provider contracts and test isolation before changing expectations.

- `tests.test_apix_v4_production_miniapp::test_v4_entrypoint_is_clean_and_does_not_import_legacy_layers`
- `tests.test_comet_fallback::test_image_service_uses_comet_fallback_after_kie_create_error`
- `tests.test_comet_fallback::test_video_service_uses_comet_fallback_after_kie_create_error`
- `tests.test_feed_first_relevance::test_vite_build_opens_feed_first_and_keeps_trends_available`
- `tests.test_feed_pinterest_ui::test_initial_feed_is_limited_and_build_id_is_bumped`
- `tests.test_image_gen_references::test_model_selection_opens_task_first_composer_for_any_model`
- `tests.test_image_service::test_normalize_quality_for_aspect_ratio_downgrades_square_4k`
- `tests.test_image_service::test_build_input_uses_2k_for_square_4k_request`
- `tests.test_keyboards_and_ui::test_main_menu_keyboard_keeps_core_buttons`
- `tests.test_keyboards_and_ui::test_main_menus_show_webapp_button_at_top`
- `tests.test_keyboards_and_ui::test_main_menu_keyboard_uses_public_web_url`
- `tests.test_keyboards_and_ui::test_render_main_menu_uses_public_web_url`
- `tests.test_keyboards_and_ui::test_render_main_menu_active_session_text`
- `tests.test_keyboards_and_ui::test_render_main_menu_force_main_text_even_with_active_session`
- `tests.test_keyboards_and_ui::test_prompt_use_model_kb_reference_only_filters_text_models`
- `tests.test_keyboards_and_ui::test_help_text_explains_settings_plainly`
- `tests.test_middlewares::test_auth_middleware_late_binds_referral_for_existing_user_without_referrer`
- `tests.test_middlewares::test_auth_middleware_binds_referral_from_shared_trend_payload`
- `tests.test_middlewares::test_auth_middleware_late_bind_rejects_descendant_referrer`
- `tests.test_model_family_routing::test_native_multimodal_models_keep_one_provider_key`
- `tests.test_trend_category_home::test_frontend_is_category_first_and_keeps_studio_as_action`
- `tests.test_trend_run_reliability::test_concurrent_trend_claims_admit_only_one_paid_request`
- `tests.test_trend_run_reliability::test_pre_submit_rejection_releases_claim_for_retry`
- `tests.test_veo_capabilities::test_veo_quality_capabilities_match_generation_endpoint`
- `tests.test_veo_capabilities::test_veo_fast_and_lite_expose_material_reference_mode`
- `tests.test_video_reference_support::test_seedance_payload_uses_reference_video_urls`
- `tests.test_web_api_contract::test_web_referrals_return_site_link`
- `tests.test_web_api_contract::test_contact_auth_request_rate_limits_by_contact`
- `tests.test_web_api_contract::test_contact_auth_verify_rate_limits_after_repeated_failures`
- `tests.test_webapp_routes::test_photo_prompt_rejects_disguised_non_image`
- `tests.test_webapp_routes::test_webapp_feed_returns_items`
- `tests.test_webapp_routes::test_webapp_my_feed_returns_only_current_user_cards`
- `tests.test_webapp_routes::test_generation_out_includes_all_result_urls`
- `tests.test_webapp_routes::test_webapp_public_models_is_public`
- `tests.test_webapp_routes::test_webapp_publish_generation_returns_feed_link`
- `tests.test_webapp_routes::test_trend_checkout_quote_recommends_smallest_plan_covering_deficit`
- `tests.test_webapp_routes::test_webapp_feed_item_returns_public_post_without_auth`
- `tests.test_webapp_routes::test_generate_image_from_prompt_library_keeps_user_prompt_and_rewards`
- `tests.test_webapp_routes::test_generate_image_spends_selected_quality_price`
- `tests.test_webapp_routes::test_generate_video_rejects_unsupported_duration_without_spending_credits`
- `tests.test_webapp_routes::test_feed_remix_image_uses_and_saves_reference`
- `tests.test_webapp_routes::test_feed_remix_image_uses_public_source_and_user_reference_without_secret`
- `tests.test_webapp_routes::test_feed_remix_midjourney_imagine_uses_hidden_prompt_and_source_ref`
- `tests.test_webapp_routes::test_feed_remix_midjourney_blend_uses_source_ref_and_reference_urls`
- `tests.test_webapp_routes::test_webapp_image_models_expose_single_ref_caps_and_no_false_count`
- `tests.test_webapp_routes::test_normalize_video_request_maps_legacy_kling_30_motion_aliases`
- `tests.test_webapp_routes::test_webapp_image_models_expose_seedream_5_pro_caps`
