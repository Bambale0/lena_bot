# Image Model Unlimited Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let admins grant selected users unlimited image generation on selected image models without affecting video/music billing or other users.

**Architecture:** Add a normalized PostgreSQL entitlement table keyed by `user_id + base model_key`, with a foreign key to `model_costs.model_key`. Centralize image-generation charging in repository helpers that resolve unlimited entitlement and return the actual charged amount. Admin control lives in the Telegram `/admin` panel: enter Telegram/internal user ID, then toggle active image models. All image-generation surfaces reuse the same charge helper so bot, Mini App, and web behave consistently.

**Tech Stack:** Python 3, FastAPI, aiogram, SQLAlchemy async, PostgreSQL, Alembic, pytest.

**Spec:** User request in chat, 2026-09-23.

## Global Constraints

- Unlimited applies only to `GenerationType.image`.
- Admin selects the exact models per user; no source-code whitelist.
- Telegram ID or internal user ID can be used to find the target user.
- Unlimited image generations charge 0 credits and store `credits_spent=0`.
- Failure/refund paths must never credit a user for an unlimited generation.
- Video, music, video-to-prompt and unrelated credit operations remain unchanged.
- Authorization remains server-side; admin UI alone is not a security boundary.
- All applicable user surfaces must share the same billing rule.

---

### Task 1: Entitlement schema and repository contract

**Files:**
- Modify: `artflow/db/models.py`
- Create: `artflow/db/migrations/versions/034_user_image_model_unlimited.py`
- Modify: `artflow/db/repository.py`
- Test: `artflow/tests/test_image_model_unlimited.py`

**Interfaces:**
- Produces: `UserImageModelUnlimited` model.
- Produces: `ImageGenerationCharge`, `charge_image_generation()`, `has_unlimited_image_model()`, `get_user_unlimited_image_model_ids()`, `set_user_image_model_unlimited()`, `clear_user_image_model_unlimited()`.

- [ ] **Step 1: Write failing repository tests** for unlimited charge = 0, normal charge = model price, image-only validation, toggle/list/clear behavior.
- [ ] **Step 2: Run focused tests and confirm RED** because the model/helpers do not exist.
- [ ] **Step 3: Add schema + Alembic migration** with unique `(user_id, model_key)`, FKs with cascade, admin actor and timestamp.
- [ ] **Step 4: Implement minimal repository helpers** and safe structured logging.
- [ ] **Step 5: Run focused tests and confirm GREEN**.

### Task 2: Telegram admin control plane

**Files:**
- Modify: `artflow/bot/handlers/admin.py`
- Modify: `artflow/tests/test_admin.py`
- Modify: `artflow/tests/test_fsm.py`

**Interfaces:**
- Consumes repository entitlement helpers.
- Produces `adm:image_unlimited` flow and model toggle callbacks.

- [ ] **Step 1: Write failing admin tests** for menu button, ID input, model list/toggle, and clear-all.
- [ ] **Step 2: Run focused tests and confirm RED**.
- [ ] **Step 3: Add FSM state and admin handlers**; resolve Telegram ID first, then internal ID; show only active image models.
- [ ] **Step 4: Keep callback payloads short by using `model_cost_id`**, validate image type server-side.
- [ ] **Step 5: Run focused admin tests and confirm GREEN**.

### Task 3: Apply unlimited billing to image generation surfaces

**Files:**
- Modify: `artflow/bot/handlers/image_gen.py`
- Modify: `artflow/bot/handlers/midjourney.py`
- Modify: `artflow/api/miniapp_routes.py`
- Test: `artflow/tests/test_image_gen_references.py`
- Test: `artflow/tests/test_webapp_routes.py`
- Test: `artflow/tests/test_midjourney.py` or closest existing Midjourney test file

**Interfaces:**
- Consumes `charge_image_generation()`.
- Uses `charge.charged_credits` for `Generation.credits_spent` and refund paths.

- [ ] **Step 1: Write failing integration regressions** proving an entitled user can generate with zero balance and no credit deduction.
- [ ] **Step 2: Run focused tests and confirm RED**.
- [ ] **Step 3: Replace image-only spend paths** with centralized image charge helper.
- [ ] **Step 4: Ensure generated records/refunds use actual charged credits, not nominal tariff**.
- [ ] **Step 5: Verify site/web parity through shared Mini App/web generation handlers**.
- [ ] **Step 6: Run focused regressions and confirm GREEN**.

### Task 4: Verification, review and delivery

**Files:**
- Modify: `artflow/docs/agents/EXECUTION.md`

- [ ] **Step 1: Run migration contract, focused pytest, maintained PR gate, Ruff/compile, frontend build/smoke where CI requires it**.
- [ ] **Step 2: Review diff for billing/refund/authorization regressions**.
- [ ] **Step 3: Open PR and wait for exact-head CI**.
- [ ] **Step 4: Merge only with all required gates green**.
- [ ] **Step 5: Verify production autodeploy, Alembic upgrade, health, and application logs**.
