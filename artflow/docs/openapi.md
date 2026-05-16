# APIX OpenAPI

- Version: `1.0.0`
- OpenAPI: `3.1.0`
- Paths: `49`

APIX AI API for Telegram auth, content generation, billing, prompt library, feed, and provider webhooks.

## Generated Artifacts

- Machine-readable schema: `docs/openapi.json`
- Human-readable summary: `docs/openapi.md`

## Endpoints

### default

#### `GET /health`

- Summary: Health
- Operation ID: `health_health_get`
- Auth: not declared
- Request body: none

Parameters: none

Responses:
- `200`: Successful Response (`application/json`)

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

Responses:
- `200`: Successful Response (`application/json`)
- `422`: Validation Error (`application/json`)

#### `POST /webhook/kie/music`

- Summary: Kie Music Webhook
- Operation ID: `kie_music_webhook_webhook_kie_music_post`
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

### miniapp

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
- Request body: `application/json`: `TelegramLoginRequest`

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

Returns a shareable Telegram deeplink for this public post. Only the author can get it.

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

Start a generation using the hidden prompt of a public feed post.
The user chooses model/params; the original author's prompt is used silently.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `gen_id` | `path` | yes | `integer` |
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `202`: Successful Response (`application/json`)
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
| `x-telegram-init-data` | `header` | no | `string | null` |
| `x-web-auth-token` | `header` | no | `string | null` |

Responses:
- `202`: Successful Response (`application/json`)
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
- Operation ID: `health_api_v1_health_get`
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

Last N generations for the current user.

Parameters:

| Name | In | Required | Type |
| --- | --- | --- | --- |
| `limit` | `query` | no | `integer` |
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

Lightweight prompt improver for miniapp studio.

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
