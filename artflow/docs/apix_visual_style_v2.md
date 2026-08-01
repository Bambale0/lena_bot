# APIX Visual Style v2

## Контекст

APIX Mini App — премиальная AI-галерея и студия генерации внутри Telegram. Главная задача интерфейса: быстро показать визуальный уровень продукта и довести пользователя до действия: открыть работу, повторить, создать, пополнить баланс.

Визуальный стиль строится не на декоративных баннерах, а на контенте: сама лента является hero. Большие прямоугольные промо-блоки над лентой запрещены для feed screen.

## Арт-дирекшн

Ключевые визуальные образы:

- бархатно-чёрный фон;
- magenta / violet / cyan neon;
- glassmorphism;
- glossy reflections;
- black marble;
- premium fashion editorial;
- luxury product photography;
- cinematic cyberpunk noir;
- мягкая глубина, не кислотный UI.

## Цвета

```css
--apx-bg: #08070c;
--apx-bg-2: #050408;
--apx-surface: rgba(20, 17, 26, .72);
--apx-surface-strong: rgba(12, 10, 16, .88);
--apx-text: #f7f5f8;
--apx-muted: #8a8a9a;
--apx-primary: #bb2cff;
--apx-violet: #7b4dff;
--apx-cyan: #00f0ff;
--apx-pink: #ff4d90;
--apx-gold: #ffd700;
```

## Glassmorphism

Glassmorphism in APIX is a surface system, not decoration. The goal is to make controls feel suspended above the media while preserving compact layout.

Required glass rules:

```css
background: rgba(18, 14, 24, .54);
backdrop-filter: blur(18px-24px) saturate(1.2-1.35);
border: 1px solid rgba(255,255,255,.10-.14);
box-shadow: 0 18px 46px rgba(0,0,0,.30-.38), inset 0 1px 0 rgba(255,255,255,.06-.10);
```

Use glass on:

- feed cards;
- bottom glass action rail;
- top bar;
- bottom navigation;
- chips and controls;
- form fields;
- sheets/viewers.

Do not use glass to create new large promo rectangles. Blur must support the central content, not compete with it. If a glass block does not help scanning or action, remove it.

## Типографика

- Brand / large titles: `Playfair Display`, `Cormorant Garamond`, fallback `Georgia`.
- Interface text: `Inter`, `SF Pro`, system sans-serif.
- Body minimum: 14–16px.
- Labels/captions: 11–12px, only for useful metadata.

## Feed screen rule

Feed screen must start fast:

```text
TopBar
Tabs
Content chips
Pinterest feed
```

Do not show:

```text
Главная подборка
Лента
AI-искусство нового поколения
Вдохновляйся...
Large promo card
Duplicate feature card
```

Reason: the user already understands the screen from selected bottom tab and content.

## Cards

- 2-column Pinterest grid.
- Mixed heights: small / tall.
- Radius: 20–24px.
- Border: `1px rgba(255,255,255,.10)`.
- Bottom glass action rail.
- Visual focus is image-first, not caption-first.
- Keep captions short; use metadata only when it affects action.

## Buttons / shadcn-inspired discipline

We use shadcn/ui as a pattern source, not as a runtime dependency.

Required button behavior:

- semantic `button` element;
- focus-visible ring;
- disabled state: `pointer-events: none`, `opacity: .5`;
- stable layout on press;
- transition 150–300ms;
- touch target >= 44px.

## Motion

- Press: scale `.97–.98`, 80–150ms.
- Hover/image lift: transform/opacity only.
- No animation of `width`, `height`, `top`, `left`.
- `prefers-reduced-motion` must be respected.

## Assets

Current text-safe demo assets live in:

```text
artflow/webapp/src/apix/archiveAssets.js
```

They are fallback/demo art only. Production media must come from:

```text
/api/v1/feed
media.apixbotai.com / CDN
```

For exact visual parity with generated PNG art, add optimized binary files separately:

```text
artflow/webapp/public/feed/portrait-neon.webp
artflow/webapp/public/feed/architecture-noir.webp
artflow/webapp/public/feed/fashion-noir.webp
artflow/webapp/public/feed/supercar-rain.webp
artflow/webapp/public/feed/abstract-glass.webp
artflow/webapp/public/feed/product-nocturne.webp
artflow/webapp/public/feed/watch-crystal.webp
artflow/webapp/public/feed/lounge-penthouse.webp
artflow/webapp/public/feed/editorial-sculpture.webp
```

## Screens

### Feed

Content-first. No explanatory masthead. Main CTA is accessible via top create button or bottom nav center.

### Create

May keep title and short helper because the user is entering a task. Use progressive disclosure for advanced settings. Use glass on individual fields and controls, not on one giant form wrapper.

### Prompts

Search-first. Prompt cards are functional objects with one clear action: copy/use.

### Profile

Can use profile card and stats because it is identity/account context, not browsing context.

### Balance

Use sheet/dialog pattern. Keep payment CTA sticky and obvious. Do not create fake invoice route; consume backend payment URL only if provided.

## Quality checks

Before merge:

- no CSS radial-gradient bubbles as feed content;
- no large feed masthead;
- no duplicate feed feature block;
- safe area respected;
- bottom nav does not hide cards;
- glassmorphism uses translucent rgba backgrounds;
- glassmorphism uses backdrop-filter and -webkit-backdrop-filter;
- glass surfaces use soft border and inset highlight;
- glass does not create new bulky rectangles;
- focus-visible exists;
- disabled states exist;
- all main tap targets >= 44px;
- first viewport shows real content cards.
