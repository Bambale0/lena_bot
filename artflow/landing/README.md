# APIX Studio standalone web

Актуальная версия публичного сайта обслуживается из `landing/index.html` и работает как vanilla JS SPA через `landing/js/riot-site.js`. До авторизации это премиальная витрина APIX Studio, после входа через Telegram тот же URL переключается в рабочее пространство с быстрым режимом и PRO Studio.

## Актуальная структура

```text
landing/
├── index.html
├── css/
│   └── riot-site.css
├── js/
│   └── riot-site.js
├── images/
│   ├── apix-mark.svg
│   ├── apix-premium-mark.svg
│   ├── apix-premium-studio-hero.png
│   ├── apix-hero-studio-scene.svg
│   ├── apix-campaign-board.svg
│   ├── apix-production-flow.svg
│   ├── apix-reference-motion.svg
│   ├── apix-motion-preview.svg
│   ├── apix-library-system.svg
│   ├── apix-credits-control.svg
│   ├── hero-cinematic-gallery.png
│   ├── apix-showcase.png
│   └── favicon.png
├── media/
└── README.md
```

## Legacy файлы

```text
landing/
├── account.html
├── contact.html
├── features.html
├── guide.html
├── css/styles.css
└── js/main.js
```

Если деплой внезапно показывает старый сайт, сначала проверьте nginx/FastAPI static root и cache: актуальная точка входа должна быть `landing/index.html`, а не одна из legacy-страниц.

## UX-логика

- Гость видит позиционирование APIX Studio, возможности, галерею, тарифы, бизнес-сценарии и вход через Telegram.
- Публичная шапка ведёт по структуре лендинга: возможности, процесс, Studio preview, тарифы, галерея.
- Меню авторизации раскрывается из шапки и ведёт в Telegram Login modal, Quick Create, тарифы и шаблоны.
- Публичная витрина должна быть динамичной: scroll progress, floating navigation, animated hero, hover/tilt cards, reveal-анимации и визуальные секции показывают продукт как живую AI-студию.
- Авторизованный пользователь первым экраном видит крупные действия: создать картинку, оживить фото, сделать видео, изменить фото.
- `Быстро создать` не показывает названия моделей и advanced-параметры; модель выбирается автоматически из доступных `/api/v1/models/*`.
- `PRO Studio` оставляет полный контроль: модель, примеры, формат, качество, количество, длительность видео и очередь.
- `Проекты`, `Моя библиотека`, `Шаблоны`, `Галерея`, `Маркетплейс`, `Баланс`, `Рефералы`, `Настройки` собраны в app-shell с sidebar/topbar.
- WebSocket-статусы генераций продолжают работать через `/api/v1/ws/generations`, с polling fallback.

## Бренд и стиль

Текущая версия использует строгий тёмный premium: графитовая основа, спокойные карточки, тонкие границы и тёплый золотой акцент. Простые экраны говорят человеческими словами, а термины вроде aspect ratio, seed и reference strength остаются в PRO Studio.

`images/apix-premium-mark.svg` заменяет старый неоновый знак на спокойный тёмный mark с тонкими cyan/gold акцентами. Публичные product-visuals используют отдельные SVG-сцены без видимого текста внутри изображений: `apix-hero-studio-scene.svg`, `apix-campaign-board.svg`, `apix-production-flow.svg`, `apix-reference-motion.svg`, `apix-motion-preview.svg`, `apix-library-system.svg` и `apix-credits-control.svg`. Подписи и объяснение остаются в интерфейсе рядом с картинкой, чтобы визуалы не выглядели как технические скриншоты.

## Деплой и ссылки

Если username бота изменится, обновите backend-конфиг, который отдаёт `/api/web/auth/config`. Если сайт обслуживается через FastAPI/nginx из корня `landing/`, относительные пути `css/`, `js/`, `images/` уже готовы.
