# APIX OpenAPI

- Version: `1.0.0`
- OpenAPI: `3.1.0`
- Paths: `193`

APIX AI API for Telegram auth, content generation, billing, prompt library, feed, and provider webhooks.

## Generated Artifacts

- Machine-readable schema: `docs/openapi.json`
- Human-readable summary: `docs/openapi.md`

## Endpoints

### default

#### `GET /health`

- Summary: Health
- Operation ID: `public_health_get`
- Auth: not declared
- Request body: none

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)

#### `HEAD /health`

- Summary: Health
- Operation ID: `public_health_head`
- Auth: not declared
- Request body: none

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)

#### `GET /pay/lava/{invoice_id}`

- Summary: Lava Pay Redirect
- Operation ID: `lava_pay_redirect_pay_lava__invoice_id__get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `invoice_id` | `path` | yes | `string` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /upload`

- Summary: Upload File
- Operation ID: `upload_file_upload_post`
- Auth: not declared
- Request body: `multipart/form-data`: `Body_upload_file_upload_post`

Upload an image for use as a reference in generation.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /webhook/comet/midjourney`

- Summary: Midjourney Webhook
- Operation ID: `midjourney_webhook_webhook_comet_midjourney_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `secret` | `query` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /webhook/cryptobot`

- Summary: Cryptobot Webhook
- Operation ID: `cryptobot_webhook_webhook_cryptobot_post`
- Auth: not declared
- Request body: none

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)

#### `POST /webhook/kie`

- Summary: Kie Webhook
- Operation ID: `kie_webhook_webhook_kie_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `secret` | `query` | no | `string | null` |
| `provider` | `query` | no | `string | null` |
| `comet_kind` | `query` | no | `string | null` |
| `nexus_request_id` | `query` | no | `string | null` |
| `nexus_signature` | `query` | no | `string | null` |
| `apix_generation_id` | `query` | no | `integer | null` |
| `apix_generation_sig` | `query` | no | `string | null` |
| `X-KIE-Webhook-Secret` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /webhook/kie/music`

- Summary: Kie Music Webhook
- Operation ID: `kie_music_webhook_webhook_kie_music_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `secret` | `query` | no | `string | null` |
| `X-KIE-Webhook-Secret` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /webhook/kie/suno-voice`

- Summary: Kie Suno Voice Webhook
- Operation ID: `kie_suno_voice_webhook_webhook_kie_suno_voice_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `secret` | `query` | no | `string | null` |
| `stage` | `query` | no | `string | null` |
| `X-KIE-Webhook-Secret` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /webhook/lava`

- Summary: Lava Webhook
- Operation ID: `lava_webhook_webhook_lava_post`
- Auth: not declared
- Request body: none

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)

#### `POST /webhook/tbank`

- Summary: Tbank Webhook
- Operation ID: `tbank_webhook_webhook_tbank_post`
- Auth: not declared
- Request body: none

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)

#### `POST /webhook/telegram`

- Summary: Telegram Webhook
- Operation ID: `telegram_webhook_webhook_telegram_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-bot-api-secret-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /webhook/tribute`

- Summary: Tribute Webhook
- Operation ID: `tribute_webhook_webhook_tribute_post`
- Auth: not declared
- Request body: none

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)

### miniapp

#### `GET /api/v1/admin/overview`

- Summary: Admin Overview
- Operation ID: `admin_overview_api_v1_admin_overview_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `days` | `query` | no | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/admin/users`

- Summary: Admin Users
- Operation ID: `admin_users_api_v1_admin_users_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `query` | `query` | no | `string | null` |
| `limit` | `query` | no | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/admin/users/{user_id}`

- Summary: Admin User Detail
- Operation ID: `admin_user_detail_api_v1_admin_users__user_id__get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `user_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/admin/users/{user_id}/ban`

- Summary: Admin User Ban
- Operation ID: `admin_user_ban_api_v1_admin_users__user_id__ban_post`
- Auth: not declared
- Request body: `application/json`: `AdminBanRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `user_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/admin/users/{user_id}/credits`

- Summary: Admin User Credits
- Operation ID: `admin_user_credits_api_v1_admin_users__user_id__credits_post`
- Auth: not declared
- Request body: `application/json`: `AdminCreditsRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `user_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/admin/withdrawals`

- Summary: Admin Withdrawals
- Operation ID: `admin_withdrawals_api_v1_admin_withdrawals_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `status` | `query` | no | `string` |
| `limit` | `query` | no | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/admin/withdrawals/{request_id}/review`

- Summary: Admin Withdrawal Review
- Operation ID: `admin_withdrawal_review_api_v1_admin_withdrawals__request_id__review_post`
- Auth: not declared
- Request body: `application/json`: `AdminWithdrawalReviewRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `request_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/assistant`

- Summary: Miniapp Assistant
- Operation ID: `miniapp_assistant_api_v1_assistant_post`
- Auth: not declared
- Request body: `application/json`: `AssistantChatRequest`

Assistant chat inside the mini app, backed by the same assistant as the bot.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/auth/config`

- Summary: Web Auth Config
- Operation ID: `web_auth_config_api_v1_auth_config_get`
- Auth: not declared
- Request body: none

Public auth config for the standalone website.

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)

#### `POST /api/v1/auth/telegram-login`

- Summary: Web Telegram Login
- Operation ID: `web_telegram_login_api_v1_auth_telegram_login_post`
- Auth: not declared
- Request body: `application/json`: `api__miniapp_routes__TelegramLoginRequest`

Login for the standalone website via Telegram Login Widget.

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/feed`

- Summary: Get Feed
- Operation ID: `get_feed_api_v1_feed_get`
- Auth: not declared
- Request body: none

Public image feed — prompt is hidden from non-authors.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `source` | `query` | no | `string` |
| `limit` | `query` | no | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/feed/{gen_id}`

- Summary: Get Feed Item
- Operation ID: `get_feed_item_api_v1_feed__gen_id__get`
- Auth: not declared
- Request body: none

Hydrate shared posts with the same media and privacy contract as the list.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `gen_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/feed/{gen_id}/like`

- Summary: Like Feed Post
- Operation ID: `like_feed_post_api_v1_feed__gen_id__like_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `gen_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/feed/{gen_id}/link`

- Summary: Get Feed Share Link
- Operation ID: `get_feed_share_link_api_v1_feed__gen_id__link_get`
- Auth: not declared
- Request body: none

Returns a shareable public Mini App link for a public post.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `gen_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/feed/{gen_id}/remix`

- Summary: Remix Feed Post
- Operation ID: `remix_feed_post_api_v1_feed__gen_id__remix_post`
- Auth: not declared
- Request body: `application/json`: `FeedRemixRequest`

Repeat a public post, or edit its public media without disclosing author text.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `gen_id` | `path` | yes | `integer` |
| `surface` | `query` | no | `string` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `202`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/feed/{gen_id}/remix/quote`

- Summary: Quote Feed Remix
- Operation ID: `quote_feed_remix_api_v1_feed__gen_id__remix_quote_post`
- Auth: not declared
- Request body: `application/json`: `FeedRemixRequest`

Read-only exact DB tariff quote, with no reservation or paid submission.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `gen_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/feed/{gen_id}/remove`

- Summary: Remove Feed Post
- Operation ID: `remove_feed_post_api_v1_feed__gen_id__remove_post`
- Auth: not declared
- Request body: none

Remove own generation from the public feed.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `gen_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/feed/{generation_id}/display.webp`

- Summary: Feed Display Webp
- Operation ID: `feed_display_webp_api_v1_feed__generation_id__display_webp_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `generation_id` | `path` | yes | `integer` |
| `index` | `query` | no | `integer` |
| `output_id` | `query` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/feed/{generation_id}/preview.webp`

- Summary: Feed Preview Webp
- Operation ID: `feed_preview_webp_api_v1_feed__generation_id__preview_webp_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `generation_id` | `path` | yes | `integer` |
| `index` | `query` | no | `integer` |
| `output_id` | `query` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/generate/image`

- Summary: Create Image Generation
- Operation ID: `create_image_generation_api_v1_generate_image_post`
- Auth: not declared
- Request body: `application/json`: `ImageGenRequest`

Start an async image generation.

Returns immediately with `status: pending` and the generation `id`.
Poll `GET /api/v1/generations/{id}` until `status` is `done` or `failed`.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `surface` | `query` | no | `string` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `202`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/generate/music`

- Summary: Create Music Generation
- Operation ID: `create_music_generation_api_v1_generate_music_post`
- Auth: not declared
- Request body: `application/json`: `MusicGenRequest`

Start Suno music generation. Returns immediately; poll /generations/{id}.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `surface` | `query` | no | `string` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `202`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/generate/video`

- Summary: Create Video Generation
- Operation ID: `create_video_generation_api_v1_generate_video_post`
- Auth: not declared
- Request body: `application/json`: `VideoGenRequest`

Start an async video generation.

Returns immediately with `status: pending`.
Poll `GET /api/v1/generations/{id}` until done.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `surface` | `query` | no | `string` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `202`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/generate/video/quote`

- Summary: Quote Video Generation
- Operation ID: `quote_video_generation_api_v1_generate_video_quote_post`
- Auth: not declared
- Request body: `application/json`: `VideoGenRequest`

Read-only tariff quote after the same normalization and media probe as launch.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/generations/{gen_id}`

- Summary: Get Generation
- Operation ID: `get_generation_api_v1_generations__gen_id__get`
- Auth: not declared
- Request body: none

Poll a single generation for status and result_url.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `gen_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/generations/{gen_id}/publish`

- Summary: Publish Generation To Library
- Operation ID: `publish_generation_to_library_api_v1_generations__gen_id__publish_post`
- Auth: not declared
- Request body: none

User explicitly publishes own generation to public feed/prompt library.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `gen_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/generations/{gen_id}/remove-library`

- Summary: Remove From Library
- Operation ID: `remove_from_library_api_v1_generations__gen_id__remove_library_post`
- Auth: not declared
- Request body: none

Remove own generation's prompt from the public prompt library.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `gen_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/generations/{gen_id}/share`

- Summary: Share Generation
- Operation ID: `share_generation_api_v1_generations__gen_id__share_post`
- Auth: not declared
- Request body: none

Publish own generation to the public feed and return its repost link.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `gen_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/generations/{gen_id}/share-library`

- Summary: Share To Library
- Operation ID: `share_to_library_api_v1_generations__gen_id__share_library_post`
- Auth: not declared
- Request body: none

Opt this generation's prompt into the public prompt library.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `gen_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/health`

- Summary: Health
- Operation ID: `miniapp_health_get`
- Auth: not declared
- Request body: none

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)

#### `HEAD /api/v1/health`

- Summary: Health
- Operation ID: `miniapp_health_head`
- Auth: not declared
- Request body: none

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)

#### `GET /api/v1/help`

- Summary: Miniapp Help
- Operation ID: `miniapp_help_api_v1_help_get`
- Auth: not declared
- Request body: none

Help texts from the Telegram bot, exposed for the Mini App.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `topic` | `query` | no | `string` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/history`

- Summary: Get History
- Operation ID: `get_history_api_v1_history_get`
- Auth: not declared
- Request body: none

Paginated generations for the current user, newest first.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `limit` | `query` | no | `integer` |
| `offset` | `query` | no | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/me`

- Summary: Get Me
- Operation ID: `get_me_api_v1_me_get`
- Auth: not declared
- Request body: none

Current user profile with balance.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/me/feed`

- Summary: Get My Feed
- Operation ID: `get_my_feed_api_v1_me_feed_get`
- Auth: not declared
- Request body: none

Current user's public image/video feed posts.

NOTE (parity): unlike /history, this stays a bounded window (max 1000):
feed cards join user/session/remix metadata and are heavy, and the "Мои"
tab re-fetches on every selection. Paging beyond that needs cursor
pagination, not offset.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `limit` | `query` | no | `integer` |
| `offset` | `query` | no | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/me/permissions`

- Summary: Miniapp Permissions
- Operation ID: `miniapp_permissions_api_v1_me_permissions_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/me/photo`

- Summary: Set Me Photo
- Operation ID: `set_me_photo_api_v1_me_photo_post`
- Auth: not declared
- Request body: `application/json`: `ProfilePhotoRequest`

Save a profile photo uploaded by the current user.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/models/image`

- Summary: List Image Models
- Operation ID: `list_image_models_api_v1_models_image_get`
- Auth: not declared
- Request body: none

All active image models with costs and capabilities.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/models/music`

- Summary: List Music Models
- Operation ID: `list_music_models_api_v1_models_music_get`
- Auth: not declared
- Request body: none

All active music models with costs and capabilities.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/models/video`

- Summary: List Video Models
- Operation ID: `list_video_models_api_v1_models_video_get`
- Auth: not declared
- Request body: none

All active video models with costs and capabilities.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/music/from-audio`

- Summary: Generate From Source
- Operation ID: `generate_from_source_api_v1_music_from_audio_post`
- Auth: not declared
- Request body: `application/json`: `SunoSourceGenerationRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `surface` | `query` | no | `string` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `202`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/music/source-audio`

- Summary: Upload Source
- Operation ID: `upload_source_api_v1_music_source_audio_post`
- Auth: not declared
- Request body: `multipart/form-data`: `Body_upload_source_api_v1_music_source_audio_post`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `201`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/music/voices`

- Summary: List Suno Voices
- Operation ID: `list_suno_voices_api_v1_music_voices_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/music/voices`

- Summary: Create Suno Voice
- Operation ID: `create_suno_voice_api_v1_music_voices_post`
- Auth: not declared
- Request body: `multipart/form-data`: `Body_create_suno_voice_api_v1_music_voices_post`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `202`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/music/voices/{voice_id}/refresh`

- Summary: Refresh Suno Voice
- Operation ID: `refresh_suno_voice_api_v1_music_voices__voice_id__refresh_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `voice_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/music/voices/{voice_id}/verify`

- Summary: Verify Suno Voice
- Operation ID: `verify_suno_voice_api_v1_music_voices__voice_id__verify_post`
- Auth: not declared
- Request body: `multipart/form-data`: `Body_verify_suno_voice_api_v1_music_voices__voice_id__verify_post`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `voice_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `202`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/payment-methods`

- Summary: List Payment Methods
- Operation ID: `list_payment_methods_api_v1_payment_methods_get`
- Auth: not declared
- Request body: none

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)

#### `GET /api/v1/payment-options`

- Summary: List Payment Options
- Operation ID: `list_payment_options_api_v1_payment_options_get`
- Auth: not declared
- Request body: none

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)

#### `POST /api/v1/photo-prompt`

- Summary: Miniapp Photo Prompt
- Operation ID: `miniapp_photo_prompt_api_v1_photo_prompt_post`
- Auth: not declared
- Request body: `multipart/form-data`: `Body_miniapp_photo_prompt_api_v1_photo_prompt_post`

Generate prompt from uploaded photo for miniapp studio.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/plans`

- Summary: List Plans
- Operation ID: `list_plans_api_v1_plans_get`
- Auth: not declared
- Request body: none

Active price plans.

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)

#### `POST /api/v1/prompt/improve`

- Summary: Miniapp Improve Prompt
- Operation ID: `miniapp_improve_prompt_api_v1_prompt_improve_post`
- Auth: not declared
- Request body: `application/json`: `PromptImproveRequest`

Return prompt unchanged; generation payloads must use user text verbatim.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/prompts`

- Summary: List Prompts
- Operation ID: `list_prompts_api_v1_prompts_get`
- Auth: not declared
- Request body: none

Prompt marketplace: catalog plus bot-like top/popular/collection sources.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `category` | `query` | no | `string | null` |
| `source` | `query` | no | `string` |
| `tag` | `query` | no | `string | null` |
| `page` | `query` | no | `integer` |
| `limit` | `query` | no | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/prompts`

- Summary: Submit Prompt
- Operation ID: `submit_prompt_api_v1_prompts_post`
- Auth: not declared
- Request body: `application/json`: `PromptSubmitRequest`

Submit a new prompt for moderation.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `201`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/prompts/my`

- Summary: My Prompts
- Operation ID: `my_prompts_api_v1_prompts_my_get`
- Auth: not declared
- Request body: none

Prompts submitted by the current user, including moderation status.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/prompts/{prompt_id}`

- Summary: Get Prompt
- Operation ID: `get_prompt_api_v1_prompts__prompt_id__get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `prompt_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/prompts/{prompt_id}/deactivate`

- Summary: Deactivate Prompt Web
- Operation ID: `deactivate_prompt_web_api_v1_prompts__prompt_id__deactivate_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `prompt_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/prompts/{prompt_id}/like`

- Summary: Like Prompt Web
- Operation ID: `like_prompt_web_api_v1_prompts__prompt_id__like_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `prompt_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/prompts/{prompt_id}/link`

- Summary: Get Prompt Share Link
- Operation ID: `get_prompt_share_link_api_v1_prompts__prompt_id__link_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `prompt_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/prompts/{prompt_id}/use`

- Summary: Use Prompt Web
- Operation ID: `use_prompt_web_api_v1_prompts__prompt_id__use_post`
- Auth: not declared
- Request body: none

Mark a prompt as used when it is loaded into the web studio.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `prompt_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/public/feed/{gen_id}`

- Summary: Public Feed Post
- Operation ID: `public_feed_post_api_v1_public_feed__gen_id__get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `gen_id` | `path` | yes | `integer` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/public/midjourney`

- Summary: Public Midjourney Models
- Operation ID: `public_midjourney_models_api_v1_public_midjourney_get`
- Auth: not declared
- Request body: none

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)

#### `GET /api/v1/public/models`

- Summary: Public Models Summary
- Operation ID: `public_models_summary_api_v1_public_models_get`
- Auth: not declared
- Request body: none

Public model summary for the landing page.

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)

#### `GET /api/v1/referrals`

- Summary: Miniapp Referrals
- Operation ID: `miniapp_referrals_api_v1_referrals_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/referrals/exchange`

- Summary: Miniapp Exchange Referral Balance
- Operation ID: `miniapp_exchange_referral_balance_api_v1_referrals_exchange_post`
- Auth: not declared
- Request body: `application/json`: `ReferralExchangeRequestIn`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `201`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/referrals/withdrawals`

- Summary: Miniapp Create Referral Withdrawal
- Operation ID: `miniapp_create_referral_withdrawal_api_v1_referrals_withdrawals_post`
- Auth: not declared
- Request body: `application/json`: `ReferralWithdrawalRequestIn`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `201`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/services/pinterest`

- Summary: Get Pinterest Service
- Operation ID: `get_pinterest_service_api_v1_services_pinterest_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/services/pinterest/run`

- Summary: Run Pinterest Service
- Operation ID: `run_pinterest_service_api_v1_services_pinterest_run_post`
- Auth: not declared
- Request body: `application/json`: `PinterestServiceRunRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `202`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/services/pinterest/upload`

- Summary: Upload Pinterest Reference
- Operation ID: `upload_pinterest_reference_api_v1_services_pinterest_upload_post`
- Auth: not declared
- Request body: `multipart/form-data`: `Body_upload_pinterest_reference_api_v1_services_pinterest_upload_post`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/settings/language`

- Summary: Miniapp Set Language
- Operation ID: `miniapp_set_language_api_v1_settings_language_post`
- Auth: not declared
- Request body: `application/json`: `LanguageRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/topup/crypto`

- Summary: Topup Crypto
- Operation ID: `topup_crypto_api_v1_topup_crypto_post`
- Auth: not declared
- Request body: `application/json`: `TopupRequest`

Create a CryptoBot invoice. Returns `pay_url` to open in CryptoBot.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/topup/lava`

- Summary: Topup Lava
- Operation ID: `topup_lava_api_v1_topup_lava_post`
- Auth: not declared
- Request body: `application/json`: `TopupRequest`

Create a Lava invoice. Returns `pay_url` to open checkout.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/topup/stars`

- Summary: Topup Stars
- Operation ID: `topup_stars_api_v1_topup_stars_post`
- Auth: not declared
- Request body: `application/json`: `TopupRequest`

Create a Telegram Stars invoice link for the mini app.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/topup/tbank`

- Summary: Topup Tbank
- Operation ID: `topup_tbank_api_v1_topup_tbank_post`
- Auth: not declared
- Request body: `application/json`: `TopupRequest`

Create a T-Bank payment invoice. Returns `pay_url` to redirect the user.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/topup/tribute`

- Summary: Topup Tribute
- Operation ID: `topup_tribute_api_v1_topup_tribute_post`
- Auth: not declared
- Request body: `application/json`: `TopupRequest`

Return the fixed Tribute Digital Product checkout for a credit pack.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/video-prompt`

- Summary: Miniapp Video Prompt
- Operation ID: `miniapp_video_prompt_api_v1_video_prompt_post`
- Auth: not declared
- Request body: `multipart/form-data`: `Body_miniapp_video_prompt_api_v1_video_prompt_post`

Generate prompt from uploaded video for miniapp studio.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

### trends

#### `GET /api/v1/admin/trends`

- Summary: Admin List Trends
- Operation ID: `admin_list_trends_api_v1_admin_trends_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/admin/trends`

- Summary: Admin Create Trend
- Operation ID: `admin_create_trend_api_v1_admin_trends_post`
- Auth: not declared
- Request body: `application/json`: `TrendCreateRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `201`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/admin/trends/upload`

- Summary: Admin Upload Trend Preview
- Operation ID: `admin_upload_trend_preview_api_v1_admin_trends_upload_post`
- Auth: not declared
- Request body: `multipart/form-data`: `Body_admin_upload_trend_preview_api_v1_admin_trends_upload_post`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/admin/trends/{trend_id}/archive`

- Summary: Admin Archive Trend
- Operation ID: `admin_archive_trend_api_v1_admin_trends__trend_id__archive_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `trend_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/admin/trends/{trend_id}/update`

- Summary: Admin Update Trend
- Operation ID: `admin_update_trend_api_v1_admin_trends__trend_id__update_post`
- Auth: not declared
- Request body: `application/json`: `TrendUpdateRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `trend_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/trends`

- Summary: List Trends
- Operation ID: `list_trends_api_v1_trends_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `kind` | `query` | no | `string | null` |
| `limit` | `query` | no | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/trends/upload`

- Summary: Upload Trend Photo
- Operation ID: `upload_trend_photo_api_v1_trends_upload_post`
- Auth: not declared
- Request body: `multipart/form-data`: `Body_upload_trend_photo_api_v1_trends_upload_post`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/trends/{trend_id}`

- Summary: Get Trend
- Operation ID: `get_trend_api_v1_trends__trend_id__get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `trend_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/trends/{trend_id}/checkout`

- Summary: Trend Checkout
- Operation ID: `trend_checkout_api_v1_trends__trend_id__checkout_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `trend_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/v1/trends/{trend_id}/link`

- Summary: Trend Link
- Operation ID: `trend_link_api_v1_trends__trend_id__link_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `trend_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/trends/{trend_id}/prepare`

- Summary: Prepare Trend
- Operation ID: `prepare_trend_api_v1_trends__trend_id__prepare_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `trend_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/v1/trends/{trend_id}/run`

- Summary: Run Trend
- Operation ID: `run_trend_api_v1_trends__trend_id__run_post`
- Auth: not declared
- Request body: `application/json`: `TrendRunRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `trend_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `202`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

### web

#### `GET /api/web/admin/prompts`

- Summary: Admin Prompts
- Operation ID: `admin_prompts_api_web_admin_prompts_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `status` | `query` | no | `string` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/admin/prompts/{prompt_id}/approve`

- Summary: Admin Prompt Approve
- Operation ID: `admin_prompt_approve_api_web_admin_prompts__prompt_id__approve_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `prompt_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/admin/prompts/{prompt_id}/deactivate`

- Summary: Admin Prompt Deactivate
- Operation ID: `admin_prompt_deactivate_api_web_admin_prompts__prompt_id__deactivate_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `prompt_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/admin/prompts/{prompt_id}/reject`

- Summary: Admin Prompt Reject
- Operation ID: `admin_prompt_reject_api_web_admin_prompts__prompt_id__reject_post`
- Auth: not declared
- Request body: `application/json`: `PromptRejectRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `prompt_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/assistant`

- Summary: Assistant Chat
- Operation ID: `assistant_chat_api_web_assistant_post`
- Auth: not declared
- Request body: `application/json`: `AssistantChatRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/auth/config`

- Summary: Auth Config
- Operation ID: `auth_config_api_web_auth_config_get`
- Auth: not declared
- Request body: none

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)

#### `POST /api/web/auth/contact/request`

- Summary: Contact Auth Request
- Operation ID: `contact_auth_request_api_web_auth_contact_request_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `body` | `query` | yes | `object` |
| `request` | `query` | yes | `object` |
| `session` | `query` | yes | `object` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/auth/contact/verify`

- Summary: Contact Auth Verify
- Operation ID: `contact_auth_verify_api_web_auth_contact_verify_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `body` | `query` | yes | `object` |
| `response` | `query` | yes | `object` |
| `request` | `query` | yes | `object` |
| `session` | `query` | yes | `object` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/auth/logout`

- Summary: Logout
- Operation ID: `logout_api_web_auth_logout_post`
- Auth: not declared
- Request body: none

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)

#### `POST /api/web/auth/password-login`

- Summary: Password Login
- Operation ID: `password_login_api_web_auth_password_login_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `body` | `query` | yes | `object` |
| `response` | `query` | yes | `object` |
| `session` | `query` | yes | `object` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/auth/password-register`

- Summary: Password Register
- Operation ID: `password_register_api_web_auth_password_register_post`
- Auth: not declared
- Request body: `application/json`: `PasswordRegisterRequest`

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/auth/telegram-login`

- Summary: Telegram Login
- Operation ID: `telegram_login_api_web_auth_telegram_login_post`
- Auth: not declared
- Request body: `application/json`: `api__web__auth__TelegramLoginRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Web-Auth-Token` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/billing/payment-methods`

- Summary: Billing Payment Methods
- Operation ID: `billing_payment_methods_api_web_billing_payment_methods_get`
- Auth: not declared
- Request body: none

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)

#### `GET /api/web/billing/payment-options`

- Summary: Billing Payment Options
- Operation ID: `billing_payment_options_api_web_billing_payment_options_get`
- Auth: not declared
- Request body: none

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)

#### `GET /api/web/billing/plans`

- Summary: Billing Plans
- Operation ID: `billing_plans_api_web_billing_plans_get`
- Auth: not declared
- Request body: none

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)

#### `POST /api/web/billing/topup/crypto`

- Summary: Topup Crypto
- Operation ID: `topup_crypto_api_web_billing_topup_crypto_post`
- Auth: not declared
- Request body: `application/json`: `TopupRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/billing/topup/lava`

- Summary: Topup Lava
- Operation ID: `topup_lava_api_web_billing_topup_lava_post`
- Auth: not declared
- Request body: `application/json`: `TopupRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/billing/topup/stars`

- Summary: Topup Stars
- Operation ID: `topup_stars_api_web_billing_topup_stars_post`
- Auth: not declared
- Request body: `application/json`: `TopupRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/billing/topup/tbank`

- Summary: Topup Tbank
- Operation ID: `topup_tbank_api_web_billing_topup_tbank_post`
- Auth: not declared
- Request body: `application/json`: `TopupRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/billing/topup/tribute`

- Summary: Topup Tribute
- Operation ID: `topup_tribute_api_web_billing_topup_tribute_post`
- Auth: not declared
- Request body: `application/json`: `TopupRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/billing/transactions`

- Summary: Billing Transactions
- Operation ID: `billing_transactions_api_web_billing_transactions_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `limit` | `query` | no | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/feed`

- Summary: Feed
- Operation ID: `feed_api_web_feed_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `source` | `query` | no | `string` |
| `limit` | `query` | no | `integer` |
| `compact` | `query` | no | `boolean` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/feed/generations/{generation_id}/publish`

- Summary: Publish Own Generation To Feed
- Operation ID: `publish_own_generation_to_feed_api_web_feed_generations__generation_id__publish_post`
- Auth: not declared
- Request body: none

Publish any own ready image/video generation without exposing its prompt.

This endpoint deliberately does not reject hidden-prompt generations or feed
remixes. The public feed payload always hides prompts, so users can publish
their own finished media while trend/remix source prompts stay protected.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `generation_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/feed/top`

- Summary: Feed Top
- Operation ID: `feed_top_api_web_feed_top_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `limit` | `query` | no | `integer` |
| `compact` | `query` | no | `boolean` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/feed/{generation_id}`

- Summary: Feed Item
- Operation ID: `feed_item_api_web_feed__generation_id__get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `generation_id` | `path` | yes | `integer` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/feed/{generation_id}/like`

- Summary: Feed Like
- Operation ID: `feed_like_api_web_feed__generation_id__like_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `generation_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/feed/{generation_id}/link`

- Summary: Feed Share Link
- Operation ID: `feed_share_link_api_web_feed__generation_id__link_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `generation_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/feed/{generation_id}/remix`

- Summary: Remix Feed Generation
- Operation ID: `remix_feed_generation_api_web_feed__generation_id__remix_post`
- Auth: not declared
- Request body: `application/json`: `FeedRemixRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `generation_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `202`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/feed/{generation_id}/remix/quote`

- Summary: Quote Feed Generation
- Operation ID: `quote_feed_generation_api_web_feed__generation_id__remix_quote_post`
- Auth: not declared
- Request body: `application/json`: `FeedRemixRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `generation_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/feed/{generation_id}/remove`

- Summary: Remove Feed Generation
- Operation ID: `remove_feed_generation_api_web_feed__generation_id__remove_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `generation_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/feed/{generation_id}/share`

- Summary: Feed Share
- Operation ID: `feed_share_api_web_feed__generation_id__share_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `generation_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/generate/image`

- Summary: Generate Image
- Operation ID: `generate_image_api_web_generate_image_post`
- Auth: not declared
- Request body: `application/json`: `ImageGenRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `202`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/generate/music`

- Summary: Generate Music
- Operation ID: `generate_music_api_web_generate_music_post`
- Auth: not declared
- Request body: `application/json`: `MusicGenRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `202`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/generate/video`

- Summary: Generate Video
- Operation ID: `generate_video_api_web_generate_video_post`
- Auth: not declared
- Request body: `application/json`: `VideoGenRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `202`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/generate/video/quote`

- Summary: Quote Video
- Operation ID: `quote_video_api_web_generate_video_quote_post`
- Auth: not declared
- Request body: `application/json`: `VideoGenRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/generations/active`

- Summary: Active Generations
- Operation ID: `active_generations_api_web_generations_active_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/generations/{generation_id}`

- Summary: Generation Detail
- Operation ID: `generation_detail_api_web_generations__generation_id__get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `generation_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/generations/{generation_id}/download`

- Summary: Generation Download
- Operation ID: `generation_download_api_web_generations__generation_id__download_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `generation_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/generations/{generation_id}/publish`

- Summary: Publish Generation
- Operation ID: `publish_generation_api_web_generations__generation_id__publish_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `generation_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/generations/{generation_id}/remove-library`

- Summary: Remove Generation From Library
- Operation ID: `remove_generation_from_library_api_web_generations__generation_id__remove_library_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `generation_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/generations/{generation_id}/share`

- Summary: Share Generation
- Operation ID: `share_generation_api_web_generations__generation_id__share_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `generation_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/generations/{generation_id}/share-library`

- Summary: Share Generation To Library
- Operation ID: `share_generation_to_library_api_web_generations__generation_id__share_library_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `generation_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/h3/upload-reference`

- Summary: Upload H3 Reference
- Operation ID: `upload_h3_reference_api_web_h3_upload_reference_post`
- Auth: not declared
- Request body: `multipart/form-data`: `Body_upload_h3_reference_api_web_h3_upload_reference_post`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/health`

- Summary: Health
- Operation ID: `health_api_web_health_get`
- Auth: not declared
- Request body: none

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)

#### `GET /api/web/help`

- Summary: Help Text
- Operation ID: `help_text_api_web_help_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `topic` | `query` | no | `string` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/history`

- Summary: History
- Operation ID: `history_api_web_history_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `limit` | `query` | no | `integer` |
| `offset` | `query` | no | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/image-sessions`

- Summary: Create Image Session
- Operation ID: `create_image_session_api_web_image_sessions_post`
- Auth: not declared
- Request body: `application/json`: `ImageSessionCreateRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/image-sessions/active`

- Summary: Active Image Session
- Operation ID: `active_image_session_api_web_image_sessions_active_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/image-sessions/{session_id}/archive`

- Summary: Archive Image Session
- Operation ID: `archive_image_session_api_web_image_sessions__session_id__archive_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `session_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/landing`

- Summary: Landing Payload
- Operation ID: `landing_payload_api_web_landing_get`
- Auth: not declared
- Request body: none

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)

#### `GET /api/web/me`

- Summary: Me
- Operation ID: `me_api_web_me_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `PUT /api/web/me/password`

- Summary: Update Password
- Operation ID: `update_password_api_web_me_password_put`
- Auth: not declared
- Request body: `application/json`: `PasswordUpdateRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `PUT /api/web/me/profile`

- Summary: Update Profile
- Operation ID: `update_profile_api_web_me_profile_put`
- Auth: not declared
- Request body: `application/json`: `ProfileUpdateRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/models`

- Summary: Models
- Operation ID: `models_api_web_models_get`
- Auth: not declared
- Request body: none

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)

#### `GET /api/web/models/image`

- Summary: Image Models
- Operation ID: `image_models_api_web_models_image_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/models/music`

- Summary: Music Models
- Operation ID: `music_models_api_web_models_music_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/models/video`

- Summary: Video Models
- Operation ID: `video_models_api_web_models_video_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/music/from-audio`

- Summary: Generate From Source
- Operation ID: `generate_from_source_api_web_music_from_audio_post`
- Auth: not declared
- Request body: `application/json`: `SunoSourceGenerationRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `202`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/music/source-audio`

- Summary: Upload Source
- Operation ID: `upload_source_api_web_music_source_audio_post`
- Auth: not declared
- Request body: `multipart/form-data`: `Body_upload_source_api_web_music_source_audio_post`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `201`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/music/voices`

- Summary: Suno Voices
- Operation ID: `suno_voices_api_web_music_voices_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/music/voices`

- Summary: Create Suno Voice
- Operation ID: `create_suno_voice_api_web_music_voices_post`
- Auth: not declared
- Request body: `multipart/form-data`: `Body_create_suno_voice_api_web_music_voices_post`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `202`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/music/voices/{voice_id}/refresh`

- Summary: Refresh Suno Voice
- Operation ID: `refresh_suno_voice_api_web_music_voices__voice_id__refresh_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `voice_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/music/voices/{voice_id}/verify`

- Summary: Verify Suno Voice
- Operation ID: `verify_suno_voice_api_web_music_voices__voice_id__verify_post`
- Auth: not declared
- Request body: `multipart/form-data`: `Body_verify_suno_voice_api_web_music_voices__voice_id__verify_post`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `voice_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `202`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/photo-prompt`

- Summary: Photo Prompt
- Operation ID: `photo_prompt_api_web_photo_prompt_post`
- Auth: not declared
- Request body: `multipart/form-data`: `Body_photo_prompt_api_web_photo_prompt_post`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/price-plans`

- Summary: Price Plans
- Operation ID: `price_plans_api_web_price_plans_get`
- Auth: not declared
- Request body: none

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)

#### `POST /api/web/prompt/improve`

- Summary: Improve Prompt
- Operation ID: `improve_prompt_api_web_prompt_improve_post`
- Auth: not declared
- Request body: `application/json`: `PromptImproveRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/prompts`

- Summary: Prompts
- Operation ID: `prompts_api_web_prompts_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `source` | `query` | no | `string` |
| `tag` | `query` | no | `string | null` |
| `category` | `query` | no | `string | null` |
| `page` | `query` | no | `integer` |
| `limit` | `query` | no | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/prompts`

- Summary: Prompt Create
- Operation ID: `prompt_create_api_web_prompts_post`
- Auth: not declared
- Request body: `application/json`: `PromptCreateRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/prompts/{prompt_id}`

- Summary: Prompt Detail
- Operation ID: `prompt_detail_api_web_prompts__prompt_id__get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `prompt_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/prompts/{prompt_id}/like`

- Summary: Prompt Like
- Operation ID: `prompt_like_api_web_prompts__prompt_id__like_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `prompt_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/prompts/{prompt_id}/use`

- Summary: Prompt Use
- Operation ID: `prompt_use_api_web_prompts__prompt_id__use_post`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `prompt_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/referrals`

- Summary: Referrals
- Operation ID: `referrals_api_web_referrals_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/referrals/exchange`

- Summary: Exchange Referral Balance
- Operation ID: `exchange_referral_balance_api_web_referrals_exchange_post`
- Auth: not declared
- Request body: `application/json`: `ReferralWithdrawalRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/referrals/withdrawals`

- Summary: Create Referral Withdrawal
- Operation ID: `create_referral_withdrawal_api_web_referrals_withdrawals_post`
- Auth: not declared
- Request body: `application/json`: `ReferralWithdrawalRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/seedance25/upload-reference`

- Summary: Upload Seedance25 Reference
- Operation ID: `upload_seedance25_reference_api_web_seedance25_upload_reference_post`
- Auth: not declared
- Request body: `multipart/form-data`: `Body_upload_seedance25_reference_api_web_seedance25_upload_reference_post`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/settings/language`

- Summary: Set Language
- Operation ID: `set_language_api_web_settings_language_post`
- Auth: not declared
- Request body: `application/json`: `LanguageRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/upload-media`

- Summary: Upload Media
- Operation ID: `upload_media_api_web_upload_media_post`
- Auth: not declared
- Request body: `multipart/form-data`: `Body_upload_media_api_web_upload_media_post`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/upload-media/check`

- Summary: Check Reference Availability
- Operation ID: `check_reference_availability_api_web_upload_media_check_post`
- Auth: not declared
- Request body: `application/json`: `ReferenceCheckRequest`

Inspect a known public upload; never fetch external URLs or renew access.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/upload-media/policy`

- Summary: Upload Media Policy
- Operation ID: `upload_media_policy_api_web_upload_media_policy_get`
- Auth: not declared
- Request body: none

Read-only upload limits shared with the existing server validator.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/uploads/reference`

- Summary: Upload Reference
- Operation ID: `upload_reference_api_web_uploads_reference_post`
- Auth: not declared
- Request body: `multipart/form-data`: `Body_upload_reference_api_web_uploads_reference_post`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/video-prompt`

- Summary: Video Prompt
- Operation ID: `video_prompt_api_web_video_prompt_post`
- Auth: not declared
- Request body: `multipart/form-data`: `Body_video_prompt_api_web_video_prompt_post`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

### web-admin

#### `GET /api/web/admin/feed-recipe-identity`

- Summary: Admin Get Feed Recipe Identity Policy
- Operation ID: `admin_get_feed_recipe_identity_policy_api_web_admin_feed_recipe_identity_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `PUT /api/web/admin/feed-recipe-identity`

- Summary: Admin Set Feed Recipe Identity Policy
- Operation ID: `admin_set_feed_recipe_identity_policy_api_web_admin_feed_recipe_identity_put`
- Auth: not declared
- Request body: `application/json`: `FeedRecipeIdentityPolicyUpdate`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/admin/generations`

- Summary: Admin Generations
- Operation ID: `admin_generations_api_web_admin_generations_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `status` | `query` | no | `string` |
| `gen_type` | `query` | no | `string` |
| `q` | `query` | no | `string | null` |
| `limit` | `query` | no | `integer` |
| `offset` | `query` | no | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/admin/generations/{generation_id}/fail`

- Summary: Admin Fail Generation
- Operation ID: `admin_fail_generation_api_web_admin_generations__generation_id__fail_post`
- Auth: not declared
- Request body: `application/json`: `AdminGenerationFailRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `generation_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/admin/image-recovery/{provider}`

- Summary: Admin Get Image Recovery Policy
- Operation ID: `admin_get_image_recovery_policy_api_web_admin_image_recovery__provider__get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `provider` | `path` | yes | `string` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `PUT /api/web/admin/image-recovery/{provider}`

- Summary: Admin Set Image Recovery Policy
- Operation ID: `admin_set_image_recovery_policy_api_web_admin_image_recovery__provider__put`
- Auth: not declared
- Request body: `application/json`: `ImageRecoveryPolicyUpdate`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `provider` | `path` | yes | `string` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `PUT /api/web/admin/images/refund-supplier-review/{gen_id}`

- Summary: Admin Resolve Refunded Image Supplier Review
- Operation ID: `admin_resolve_refunded_image_supplier_review_api_web_admin_images_refund_supplier_review__gen_id__put`
- Auth: not declared
- Request body: `application/json`: `SupplierReviewResolutionRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `gen_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/admin/images/refund-supplier-reviews`

- Summary: Admin List Unsettled Image Supplier Reviews
- Operation ID: `admin_list_unsettled_image_supplier_reviews_api_web_admin_images_refund_supplier_reviews_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `limit` | `query` | no | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/admin/ledger`

- Summary: Admin Ledger
- Operation ID: `admin_ledger_api_web_admin_ledger_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `user_id` | `query` | no | `integer | null` |
| `limit` | `query` | no | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `PATCH /api/web/admin/model-costs/{model_id}`

- Summary: Admin Update Model Cost
- Operation ID: `admin_update_model_cost_api_web_admin_model_costs__model_id__patch`
- Auth: not declared
- Request body: `application/json`: `AdminModelCostUpdateRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `model_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/admin/overview`

- Summary: Admin Overview
- Operation ID: `admin_overview_api_web_admin_overview_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `PATCH /api/web/admin/price-plans/{plan_id}`

- Summary: Admin Update Price Plan
- Operation ID: `admin_update_price_plan_api_web_admin_price_plans__plan_id__patch`
- Auth: not declared
- Request body: `application/json`: `AdminPricePlanUpdateRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `plan_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/admin/pricing`

- Summary: Admin Pricing
- Operation ID: `admin_pricing_api_web_admin_pricing_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `q` | `query` | no | `string | null` |
| `include_inactive` | `query` | no | `boolean` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/admin/provider-routing/nano-banana-2.1`

- Summary: Admin Get Nano21 Provider
- Operation ID: `admin_get_nano21_provider_api_web_admin_provider_routing_nano_banana_2_1_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `PUT /api/web/admin/provider-routing/nano-banana-2.1`

- Summary: Admin Set Nano21 Provider
- Operation ID: `admin_set_nano21_provider_api_web_admin_provider_routing_nano_banana_2_1_put`
- Auth: not declared
- Request body: `application/json`: `Nano21ProviderRoutingUpdate`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/admin/provider-routing/qwen38/{mode}`

- Summary: Admin Get Qwen Route
- Operation ID: `admin_get_qwen_route_api_web_admin_provider_routing_qwen38__mode__get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `mode` | `path` | yes | `string` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `PUT /api/web/admin/provider-routing/qwen38/{mode}`

- Summary: Admin Set Qwen Route
- Operation ID: `admin_set_qwen_route_api_web_admin_provider_routing_qwen38__mode__put`
- Auth: not declared
- Request body: `application/json`: `QwenProviderRoutingUpdate`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `mode` | `path` | yes | `string` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `PUT /api/web/admin/seedance/refund-supplier-review/{gen_id}`

- Summary: Admin Resolve Refunded Seedance Supplier Review
- Operation ID: `admin_resolve_refunded_seedance_supplier_review_api_web_admin_seedance_refund_supplier_review__gen_id__put`
- Auth: not declared
- Request body: `application/json`: `SupplierReviewResolutionRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `gen_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/admin/seedance/refund-supplier-reviews`

- Summary: Admin List Unsettled Seedance Supplier Reviews
- Operation ID: `admin_list_unsettled_seedance_supplier_reviews_api_web_admin_seedance_refund_supplier_reviews_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `limit` | `query` | no | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/admin/users`

- Summary: Admin Users
- Operation ID: `admin_users_api_web_admin_users_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `q` | `query` | no | `string | null` |
| `limit` | `query` | no | `integer` |
| `offset` | `query` | no | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/admin/users/{user_id}/ban`

- Summary: Admin Set User Ban
- Operation ID: `admin_set_user_ban_api_web_admin_users__user_id__ban_post`
- Auth: not declared
- Request body: `application/json`: `AdminBanRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `user_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/admin/users/{user_id}/credits`

- Summary: Admin Adjust User Credits
- Operation ID: `admin_adjust_user_credits_api_web_admin_users__user_id__credits_post`
- Auth: not declared
- Request body: `application/json`: `AdminCreditAdjustmentRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `user_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `GET /api/web/admin/withdrawals`

- Summary: Admin Withdrawals
- Operation ID: `admin_withdrawals_api_web_admin_withdrawals_get`
- Auth: not declared
- Request body: none

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `status` | `query` | no | `string` |
| `limit` | `query` | no | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /api/web/admin/withdrawals/{request_id}`

- Summary: Admin Review Withdrawal
- Operation ID: `admin_review_withdrawal_api_web_admin_withdrawals__request_id__post`
- Auth: not declared
- Request body: `application/json`: `AdminWithdrawalActionRequest`

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `request_id` | `path` | yes | `integer` |
| `X-Dev-Tg-Id` | `header` | no | `string | null` |
| `X-Web-Auth-Token` | `header` | no | `string | null` |
| `X-Telegram-Init-Data` | `header` | no | `string | null` |

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)
