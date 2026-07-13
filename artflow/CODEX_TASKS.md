# CODEX TASKS: Artflow production pipeline for Telegram generation bot

## Контекст проекта

Репозиторий: `Bambale0/lena_bot`
Рабочая папка проекта: `artflow/`
Продовый домен: `https://apixbotai.com`
Nginx уже поднят и проксирует backend в Docker Compose service `app` на порт `8000`.
Telegram bot работает через webhook, не через polling.

Важно: mini app и kanban сюда не относятся. Их не трогать.

Цель текущего этапа — довести Telegram-бота генераций до стабильного production-flow:

- пользователь один раз выбирает модель и параметры изображения;
- дальше работает в активной серии: отправляет новые промпты и фото без повторного выбора настроек;
- KIE.AI должен отдавать результаты через webhook, а не через внутренний polling;
- после результата под рукой должны быть кнопки: remix, repeat, animate, settings, new session;
- ошибки должны возвращать кредиты;
- рефералы должны уведомлять пригласившего пользователя.

---

## Текущий стек

- Python 3.11
- FastAPI
- aiogram 3
- PostgreSQL + SQLAlchemy async
- Alembic
- Redis используется для aiogram FSM
- KIE.AI используется для многих image/video generation моделей
- `nano-banana-2` и `nano-banana-pro` используют CometAPI как primary provider
- Telegram webhook endpoint: `settings.WEBHOOK_PATH`
- KIE webhook endpoint должен быть: `settings.KIE_WEBHOOK_PATH`, по умолчанию `/webhook/kie`

---

## Что уже было внесено предыдущим патчем

Проверь, не сломано ли это:

1. В `core/config.py` должны быть настройки:

```python
KIE_WEBHOOK_PATH: str = "/webhook/kie"
KIE_WEBHOOK_SECRET: str = ""
```

2. В `api/kieai_client.py` `create_task()` должен принимать `callback_url` и добавлять в payload поле именно:

```python
payload["callBackUrl"] = callback_url
```

Важно: KIE ожидает ключ `callBackUrl` с большой `B`.

3. В `api/image_service.py` `generate_image()` должен принимать `callback_url`. Для KIE image-моделей он передается в `kieai_client.create_task(...)`; `nano-banana-2` и `nano-banana-pro` идут в CometAPI primary и не вызывают KIE.

4. В `main.py` должен быть endpoint:

```python
@app.post(settings.KIE_WEBHOOK_PATH)
async def kie_webhook(...)
```

5. Добавлен `api/kie_webhook.py` с функциями:

- `extract_task_id(payload)`
- `extract_result_urls(payload)`
- `is_success(payload)`
- `extract_error(payload)`

6. Добавлены модели:

- `ImageSessionStatus`
- `ImageGenerationAction`
- `ImageSession`

7. В `Generation` добавлены поля:

- `task_id` с index
- `image_session_id`
- `parent_generation_id`
- `action_type`

8. Добавлена миграция:

```text
db/migrations/versions/003_image_sessions.py
```

9. В `bot/states/__init__.py` для `ImageGenFSM` должны быть состояния:

```python
model_select
mode_select
image_upload
reference_upload
aspect_ratio_select
count_select
prompt_input
generating
session_active
remix_prompt
session_reference_upload
```

10. В `bot/keyboards/models.py` должна быть функция:

```python
def image_session_kb(gen_id: int | None = None) -> InlineKeyboardMarkup:
```

---

## Главная проблема, которую надо проверить

После патча внешне `/start` выглядит по-старому. Это нормально, потому что start menu пока специально не менялся.

Проверять надо не `/start`, а flow:

1. `/start`
2. `🎨 Изображение`
3. выбрать модель
4. выбрать параметры
5. отправить prompt
6. бот должен написать: задача запущена, результат придёт автоматически
7. KIE должен вызвать `https://apixbotai.com/webhook/kie`
8. бот должен отправить фото пользователю с кнопками активной серии

---

## Обязательные задачи для Codex

### 1. Проверить и исправить KIE webhook callback flow

Файлы:

- `api/kieai_client.py`
- `api/image_service.py`
- `api/video_service.py`
- `main.py`
- `api/kie_webhook.py`
- `bot/handlers/image_gen.py`

Требования:

1. При создании KIE-задачи для изображений обязательно передавать callback URL. Исключение: `nano-banana-2` и `nano-banana-pro`, потому что они маршрутизируются в CometAPI primary.

```python
callback_url = f"{settings.WEBHOOK_URL.rstrip('/')}{settings.KIE_WEBHOOK_PATH}"
```

Если `settings.KIE_WEBHOOK_SECRET` задан, добавить query:

```text
?secret=...
```

2. KIE payload должен содержать:

```json
{
  "callBackUrl": "https://apixbotai.com/webhook/kie"
}
```

3. Внутренний `polling.poll_until_done(...)` в image generation flow больше не использовать.

4. `api/polling.py` можно оставить для старых/fallback сценариев, но новый image flow должен работать через webhook.

5. После `createTask` сохранять `task_id` в `Generation.task_id`.

6. Handler Telegram после createTask должен только сообщить пользователю, что задача запущена. Для KIE-задач результат отправляет KIE webhook; для прямых CometAPI image results backend завершает generation без ожидания KIE webhook.

---

### 2. Сделать KIE webhook устойчивым

Файлы:

- `main.py`
- `api/kie_webhook.py`
- `db/repository.py`

Требования:

1. Webhook endpoint:

```text
POST /webhook/kie
```

2. Должен принимать разные форматы payload от KIE. Не рассчитывать только на один формат.

Обязательные варианты task id:

```python
data.task_id
data.taskId
payload.task_id
payload.taskId
info.task_id
info.taskId
```

Обязательные варианты result urls:

```python
data.result_urls
data.resultUrls
info.result_urls
info.resultUrls
payload.result_urls
payload.resultUrls
data.video_url
data.videoUrl
data.image_url
data.imageUrl
data.url
```

3. Если task id неизвестен:

- залогировать warning;
- вернуть `{"ok": true}`;
- не падать.

4. Если генерация уже `done` или `failed`, webhook должен быть идемпотентным и просто вернуть `{"ok": true}`.

5. Если KIE прислал fail:

- `repo.fail_generation(...)`
- вернуть кредиты пользователю через `repo.add_credits(...)`
- отправить пользователю сообщение об ошибке

6. Если success, но urls пустые:

- считать это ошибкой;
- вернуть кредиты;
- отправить пользователю сообщение.

7. Если success и есть urls:

- сохранить первый URL в `Generation.result_url`
- если есть `image_session_id`, обновить `ImageSession.last_result_url` и `last_generation_id`
- отправить результат в Telegram.

8. Отправка Telegram должна быть в try/except, чтобы webhook не падал из-за Telegram ошибки.

---

### 3. Довести ImageSession flow

Файлы:

- `db/models.py`
- `db/repository.py`
- `bot/states/__init__.py`
- `bot/keyboards/models.py`
- `bot/handlers/image_gen.py`

Цель UX:

Пользователь один раз выбирает модель и параметры. Далее бот должен находиться в активной серии. Пользователь может отправлять:

- новый текст: бот генерирует новую картинку с сохранёнными настройками;
- новое фото: бот сохраняет его как новый reference для серии;
- кнопку remix: бот просит написать, что изменить;
- кнопку repeat: бот повторяет последний prompt;
- кнопку settings: открывает выбор модели/параметров заново;
- кнопку new session: архивирует старую серию и начинает новую.

#### Требования к ImageSession

Модель должна хранить:

```text
id
user_id
model
mode
aspect_ratio
quality
count
base_prompt
reference_file_id
last_result_url
last_generation_id
status
created_at
updated_at
```

#### Требования к Generation

Для каждой генерации хранить:

```text
image_session_id
parent_generation_id
action_type
```

`action_type` варианты:

```text
initial
remix
repeat
reference_update
animate
```

---

### 4. Исправить repeat flow

Сейчас потенциальная проблема: callback `repeat` может просто отправлять пользователю текст последнего prompt, но не запускать генерацию автоматически.

Нужно сделать правильно:

- `repeat` должен сам запускать новую генерацию с последним prompt;
- `action_type = repeat`;
- `parent_generation_id = last_generation_id`;
- настройки брать из `ImageSession`;
- списать кредиты;
- создать `Generation`;
- отправить задачу в KIE с `callBackUrl`;
- сохранить `task_id`;
- сказать пользователю: `Повторяю последнюю генерацию...`.

Не надо заставлять пользователя заново отправлять prompt.

---

### 5. Исправить remix flow

Кнопка `✨ Ремикс` должна работать так:

1. Пользователь нажал remix.
2. Бот пишет: `Напиши, что изменить в текущей картинке`.
3. Следующий текст пользователя запускает генерацию в этой же `ImageSession`.
4. Если `ImageSession.last_result_url` есть, использовать его как reference image URL.
5. Если `last_result_url` нет, использовать `reference_file_id`, если он есть.
6. `action_type = remix`.

Важно: для моделей, которые не поддерживают img2img, нельзя молча отправлять image_url, если это ломает API. Нужно проверить `IMAGE_CAPS` / `_SUPPORTS_IMG2IMG` и корректно решить:

- либо менять модель на edit/i2i аналог;
- либо игнорировать image_url и работать text-to-image;
- либо показать пользователю понятное сообщение.

На MVP можно безопасно: если текущая модель text-only, не передавать `image_url`, но продолжить генерацию по тексту.

---

### 6. Настроить aspect ratio UX

Заказчик просил: `9:16` должно быть впереди.

Проверить `image_aspect_ratio_kb()`:

- если `9:16` есть в списке ratios, кнопка `9:16` должна быть первой;
- остальные ratios не терять.

---

### 7. Добавить понятный UI-текст активной серии

После успешной генерации caption должен объяснять пользователю, что можно продолжать без повторной настройки:

```text
✅ Готово!

<промпт>

🎨 Серия активна.
Теперь просто отправляй новый текст или фото — настройки сохранятся.
```

Под результатом кнопки:

```text
[✨ Ремикс] [🔁 Повторить]
[🎬 Оживить] [⚙️ Настройки]
[🆕 Новая серия] [🏠 Меню]
```

---

### 8. Оживить фото: пока сделать аккуратную заглушку или минимальную интеграцию

Кнопка `🎬 Оживить` сейчас может быть заглушкой. Но она не должна выглядеть как сломанная.

MVP-вариант:

```text
🎬 Оживление фото подключается следующим шагом. Пока можешь открыть раздел Видео и загрузить это изображение.
```

Лучше production-вариант:

- взять `ImageSession.last_result_url`
- выбрать дефолтную image-to-video модель, например `grok-imagine/image-to-video` или другую доступную из `ModelCost`
- создать video `Generation`
- передать `callBackUrl` в KIE video createTask
- результат отдать через тот же `/webhook/kie`

Но если не хватает времени, оставить понятную заглушку. Не делать полурабочую магию.

---

### 9. Реферальные уведомления

Файл:

- `bot/middlewares/auth.py`

Сейчас реферальные бонусы начисляются, но нужно уведомлять пригласившего.

Проблема: middleware сейчас не получает `bot` явно в зависимости от порядка/контекста. Нужно проверить aiogram data: скорее всего `bot` доступен в `data["bot"]` или через event context.

Требование:

Когда новый пользователь пришёл по referral code:

1. Создать нового пользователя.
2. Начислить L1 бонус referrer.
3. Отправить referrer сообщение:

```text
🎉 По твоей ссылке пришёл новый пользователь!
+20 кредитов начислено.
```

4. Если есть L2 referrer:

```text
🎉 По второй линии пришёл новый пользователь!
+10 кредитов начислено.
```

5. Ошибки отправки уведомления логировать, но не ломать регистрацию.

---

### 10. Проверить Alembic

Файлы:

- `db/migrations/versions/003_image_sessions.py`
- `db/models.py`

Требования:

1. `alembic upgrade head` должен проходить без ошибок.
2. Если в базе уже есть индекс на `generations.task_id`, миграция не должна падать.
3. Если enum уже создан, миграция не должна падать.
4. Если таблицы создавались через `Base.metadata.create_all`, а потом запускается Alembic, не должно быть конфликта.

Важный момент: в текущем `main.py` раньше был `Base.metadata.create_all`, но в актуальном main это вроде убрано и остался `run_seed()`. Проверить. В prod лучше не создавать таблицы через `create_all`, использовать Alembic.

---

## Проверки после изменений

### Static checks

Из папки `artflow/`:

```bash
python -m compileall core api db bot main.py
```

### Migration

```bash
alembic upgrade head
```

### Service restart

```bash
docker compose up -d --force-recreate app
docker compose logs -f app
```

### Health check

```bash
curl -i https://apixbotai.com/api/v1/health
```

Ожидаемо:

```json
{"status":"ok","service":"apix"}
```

### KIE webhook smoke test

Этот запрос должен вернуть `200` и `{"ok":true}`. В логах допустим warning `unknown task_id=test`, это нормально.

```bash
curl -i -X POST "https://apixbotai.com/webhook/kie" \
  -H "Content-Type: application/json" \
  -d '{"taskId":"test","code":200,"data":{"resultUrls":["https://example.com/test.jpg"]}}'
```

Если используется `KIE_WEBHOOK_SECRET`, тестировать так:

```bash
curl -i -X POST "https://apixbotai.com/webhook/kie?secret=$KIE_WEBHOOK_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"taskId":"test","code":200,"data":{"resultUrls":["https://example.com/test.jpg"]}}'
```

### End-to-end bot check

1. Открыть Telegram bot.
2. `/start`.
3. Нажать `🎨 Изображение`.
4. Выбрать модель.
5. Выбрать параметры.
6. Ввести prompt.
7. Бот должен ответить, что задача запущена.
8. В логах должно быть сохранение task_id.
9. После callback от KIE бот должен отправить изображение.
10. Под изображением должны быть кнопки активной серии.
11. Написать `добавь дождь и неоновый свет`.
12. Бот должен запустить новую генерацию без повторного выбора настроек.

---

## Не трогать в этой задаче

- Mini App
- Kanban
- Drag and drop
- Личный ассистент
- Внешний UI
- Marketplace промптов, кроме случаев, где он ломает импорт/роутинг
- Midjourney flow, кроме если он ломается из-за общих моделей/репозитория

---

## Ожидаемый результат

После выполнения задачи бот должен ощущаться как Syntx/Matrix workflow:

- один раз настроил;
- получил результат;
- дальше просто пишешь правки или отправляешь новые фото;
- результат приходит автоматически по webhook;
- кнопки действия всегда рядом;
- кредиты не теряются при ошибках;
- реферал получает уведомление.

---

## Рекомендация по реализации

Не делать огромный рефакторинг всего проекта. Работать точечно:

1. KIE webhook stability.
2. ImageSession correctness.
3. Repeat/remix correctness.
4. Referral notification.
5. UX text.
6. Tests/smoke checks.

Если нужно менять сигнатуру `repo.create_generation`, проверь все места вызова:

```bash
grep -RIn "create_generation(" . --exclude-dir=__pycache__
```

Сигнатура должна быть backward-compatible через optional kwargs, чтобы не сломать video/midjourney/marketplace.
