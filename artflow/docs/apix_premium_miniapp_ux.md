# APIX Premium Mini App UX Architecture

## Контекст

### Цель

Мини-приложение должно быстро доводить пользователя до трёх бизнес-действий:

1. вдохновиться в ленте;
2. запустить генерацию;
3. пополнить баланс после понятного value moment.

Продуктовая задача — увеличить переходы `feed -> create`, `prompt -> create`, `result -> publish/reuse` и снизить визуальный шум, который мешает пользоваться Mini App внутри Telegram.

### Аудитория

Премиальная аудитория 25–45 лет:

- предприниматели, creators, маркетологи, дизайнеры, продюсеры контента;
- ожидают не “игрушку”, а дорогой AI-инструмент;
- ценят скорость, предсказуемость, статусность, понятную стоимость действия;
- не готовы терпеть перегруженные формы и декоративные постеры вместо UI.

### Ограничения платформы

- Telegram Mini App, ширина 320–460 px;
- safe area сверху/снизу;
- тач-таргеты не меньше 44×44;
- bottom navigation в thumb zone;
- системная Telegram-шапка уже существует, поэтому внутренний top chrome должен быть компактным;
- bottom sheet предпочтительнее полноэкранных переходов для оплаты и быстрых действий;
- haptic feedback только на значимых действиях: like, success, error, create.

## Структура

### User Flow

```text
Лента -> карточка -> viewer -> повторить -> создание -> результат -> публикация/ещё вариант
Промпты -> выбрать промпт -> создание -> результат
Профиль -> история -> повторить/опубликовать
Баланс -> пакет -> invoice/payment link
```

### Information Architecture

Основная навигация:

| Экран | Задача | Главный CTA |
|---|---|---|
| Лента | Вдохновение и discovery | Создать / Повторить |
| Создать | Запуск image/video задачи | Создать |
| Промпты | Быстрый старт без пустого листа | Запустить |
| Профиль | История, статус, баланс | Пополнить |
| Результат | Дальнейшее действие после генерации | В ленту / Ещё вариант |

### Wireframe

Экран ленты использует F-pattern:

```text
[compact APIX chrome]
[hero section: message + visual value]
[horizontal tabs]
[featured CTA card]
[2-column Pinterest feed]
[bottom nav with center create]
```

Экран создания использует task-first layout:

```text
[compact APIX chrome]
[hero title]
[mode switch image/video]
[prompt editor]
[model + format controls]
[reference upload]
[CTA create]
```

## Альтернативы ключевых экранов

### Лента — вариант A: Editorial Hero + Pinterest Feed

Плюсы:

- сильное премиальное впечатление;
- хорош для cold start и визуального брендинга;
- быстро объясняет продукт через примеры.

Минусы:

- hero section съедает место;
- нужен строгий контроль высоты, иначе снова появится “постерная крыша”.

### Лента — вариант B: Compact Feed-first

Плюсы:

- больше контента на первом экране;
- быстрее scroll и discovery;
- лучше для активных пользователей.

Минусы:

- слабее brand moment;
- меньше ощущения “дорогого” продукта на первом входе.

Текущая ветка использует компромисс: компактный top chrome + один контролируемый hero section + сразу видимая Pinterest-сетка.

### Создание — вариант A: Single-page Composer

Плюсы:

- минимум шагов;
- пользователь видит цену, модель и prompt сразу;
- меньше time-on-task.

Минусы:

- экран может перегрузиться при большом количестве настроек.

### Создание — вариант B: Stepper/FSM

Плюсы:

- лучше для новичков;
- меньше ошибок ввода;
- проще объяснять ограничения моделей.

Минусы:

- больше кликов до запуска;
- хуже для опытных пользователей.

Текущая ветка использует Single-page Composer с возможностью перейти к stepper позже, если error rate по генерации будет высоким.

## Визуальная концепция

### Цвет

| Token | Значение | Назначение |
|---|---|---|
| `--bg` | `#07050c` | бархатно-чёрный фон |
| `--panel` | `rgba(18,15,25,.76)` | glassmorphism panels |
| `--pink` | `#ff48c6` | розовый неон |
| `--violet` | `#8a36ff` | фиолетовый градиент |
| `--cyan` | `#27e9ff` | холодный контраст |
| `--text` | `#fbf7ff` | основной текст |
| `--muted` | `#b9b1c6` | вторичный текст |

### Типографика

- Заголовки: `Georgia / Playfair-style serif`, 36–45 px, weight 700, letter-spacing до `-0.07em`.
- UI и детали: `Inter / SF Pro / system-ui`, 10–15 px, weight 700–900 для controls.
- Текст промптов: 12–15 px, line-height 1.35–1.45.

### Spacing scale

Используется шкала `4 / 8 / 12 / 16 / 24 / 32`:

- chips: 8–14 px;
- cards gap: 12 px;
- panel padding: 16 px;
- hero padding: 24–28 px;
- bottom nav inset: 12 px + safe area.

### Радиусы

- controls: 14–18 px;
- cards: 20–22 px;
- hero/panels: 28 px;
- bottom nav: 27 px;
- avatar/center CTA: 999 px.

### Компоненты

- `glassmorphism`: верх, nav, карточки, bottom sheets;
- `editorial`: крупные serif-заголовки и hero copy;
- `bento-grid`: карточки prompt/profile/history;
- `Pinterest grid`: двухколоночная feed-сетка с разной высотой;
- `CTA`: центральная кнопка создания и primary gradient actions;
- `affordance`: кнопки действий видимы как touch controls, не как декоративные иконки.

## Интеракции

### Состояния

| Компонент | Default | Active | Disabled | Error | Empty |
|---|---|---|---|---|---|
| Feed card | media + stats | viewer opens | no auth actions muted | fallback art | demo feed вместо пустоты |
| CTA create | gradient | haptic + loading | opacity .55 | toast | prompt required |
| Prompt input | glass field | focused outline | disabled during submit | toast | placeholder with example |
| Topup sheet | plan cards | open link/invoice | unavailable plan muted | toast | fallback demo plans |
| Result | pending state | poll update | — | failed panel | queue message |

### Motion

- карточки появляются с `translateY(16px)` и opacity;
- active tabs получают тонкий neon underline;
- bottom sheet появляется снизу;
- hover используется только как progressive enhancement для web preview;
- `prefers-reduced-motion` отключает animation/transition.

### Mobile behavior

- bottom nav находится в thumb zone;
- primary creation action вынесен в центр;
- viewer и topup открываются bottom sheet/fullscreen overlay;
- pull-to-refresh оставлен платформе/браузеру, не переопределяется;
- haptic feedback на like/create/success/error.

## Метрики успеха

Измерять после деплоя:

1. `feed_card_open_rate` — доля открытий карточки из ленты.
2. `feed_to_create_ctr` — переходы из ленты в создание.
3. `prompt_to_create_ctr` — запуск промптов.
4. `create_submit_rate` — доля пользователей, дошедших до нажатия “Создать”.
5. `generation_error_rate` — ошибки генерации / все попытки.
6. `result_publish_rate` — публикации результата в ленту.
7. `result_reuse_rate` — повторные варианты после результата.
8. `topup_open_rate` и `topup_click_rate` — интерес к оплате.
9. `time_on_task_create` — время от входа в создание до запуска.
10. `NPS / micro feedback` после 3–5 генераций.

Главный критерий: пользователь должен понять ценность за 5–8 секунд и запустить первую генерацию без чтения инструкций.
