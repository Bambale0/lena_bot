# APIX AI landing

Готовый статический сайт APIX AI: главная, возможности, инструкция, веб-кабинет генерации и контакты.

## Структура

```text
landing/
├── index.html
├── features.html
├── guide.html
├── account.html
├── contact.html
├── css/
│   └── styles.css
├── js/
│   └── main.js
├── images/
│   ├── apix-mark.svg
│   ├── hero-cinematic-gallery.png
│   ├── guide-contact-flow.png
│   ├── avatar-neon-orbit-01.png
│   ├── avatar-neon-orbit-02.png
│   ├── avatar-neon-orbit-03.png
│   ├── icon-all-formats.svg
│   ├── icon-fast-flow.svg
│   ├── icon-models.svg
│   ├── icon-control.svg
│   ├── chat-demo-accent.svg
│   └── favicon.png
├── fonts/
├── media/
└── README.md
```

## Бренд и стиль

Актуальная версия использует неоновый знак APIX без фоновой подложки. В нём считываются световая дуга, энергия генерации и движение от идеи к готовому медиа. Основная эмоция — технологичная креативность: продукт выглядит быстрым, визуальным и достаточно премиальным для рабочих задач.

В вебе айдентика перенесена через hero-постер, неоновую палитру `cyan / pink / mint / violet`, тонкие световые контуры, прозрачный логотип, SVG-иконки без фоновых плиток и AI-сгенерированные изображения в едином cinematic/editorial стиле. Секции после первого экрана светлые, чтобы сайт ощущался как витрина креативной студии, а не админ-панель.

## Сгенерированные изображения

Изображения созданы через встроенный генератор изображений и сохранены в проект:

- `images/hero-cinematic-gallery.png` — hero-постер с Telegram-чатом и медиа-панелями.
- `images/guide-contact-flow.png` — иллюстрация пути от сообщения к AI-медиа.
- `images/avatar-neon-orbit-01.png`, `02.png`, `03.png` — абстрактные аватарки отзывов без реалистичных лиц.

Иконки и декоративный акцент сделаны вручную в SVG, чтобы сохранить чистую геометрию и быстрый рендер.

## Рассмотренные концепции

1. **Neon Studio** — эмоциональный лендинг с сильным визуальным образом и крупными примерами генераций.
2. **Creative Console** — рабочая витрина продукта: чат-демо, команды, режимы, гайд и поддержка.
3. **Prompt Market** — акцент на библиотеке промптов, авторах, ремиксах и витрине работ.
4. **Telegram Native** — максимально похожий на Telegram-интерфейс с мягкой обучающей подачей.
5. **Cinematic Gallery** — первый экран как постер с AI-визуалом, далее светлая editorial-галерея с тонкими линиями и неоновыми маркерами.

Текущая версия переведена на концепцию **Cinematic Gallery**: она оставляет APIX технологичным и неоновым, но выглядит менее как dashboard и больше как современная витрина креативного продукта.

## Как заменить ссылки

Сейчас в HTML используются:

- бот: `https://t.me/apix_ai_bot`
- веб-кабинет: `account.html`
- канал: `https://t.me/lelupromt`
- саппорт: `https://t.me/LeLu88`
- разработчик: `https://t.me/Chillcreative`
- email: `happyarbuznik@gmail.com`

Если username бота изменится, замените `https://t.me/apix_ai_bot` во всех HTML-файлах. Если сайт обслуживается через FastAPI/nginx из корня `landing/`, относительные пути `css/`, `js/`, `images/` уже готовы.

Для корректных Telegram/social preview после деплоя замените относительные `og:image` на абсолютный URL, например `https://your-domain.ru/images/hero-cinematic-gallery.png`.

## Форма связи

Форма на `contact.html` валидируется на стороне клиента и имитирует успешную отправку. Для реального запуска можно подключить:

- отправку в Telegram через backend endpoint;
- отправку в CRM;
- email provider;
- Google Forms или иной внешний webhook.

В `js/main.js` найдите обработчик `contactForm.addEventListener("submit", ...)` и замените блок успеха на `fetch()` к вашему endpoint. Токены бота нельзя хранить в frontend-коде: они должны оставаться на сервере.

## Контент

Тексты основаны на текущем коде проекта: `README.md`, `core/config.py`, `db/seed.py`, `bot/handlers/start.py`, `bot/ui/main_menu.py`, `bot/handlers/assistant.py`, `bot/handlers/feed.py`, `bot/handlers/marketplace.py`.

Для тарифов и моделей использованы значения из seed-конфига, поэтому перед публичным релизом стоит сверить их с продакшен-базой, если цены редактировались через админку.
