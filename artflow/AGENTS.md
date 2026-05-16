# APIX Development Agents

These rules apply to Codex and delegated development agents working in this repository.

## MCP Tooling

- Use Context7 MCP for development work that depends on current library documentation, framework APIs, implementation patterns, or best practices.
- Use shadcn MCP for frontend and UI work: component research, UI patterns, registry examples, and shadcn-compatible implementation references.
- If an MCP server is unavailable in the current session, note that the Codex session may need to be restarted after updating `~/.codex/config.toml`, then continue with local project context.

## Scope Guardrails

- Do not change Telegram bot flows unless the task explicitly asks for it.
- Do not change KIE webhook, payment webhooks, mini app, or kanban unless the task explicitly asks for it.
- Prefer existing project patterns over introducing a new stack.
- Keep frontend work for the standalone site in `landing/` and web API work in `api/web/`.
- Keep Telegram mini app work in `webapp/` and `/api/webapp/*`.

## Verification

- Run `tools/codex_static_checks.sh` before final delivery on code changes.
- Report any failing checks with the failing test names and whether they appear related to the current change.
