# APIX Web Studio Frontend

Документ фиксирует текущее устройство публичного сайта APIX и выводы после ревью интерфейса. Сайт не заменяет Telegram-бот и не трогает Telegram WebApp: это отдельный web-слой для домена `apixbotai.com`.

## Поверхности

| Поверхность | Путь | Назначение |
|---|---|---|
| Публичный сайт | `/` | Витрина до авторизации и рабочая студия после входа |
| Web API | `/api/web/*` | Профиль, лента, промпты, планы, web-auth |
| Генерация | `/api/v1/generate/*` | Запуск image/video/music задач из web-студии |
| Каталог моделей | `/api/v1/models/*` | Реальные модели и их параметры для выбора в студии |
| Mini App | `/app` | Telegram WebApp, отдельный React-интерфейс |

`landing/` содержит vanilla JS сайт. `webapp/` содержит mini app. Эти поверхности нельзя смешивать: сайт должен иметь собственный workflow генерации, а mini app оставаться самостоятельным.

## MCP Для Frontend-Агентов

- Для любой frontend/UI задачи агент должен сначала свериться с `shadcn` MCP: компоненты, паттерны, формы, навигация, диалоги, карточки, empty states и layout primitives.
- Для документации по библиотекам, браузерным API, тестам и best practices агент должен использовать `Context7` MCP.
- Если MCP-инструменты не видны в текущей Codex-сессии, нужно перезапустить Codex после обновления `~/.codex/config.toml`; в отчете указать, что MCP был недоступен в этой сессии.
- Ключи MCP не добавлять в `landing/`, `webapp/`, docs, screenshots или build artifacts.

## UX-Архитектура

До авторизации сайт работает как презентация продукта:

- понятное объяснение возможностей без технического жаргона;
- примеры работ и сценариев использования;
- библиотека идей и промптов как витрина;
- вход через Telegram.

После авторизации интерфейс переключается в рабочую студию:

- баланс и профиль пользователя;
- создание image/video/music задач;
- выбор модели из реального каталога;
- пошаговый FSM-процесс: идея → медиа → настройки → запуск;
- загрузка фото-референса через `/upload` для image/video сценариев;
- просмотр фото, видео и аудио результатов в карточках без перехода в mini app;
- лента работ;
- библиотека промптов;
- история генераций и тарифы.

## Frontend Architecture После Аудита

Standalone frontend развивается как production-студия, а не как набор разрозненных форм. Основной пользовательский цикл:

```text
идея -> референсы -> модель -> настройки -> проверка -> очередь -> история -> следующий шаг
```

Реализованные frontend-компоненты в `landing/js/riot-site.js`:

| Компонент | Назначение |
|---|---|
| `ModeSwitch` | Выбор потока: image, video, music, assistant |
| `StudioStepper` | Последовательный FSM: idea, media, model, settings, review |
| `ModelPicker` | Список реальных моделей с поиском, бейджами возможностей и ценой |
| `ReferenceUploader` | Загрузка JPG/PNG/WebP через `/upload`, URL-ввод и preview |
| `PromptEditor` | Текст идеи, улучшение через `/api/v1/prompt/improve`, prompt-from-photo |
| `DynamicSettings` | Настройки, построенные из capabilities выбранной модели |
| `ReviewPanel` | Сводка перед запуском: поток, модель, стоимость, refs, prompt |
| `QueuePanel` | Локальная очередь задач, polling и переход результата в следующий шаг |
| `GenerationCard` | Единое отображение image/video/music в истории и очереди |

Архитектура вдохновлена shadcn-паттернами `sidebar`, `tabs`, `form`, `sheet/drawer`, `card`, `badge`, `select`, `progress`, `toast`, но реализована в текущем vanilla JS стеке без миграции на React.

## Sequential Generation

Последовательная генерация реализована на frontend orchestration layer без изменения backend:

1. Пользователь запускает image/video/music через существующий `/api/v1/generate/*`.
2. Ответ `GenerationOut` сохраняется в `localStorage` под ключом `apix_generation_queue`.
3. Frontend poll-ит `GET /api/v1/generations/{id}` каждые 4.5 секунды для активных статусов `pending/processing/queued/running`.
4. Когда статус становится `done`, результат можно отправить в следующий шаг:
   - image -> image variation: `reference_url = previous.result_url`;
   - image -> video: `image_url = previous.result_url`, `mode = image`;
   - any result -> reuse prompt: prompt переносится в соответствующий поток;
   - feed item -> studio remix/reference через существующий web state.
5. Следующий шаг не запускается автоматически. Пользователь видит review summary и подтверждает запуск.

Это сохраняет предсказуемость, не обходит кредитную систему и не конфликтует с backend-лимитом активных генераций.

### Queue State

Локальная queue item schema:

```json
{
  "local_id": "q_timestamp_random",
  "gen_id": 123,
  "mode": "image",
  "model": "model-key",
  "prompt": "user idea",
  "status": "pending",
  "result_url": null,
  "result_urls": [],
  "credits_spent": 2,
  "created_at": "ISO",
  "updated_at": "ISO",
  "source": "studio"
}
```

Queue не заменяет backend history. Это UX-слой восстановления активных задач после refresh и удобный мост к следующей генерации. Источник истины по готовности остаётся `GET /api/v1/generations/{id}` и `/api/v1/history`.

## Backend Endpoint Contract Для Сайта

Сайт использует два API-слоя:

| Слой | Назначение |
|---|---|
| `/api/web/*` | Web-friendly обёртка `{ ok, data }`: auth, profile, public feed/prompts, plans, image sessions |
| `/api/v1/*` | Существующий miniapp/generation API, который также принимает `X-Web-Auth-Token` |

Основные endpoints студии:

| Метод | Путь | Использование |
|---|---|---|
| GET | `/api/v1/models/image` | Реальные image-модели и capabilities |
| GET | `/api/v1/models/video` | Реальные video-модели, duration/resolution/mode options |
| GET | `/api/v1/models/music` | Реальные music-модели |
| POST | `/api/v1/generate/image` | Запуск изображения |
| POST | `/api/v1/generate/video` | Запуск видео |
| POST | `/api/v1/generate/music` | Запуск музыки |
| GET | `/api/v1/generations/{id}` | Polling статуса и результата |
| GET | `/api/v1/history` | История пользователя |
| POST | `/api/v1/prompt/improve` | Улучшение prompt |
| POST | `/api/v1/photo-prompt` | Prompt по загруженному фото |
| POST | `/api/v1/feed/{id}/remix` | Ремикс публичной работы через скрытый prompt |
| POST | `/upload` | Загрузка reference image |

Важная деталь: для image refs frontend отправляет `reference_url` как основной ref и `reference_urls` только для дополнительных refs. Один и тот же URL нельзя дублировать в обоих полях, иначе backend воспримет один ref как два.

## UX Правила Студии

- На экране студии всегда один главный шаг за раз.
- Пользователь должен видеть выбранную модель, цену и ограничения до запуска.
- Модельные настройки показываются только если модель реально отдаёт capability.
- Для image/video refs показывать preview, remove action и понятные ошибки формата.
- Для video image-only моделей шаг Media становится обязательным.
- После запуска задача остаётся видимой в QueuePanel, а не только в toast.
- Готовый image result должен иметь действия `Вариант` и `Видео`.
- История и очередь должны позволять `Reuse idea`, `Variant`, `Animate`.
- Feed должен быть входом в студию: `Как референс` и `Ремикс`.

## Типографика

Comic Sans не используется глобально. Базовый интерфейс должен оставаться читаемым: `Arial, Helvetica, sans-serif`.

Comic Sans допустим только как акцент:

- стикеры и короткие бейджи;
- постерные декоративные блоки;
- заголовки и переключатели внутри бокового выбора моделей.

Поля форм, навигация, карточки, длинные тексты, промпты, цены и технические статусы остаются в обычном читаемом шрифте.

## Выбор Моделей

Студия загружает реальные списки моделей после авторизации:

- `/api/v1/models/image`;
- `/api/v1/models/video`;
- `/api/v1/models/music`.

Выбранная модель синхронизируется с формой генерации. UI должен показывать человекочитаемые названия и сценарии, а не заставлять пользователя разбираться в сыром id модели. Технические параметры можно скрывать за аккуратными бейджами или настройками.

## Анализ Текущего Фронта

Найденные проблемы:

- Comic Sans был применен слишком широко и снижал читаемость карточек.
- Сырые названия моделей визуально доминировали над задачей пользователя.
- Карточки работ нуждаются в более стабильной иерархии: превью, короткий результат, модель, стоимость.
- На витрине нужны более сильные реальные примеры вместо длинных фрагментов промптов.
- После логина студия уже отделена от витрины, но ей нужны более явные состояния загрузки, ошибок и пустых списков.
- Двухъязычность есть, но контент примеров и microcopy нужно довести до одинакового качества на RU и EN.

## Предлагаемые Улучшения

1. Добавить человекочитаемые alias-имена моделей рядом с их реальными id.
2. Собрать curated gallery из реальных удачных генераций для публичной витрины.
3. Сделать drawer деталей промпта: пример результата, цена, кнопка применить.
4. Разделить публичные тексты и app microcopy в `landing/js/riot-site.js` по смысловым секциям.
5. Добавить визуальный smoke-тест Playwright для `/` и авторизованного состояния через dev-token.
6. Завести короткий checklist перед деплоем: CSS fonts, `/app` smoke, `/api/web/health`, root static, Telegram Login domain.

## Реализовано В Итерации

- Route-aware загрузка данных: сайт больше не перезапрашивает все публичные и приватные ресурсы на каждый `hashchange`.
- Защита от гонок render/load через `AbortController` и номер актуального render-прохода.
- Авторизованный `/` корректно догружает данные для dashboard: модели, баланс и историю.
- Студия использует единый helper для id модели, поэтому поддерживает ответы API с `key` и `model_key`.
- `prompt-use` больше не зависит от `setTimeout`: выбранная идея сохраняется в состоянии и переносится в форму после render студии.
- Action-кнопки и формы получили busy/disabled защиту от повторных кликов и двойной отправки.
- Статусы, toast и активная навигация получили базовую доступность через `aria-current`, `aria-live`, `role=status` и `role=alert`.
- CSS получил focus-visible, disabled, busy, loading, skeleton и status hooks.
- Mobile layout для hero, poster wall, studio и model list стал устойчивее к узким экранам.
- Добавлена поддержка `prefers-reduced-motion`.
- Студия переведена на user-friendly FSM: выбор потока, понятные шаги, левый навигатор, центральный workbench, правый preview/status sidebar.
- Добавлены inline SVG-иконки для режимов, шагов, загрузки, preview и проверки перед запуском.
- Добавлена работа с фото: загрузка JPG/PNG/WebP через `/upload`, preview референса, удаление референса, подстановка URL в image/video запросы.
- Карточки ленты/истории умеют показывать video/audio previews и не показывают битый alt-текст при недоступном изображении.
- Настройки студии динамически пересобираются под выбранную модель и её capabilities: text/image режимы, форматы, качество, count, длительность, разрешение, motion options, max refs и подсказки по обязательному фото.
- Студия получила явный шаг `Модель` между референсами и настройками.
- Добавлены review summary, оценка стоимости и предупреждения перед запуском.
- Добавлена локальная очередь генераций с polling `/api/v1/generations/{id}`.
- Добавлены sequential actions: reuse idea, image variant, animate image to video.
- Добавлены действия feed -> studio: use as reference и remix.
- Добавлены prompt improve и photo-to-prompt в шаге идеи.
- Исправлен frontend payload для image refs: основной ref не дублируется в `reference_urls`.

## CSS Hooks

Standalone site CSS поддерживает общие состояния без изменений JS-контрактов:

- `:focus-visible` для ссылок, кнопок, form controls, tab controls и карточек моделей;
- `.loading` / `.is-loading` для временной блокировки секций во время загрузки;
- `.skeleton` / `.is-skeleton` для placeholders в списках, карточках и превью;
- `.status-message` / `.status` с модификаторами `.is-success`, `.is-error`, `.is-warning`;
- `.is-busy` или `aria-busy="true"` для кнопок с визуальным busy state;
- `.is-disabled`, `disabled` или `aria-disabled="true"` для disabled-состояний кнопок.

## Правила Безопасных Изменений

- Не менять Telegram bot flows при работе над сайтом.
- Не менять KIE webhook и payment webhooks без отдельной задачи.
- Не ломать `/app`: mini app живет отдельно.
- Не подменять реальные модели фиктивными, если экран предназначен для авторизованной студии.
- Перед финалом запускать `tools/codex_static_checks.sh`.
