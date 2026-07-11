# APIX: актуальная карта frontend-поверхностей

Дата актуализации: 2026-07-11.

Этот документ является каноническим источником для разработчиков и AI-агентов. Если старый документ противоречит этой карте, использовать правила ниже.

## 1. Самостоятельный сайт

Путь в репозитории: `landing/`.

Публичные URL:

- `/` — главная продуктовая страница;
- `/studio.html` — создание изображений, видео и музыки;
- `/models.html` — каталог моделей;
- `/model.html?model=<model_key>` — описание и обучение по модели;
- `/gallery.html` — публичная лента;
- `/account.html` — закрытый кабинет пользователя.

Канонические frontend-файлы:

```text
landing/css/prototype-premium.css
landing/js/prototype-premium.js
```

Файлы `riot-site.*`, `styles.css` и `main.js` считаются архивными/совместимыми. Не добавлять в них новые функции и не использовать их как источник истины.

## 2. Telegram Mini App

Путь в репозитории: `webapp/`.

Стек: React, TypeScript, Vite.

Production URL: `/app`.

Mini App является отдельным клиентом. Изменения standalone-сайта не должны автоматически переноситься в `webapp/`, и наоборот.

## 3. Backend API

Standalone-сайт использует `/api/web/*`:

- auth и профиль;
- модели и тарифы;
- генерации;
- история и очередь;
- feed и prompts;
- billing и referrals;
- assistant;
- admin.

Общие генеративные операции переиспользуют реализацию Mini App через совместимые адаптеры в `api/web/generations.py`.

Realtime endpoint сайта:

```text
/api/web/ws/generations
```

Токен передаётся первым WebSocket-сообщением, а не в URL.

## 4. Защищённые поверхности

Не индексировать:

- `/account.html`;
- `/app` и `/app/*`;
- `/api/*`;
- `/static/upload/*`.

Публичные canonical и sitemap должны использовать домен `https://apixbotai.com`.

## 5. Проверки перед PR

Из директории `artflow/`:

```bash
python -m compileall api bot core db main.py
node --check landing/js/prototype-premium.js
pytest -q
```

Для Telegram Mini App:

```bash
cd webapp
npm ci
npm run build
```

## 6. Правила внесения изменений

1. Не смешивать standalone-сайт и Telegram Mini App в одной задаче без явной необходимости.
2. Не менять обязательные поля существующих `/api/v1/*` контрактов несовместимо.
3. Не хранить auth token, initData и секреты в URL или логах.
4. Цены, модели и способы оплаты получать из API, а не дублировать статическим текстом.
5. Любой production deploy должен зависеть от успешных backend-тестов и frontend-build.
6. Новые пользовательские сценарии должны иметь loading, empty, error и disabled состояния.
