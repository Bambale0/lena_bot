# Frontend Agent Workflow

This document defines a production-oriented multi-agent workflow for turning a product brief into a shipped frontend application.

## Goal

Given a request such as:

> Build a SaaS landing page for AI bots with account area, payments, onboarding, and deploy.

The agent team should move through a controlled delivery chain:

1. Brief and product idea
2. Product and UX analysis
3. User flow and screen map
4. UI specification
5. Design system and tokens
6. Frontend architecture
7. Component implementation
8. Page implementation
9. API and state integration
10. Accessibility and responsive QA
11. E2E tests
12. Build and deploy
13. Final report and handoff

Default production stack for new frontend apps:

- Next.js App Router
- TypeScript
- React
- Tailwind CSS
- Storybook
- Playwright
- GitHub Actions
- Vercel

For existing projects, prefer the repo stack unless the user explicitly asks for a new app or migration.

## MCP Policy

Development agents must use MCP tools as part of their normal research loop:

- Context7 MCP is the default documentation source for all developer agents when checking current library APIs, framework behavior, package usage, and best practices.
- shadcn MCP is required for frontend/UI agents when researching component patterns, registry examples, shadcn-compatible blocks, and implementation references.
- Frontend agents should consult shadcn before designing or implementing reusable controls, dialogs, forms, navigation, cards, empty states, and layout primitives.
- If an MCP server is not visible in the current Codex session, the orchestrator should record that the session needs a restart after MCP config changes and continue using local repo context.
- Do not paste MCP API keys or secrets into project files, artifacts, client code, docs, or screenshots.

## Artifact Contract

Agents communicate through machine-readable or structured artifacts. Each agent must read its input artifact, make assumptions when data is missing, produce its output artifact, and record risks and TODOs.

Recommended artifact paths:

```text
artifacts/
  00-brief.md
  01-prd.md
  02-user-flow.md
  03-screen-map.md
  04-design-system.json
  05-component-inventory.md
  06-frontend-architecture.md
  07-api-contract.md
  08-qa-report.md
  09-deploy-report.md
```

Recommended app structure for new Next.js projects:

```text
src/
  app/
  components/
  features/
  lib/
  hooks/
  styles/
  types/
  tests/
```

## Agents

| Agent | Role | Input | Output |
| --- | --- | --- | --- |
| Frontend Orchestrator | Owns routing, gates, MCP availability, and final delivery | User task, repo context, artifacts | Current phase, selected agent, handoff, final report |
| Product UX Agent | Converts vague requests into product requirements | Brief, goals, audience, Context7 when product depends on current platform docs | `01-prd.md` |
| UX Flow Agent | Builds journeys and screen architecture | PRD, Context7 for current UX/platform constraints | `02-user-flow.md`, `03-screen-map.md` |
| UI Design Agent | Defines implementable layouts and visual behavior | Flow, screen map, brand, shadcn examples | UI specification |
| Design System Agent | Defines reusable UI system | UI specification, shadcn registry patterns | `04-design-system.json`, `05-component-inventory.md` |
| Frontend Architect Agent | Designs app architecture | PRD, design system, Context7 framework docs | `06-frontend-architecture.md` |
| Component Developer Agent | Implements reusable typed components | Component inventory, shadcn component references, Context7 package docs | Component files and stories |
| Page Builder Agent | Composes routes and layouts | Components, routes, shadcn layout references | Page files |
| API Integration Agent | Connects APIs, auth, forms, state | API docs, app pages, Context7 docs for clients/state libs | `07-api-contract.md`, API helpers |
| QA/A11y Agent | Finds release-blocking defects | App preview/code, Context7 for testing/a11y docs | `08-qa-report.md` |
| E2E Test Agent | Writes Playwright tests | User flows, Context7 Playwright docs | E2E specs and coverage notes |
| DevOps Deploy Agent | Prepares CI/CD and deploy | Repo, env vars, Context7 deployment docs | `09-deploy-report.md` |
| Code Review Agent | Reviews final implementation | Final code state, Context7 for disputed APIs | Final code review |

## Orchestrator Rules

The orchestrator must always return:

1. Current phase
2. Agent selected
3. Input artifact
4. Expected output artifact
5. Quality gate
6. Next handoff
7. MCP sources used or unavailable

Quality gates:

- No coding before PRD and user flow exist.
- No page building before component inventory exists.
- No deployment before lint, typecheck, build, and tests pass.
- No final handoff without QA report and deploy report.

## Handoff Order

```text
Orchestrator
  -> Product UX Agent
  -> UX Flow Agent
  -> UI Design Agent
  -> Design System Agent
  -> Frontend Architect Agent
  -> Component Developer Agent
  -> Page Builder Agent
  -> API Integration Agent
  -> QA/A11y Agent
  -> E2E Test Agent
  -> DevOps Deploy Agent
  -> Code Review Agent
  -> Orchestrator final response
```

## Guardrails

- Do not deploy if build fails.
- Do not write UI without a design system or documented assumptions.
- Do not change API contracts without documenting the change and impact.
- Do not delete existing code without explaining why.
- Do not expose secrets in client-side code.
- Do not skip accessibility states.
- Do not mark the task complete without a QA report.
- Do not claim tests passed unless they were actually run.

## Tool Permissions

| Agent | Read | Write | Shell | Deploy |
| --- | --- | --- | --- | --- |
| Product UX | Yes | `artifacts/` only | No | No |
| UX Flow | Yes | `artifacts/` only | No | No |
| UI Design | Yes | `artifacts/` only | No | No |
| Architect | Yes | `artifacts/`, scaffolding | Limited | No |
| Component Developer | Yes | `src/components/` | Yes | No |
| Page Builder | Yes | `src/app/`, `src/features/` | Yes | No |
| API Integration | Yes | `src/lib/`, `src/types/`, `src/features/` | Yes | No |
| QA/A11y | Yes | reports | Yes | No |
| E2E Test | Yes | tests | Yes | No |
| DevOps Deploy | Yes | CI/deploy config | Yes | After gates |
| Code Review | Yes | reports | No | No |

## Minimum CI

```yaml
name: frontend-ci

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  checks:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Node
        uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm

      - name: Install dependencies
        run: npm ci

      - name: Lint
        run: npm run lint

      - name: Typecheck
        run: npm run typecheck

      - name: Unit tests
        run: npm run test --if-present

      - name: Build
        run: npm run build

      - name: Install Playwright
        run: npx playwright install --with-deps

      - name: E2E tests
        run: npm run e2e --if-present
```

## Final Delivery Report

The final orchestrator response must include:

```text
# Frontend Delivery Report

## Product
- Goal:
- Target users:
- MVP scope:

## UX
- Primary flow:
- Screens:
- Edge cases:

## UI / Design System
- Tokens:
- Components:
- Responsive rules:

## Implementation
- Stack:
- Routes:
- Components created:
- Pages created:
- API integrations:

## QA
- Lint:
- Typecheck:
- Build:
- Unit tests:
- E2E tests:
- Accessibility:
- Responsive:

## Deployment
- Provider:
- Deployment URL:
- Environment variables:
- Rollback notes:

## Known Issues
- ...

## Next Recommended Iteration
- ...
```

## Master Prompt Template

```xml
<frontend_agent_team_request>
  <project>
    <name>{{PROJECT_NAME}}</name>
    <description>{{PROJECT_DESCRIPTION}}</description>
    <target_users>{{TARGET_USERS}}</target_users>
    <business_goal>{{BUSINESS_GOAL}}</business_goal>
  </project>

  <input_assets>
    <figma>{{FIGMA_LINK_OR_NONE}}</figma>
    <brand_guide>{{BRAND_GUIDE_OR_NONE}}</brand_guide>
    <api_docs>{{API_DOCS_OR_NONE}}</api_docs>
    <existing_repo>{{REPO_LINK_OR_NONE}}</existing_repo>
  </input_assets>

  <requirements>
    <stack>Next.js, TypeScript, React, Tailwind CSS</stack>
    <testing>Playwright E2E, lint, typecheck, build check</testing>
    <deployment>Vercel or custom CI/CD</deployment>
    <accessibility>Keyboard navigation, focus states, contrast, semantic HTML</accessibility>
    <responsive>Mobile, tablet, desktop</responsive>
  </requirements>

  <workflow>
    Run the full frontend agent workflow:
    1. Product requirements
    2. UX flows
    3. UI specification
    4. Design system
    5. Frontend architecture
    6. Component implementation
    7. Page implementation
    8. API integration
    9. QA and accessibility review
    10. E2E tests
    11. CI/CD and deployment
    12. Final code review
  </workflow>

  <output>
    Produce all artifacts, implementation plan, code changes, QA report, deploy report, and final release recommendation.
  </output>
</frontend_agent_team_request>
```
