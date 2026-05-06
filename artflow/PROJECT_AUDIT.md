# Project Audit

Date: 2026-05-06
Branch: `miniapp-mvp`

## Scope

Audited the current FastAPI, aiogram bot, webapp API, prompt marketplace preview handling, and testing setup. Added a pytest baseline that covers every major layer with smoke and unit tests.

## Added Test Coverage

- Telegram object factories: `tests/factories.py`
- WebApp auth HMAC validation: `tests/test_webapp_auth.py`
- WebApp API smoke and protected endpoint behavior: `tests/test_webapp_routes.py`
- Prompt preview fallback and local file resolution: `tests/test_marketplace_previews.py`
- Public upload URL normalization for legacy `.bin` images: `tests/test_public_files.py`
- KIE webhook parsing helpers: `tests/test_kie_webhook.py`
- Prompt repository pure logic: `tests/test_prompt_repository.py`
- Auth and throttling middlewares: `tests/test_middlewares.py`
- Keyboards and approved main menu WebApp button: `tests/test_keyboards_and_ui.py`
- `bot_tester.py` behavior and `bot-tester.skill` archive presence: `tests/test_bot_tester.py`, `tests/test_project_smoke.py`
- Whole-project Python compile smoke: `tests/test_project_smoke.py`

## Current Test Result

```bash
./venv/bin/pytest
# 34 passed

./venv/bin/pytest --cov=api --cov=bot --cov=db --cov-report=term-missing
# 34 passed, total line coverage: 33%
```

## Findings

1. The project previously had no pytest baseline. This made regressions in Telegram auth, bot keyboards, and preview handling easy to miss.
2. Several production flows depend on external APIs or Telegram side effects. They need contract-style mocks before line coverage can be pushed much higher safely.
3. Some modules are very large, especially image/video/admin handlers. They are testable, but need sliced tests around helpers and FSM transitions rather than one huge integration test.
4. `bot/handlers/admin.py` has pre-existing local changes in the working tree. I did not modify or stage them.
5. `bot_tester.py` uses long polling and should remain a manual/debug tool. It is now smoke-tested but should not run during production service startup.

## Recommended Next Steps

- Add tests for image generation FSM transitions with mocked KIE client.
- Add tests for payment webhook idempotency and transaction state transitions.
- Add repository tests against a disposable PostgreSQL database or testcontainers.
- Add CI command: `./venv/bin/python -m compileall api bot db main.py && ./venv/bin/pytest`.
