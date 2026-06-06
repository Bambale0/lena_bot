# APIX Studio standalone site

Актуальная версия публичного сайта и web-кабинета обслуживается из `landing/` как набор статических страниц на общем vanilla JS/CSS слое:

```text
landing/
├── index.html              # продуктовый вход и сценарии создания
├── studio.html             # создание картинок, видео и музыки
├── models.html             # каталог моделей
├── model.html              # динамическая страница модели: обучение, FAQ, примеры
├── gallery.html            # галерея и живые примеры
├── account.html            # кабинет: очередь, библиотека, баланс, рефералы, помощник
├── features.html           # совместимая страница возможностей в новом стиле
├── guide.html              # совместимая страница маршрута создания в новом стиле
├── contact.html            # совместимая страница поддержки в новом стиле
├── css/prototype-premium.css
├── js/prototype-premium.js
├── data/
└── images/
```

`index-riot-backup.html` и `prototype-premium.html` редиректят на `/`, чтобы прямые старые ссылки не показывали другой визуал. `css/riot-site.css`, `js/riot-site.js`, `css/styles.css` и `js/main.js` оставлены только как архив/референс. Новые правки публичного сайта нужно делать в `prototype-premium.css` и `prototype-premium.js`.

## UX-логика

- Сайт не является одностраничным лендингом: основные сценарии разведены по отдельным страницам.
- Верхнее меню отвечает только за разделы продукта: главная, создание, галерея и модели. Кабинет вынесен в правый блок аккаунта, чтобы не дублировать навигацию.
- Продуктовое меню на главной ведёт только в сценарии создания: картинка с нуля, фото по примеру, улучшение фото, видео и музыка.
- В `studio.html` выбор устроен в два уровня: сначала формат результата, затем сценарий картинки. Для видео и музыки второй уровень скрывается.
- `studio.html?type=image&flow=text` открывает создание картинки с нуля.
- `studio.html?type=image&flow=reference` открывает сценарий с фото-примером.
- `studio.html?type=image&flow=edit` открывает улучшение фото.
- `model.html?model=<model_key>` открывает обучение по конкретной модели: возможности, лайфхаки, FAQ, примеры и переход в Studio с готовым тестом.
- `account.html#billing`, `account.html#assistant`, `account.html#library` открывают нужные вкладки кабинета.
- Telegram Login создаёт web-token и сайт работает через `/api/web`.
- Реальные генерации идут через `/api/web/generate/image`, `/api/web/generate/video`, `/api/web/generate/music`.
- Статусы задач приходят по `/api/web/ws/generations`; токен передаётся первым auth-сообщением после открытия WebSocket.

## Дизайн

Текущий визуальный язык: тёмная premium-основа, лилово-розово-синие акценты, реальные bitmap-примеры генераций, плавные карточки, единые dropdown-контролы и компактный app-like кабинет. Все видимые страницы в `landing/*.html` должны подключать `css/prototype-premium.css` и `js/prototype-premium.js`.

## Проверка

```bash
node --check landing/js/prototype-premium.js
tools/codex_static_checks.sh
```
