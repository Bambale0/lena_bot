# APIX Frontend Agent Handoff

Дата: 2026-05-25

Этот handoff фиксирует, как применять MCP prompts к standalone web Studio в `landing/`.

## MCP Prompt Discovery Status

Запросы через `prompts_chat.search_prompts`:

- `premium minimalist landing page frontend design`;
- `luxury SaaS website UI design prompt`;
- `frontend developer design system prompt dark premium minimal`.

Результат: готовые публичные prompts не найдены (`count: 0`). `prompts_chat.improve_prompt` недоступен без API key (`Authentication required`). Поэтому ниже зафиксированы локальные рабочие prompts, составленные для frontend-агентов на основе текущего продукта и применяемые как source of truth до появления MCP prompt library.

## Applied MCP-Inspired Prompts

- `Modern Web Development Assistant`: реализовывать production-ready web UI без смены стека, с чистым HTML/CSS/JS и проверками.
- `AI-First Design Handoff Generator`: держать изменения как систему компонентов, состояний, токенов, accessibility и route contracts.
- `Architecture & UI/UX Audit`: перед кодом проверять IA, layout hierarchy, visual consistency, state coverage и design debt.
- `Design System Consistency Auditor`: после изменений сканировать typography, spacing, colors, buttons, inputs, cards, navigation and one-off styles.

## Current Creative Direction

Ключевой вектор: минимализм, premium, elegant, bright/saturated.

Это не означает бледный monochrome и не означает ярмарочный neon. Насыщенность должна идти через:

- глубокий dark-first фон;
- точный контраст светлого текста;
- ограниченные cyan/mint/gold accents;
- тонкие border/highlight линии;
- refined glass, controlled reflections, editorial lighting;
- уверенную плотность интерфейса без декоративной “мультяшности”.

Запрещённые ощущения:

- `мыльница из мультика`;
- toy-like cards;
- over-rounded pills;
- cheap neon;
- generic gradient blobs;
- syrup purple-blue dominance;
- stock-like visuals;
- лишние маркетинговые hero-карточки внутри рабочего app-shell.

## Frontend Agent Prompt: Visual System

```text
Ты frontend visual design worker для APIX Studio.

Scope: редактируй только `landing/css/riot-site.css`.

Цель: довести landing + authenticated Studio до minimal premium AI creative SaaS / editorial production tool.

Visual direction:
- dark-first, elegant, saturated, high-contrast;
- fewer bubble/pill forms, moderate radii;
- refined glass and metal surfaces;
- cyan/mint/gold accents only where they clarify hierarchy;
- subtle purposeful animation, no decorative noise;
- premium density: fewer oversized marketing shapes in app-shell.

Avoid:
- cartoon / toy / glossy candy look;
- cheap neon;
- generic purple gradient blobs;
- over-rounded CTA pills;
- low-contrast gray-on-gray;
- one-off styles that break the system.

Work areas:
- topbar/buttons/auth menu;
- hero stage and trust bar;
- showcase cards;
- visual workflow wall;
- quick cards;
- pricing cards;
- app shell, sidebar, studio composer;
- mobile breakpoints.

Acceptance:
- no text overlap on 390px mobile and desktop 1440px+;
- sticky header feels premium and quiet;
- visual assets look informational, not decorative stock;
- `prefers-reduced-motion` remains respected;
- no new dependencies.
```

## Frontend Agent Prompt: Content UX

```text
Ты frontend content UX worker для APIX Studio.

Scope: редактируй только `landing/js/riot-site.js`.

Цель: RU/EN copy для AI image/video/music generation web studio: user-friendly, concise, premium, not generic.

Product truths to communicate:
- Telegram login opens the web studio without password;
- Quick Create is task-first;
- PRO Studio gives model/settings/reference control;
- supported surfaces: image, video, music;
- users can upload references;
- queue/statuses make generation trackable;
- credits/billing are visible;
- library/gallery/remix make results reusable.

Tone:
- RU: живой продуктовый русский, без канцелярита и лишнего англо-мусора;
- EN: concise premium SaaS tone;
- short CTAs, clear labels;
- no vague “AI magic”;
- no guaranteed timings unless backend guarantees them;
- no repeated blocks saying the same thing.

Acceptance:
- every public section has a distinct job;
- RU/EN switch changes content coherently;
- authenticated screens explain action and state, not marketing;
- no backend route or business logic changes.
```

## Frontend Agent Prompt: Visual Assets

```text
Create project-bound visuals for APIX Studio.

Style:
- premium minimal dark UI;
- saturated but controlled cyan/mint/gold accents;
- editorial AI production board mood;
- informative system diagrams, not cute illustrations;
- no readable text inside images;
- no logos;
- no generic stock-photo look;
- no glossy toy/cartoon look.

Asset needs:
1. Campaign board: prompt + reference + generated asset + publish queue.
2. Reference to video: source frame, motion direction, output preview.
3. Asset library: reusable results, versions, gallery/remix state.
4. Credits control: balance, cost, active queue, status.

Use these as web product visuals, not ads.
```

## Local Stack Constraint

Инструкция рынка рекомендует Next.js, Motion for React и `next/image`, но текущая production-поверхность сайта реализована как vanilla SPA в `landing/`.
До отдельного migration task агент должен развивать текущий стек:

- frontend site: `landing/index.html`, `landing/js/riot-site.js`, `landing/css/riot-site.css`;
- app routes: hash routes;
- backend web API: `/api/web/*`;
- generation API: `/api/v1/*`;
- Telegram mini app не трогать.

## Route Contract

- canonical Studio route: `/#/studio`;
- supported alias: `/#/pro`;
- deep links: `/#/studio/image`, `/#/studio/video`, `/#/studio/music`;
- Quick deep links: `/#/quick/image`, `/#/quick/animate`, `/#/quick/video`, `/#/quick/edit`.

## Studio Layout Contract

Studio должна читаться как рабочая среда:

- top: task tabs for Image, Video, Midjourney, Music, Batch, Motion;
- left: project/session context, mode rail, version tree;
- center: canvas preview, launch status, prompt/model/settings/review form;
- right: inspector, selected model, step navigation, sequence state;
- bottom: queue dock.

## Acceptance Checklist

- Quick Create always exposes four large task entries.
- Quick result state includes an accessible status region.
- Studio has no hidden single-form feel: project, preview, inspector, versions and queue are visible.
- Queue updates remain non-blocking and have live status labels.
- Uploads validate type and 20 MB size before sending.
- `prefers-reduced-motion` remains respected in CSS.
- No neon-heavy palette drift; primary accent stays controlled gold/champagne.
- `tools/codex_static_checks.sh` passes before delivery.
