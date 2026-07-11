# QA Checklist — APIX Site and Mini App

Дата актуализации: 2026-07-11.

## 1. Public site

- `/` открывается без ошибок.
- Hero объясняет продукт и ведёт в реальный сценарий.
- `/studio.html`, `/models.html`, `/model.html` и `/gallery.html` открываются.
- Feed и модели загружаются либо показывают понятное empty/error состояние.
- Цены и доступность моделей приходят из API.
- Canonical и social preview используют `https://apixbotai.com`.
- `/account.html` отсутствует в sitemap и закрыт от индексации через robots policy.

## 2. Авторизация

- Гость не может запускать генерации и административные действия.
- Telegram Login работает и создаёт защищённую сессию.
- Email/password flow показывает понятные ошибки и retry state.
- В production отключён `X-Dev-Tg-Id` fallback.
- Cookie авторизации имеет `HttpOnly`, `SameSite=Lax` и `Secure` в production.
- В URL и логах отсутствуют `token=`, `init_data=` и `initData=`.
- После входа сохраняется выбранный `type`, `flow`, `model` и prompt draft.

## 3. Studio

- Тип результата и сценарий выбираются предсказуемо.
- Обязательные поля валидируются до запуска.
- Кнопка запуска заблокирована до заполнения обязательных данных.
- Модель, параметры и стоимость видны до списания.
- Готовый пример prompt не находится в textarea как пользовательское значение.
- Загрузка JPEG, PNG и WebP работает; неподдерживаемый файл отклоняется.
- Ошибки API отображаются рядом с формой или понятным уведомлением.
- На viewport 390 px нет горизонтального скролла и перекрытий.

## 4. Генерации и очередь

- После запуска появляется элемент очереди.
- WebSocket получает auth первым сообщением, без токена в URL.
- При потере WebSocket включается polling fallback.
- Статусы `pending`, `processing`, `done`, `failed` отображаются корректно.
- Ошибка провайдера возвращает кредиты один раз.
- Повторный webhook не завершает и не оплачивает операцию повторно.
- Готовый результат обновляет историю и баланс без ручного refresh.

## 5. Результаты

- Отображаются image, video и music результаты.
- Все элементы `result_urls` доступны пользователю.
- Сломанная media URL показывает fallback, а не ломает страницу.
- Скачивание доступно только владельцу генерации.
- Publish, share, remix и повторный запуск защищены от двойного клика.

## 6. Feed и prompts

- Фильтры ленты работают.
- Like/share/remix имеют busy state.
- Неподдерживаемое действие отключено с объяснением.
- Prompt library загружается и применяет идею в Studio.
- Submit flow показывает `pending`, `approved` и `rejected`.
- Администратор может модерировать prompt; обычный пользователь — нет.

## 7. Billing и referrals

- Показываются только включённые способы оплаты.
- Повторный клик не создаёт несколько независимых pending-операций.
- Webhook подтверждает платёж идемпотентно.
- Статусы `pending`, `paid`, `failed`, `refunded` видны пользователю.
- После успешной оплаты баланс обновляется без refresh.
- Реферальная цепочка не допускает самореферал и циклы.
- Комиссии корректно начисляются и откатываются при refund.

## 8. Admin

- Admin-раздел виден только пользователям из `ADMIN_IDS`.
- Не-admin получает 403 от административных API независимо от скрытия кнопки.
- Поиск пользователей и генераций работает.
- Изменение баланса и тарифов фиксируется в audit/ledger.
- Reject требует причины.
- Опасные действия имеют подтверждение.

## 9. Telegram Mini App

- `/app` отдаёт собранный React/Vite frontend.
- Telegram initData проверяется на backend.
- Прямое открытие вне Telegram показывает корректный fallback.
- Bottom navigation, safe area и клавиатура телефона не перекрывают форму.
- Build проходит командой `npm run build`.

## 10. Screen-by-screen E2E

Playwright использует mock API/WebSocket, поэтому не вызывает реальные генерации, платежи и Telegram login.

- Guest Home: hero, CTA и login modal.
- Models: каталог и media filters.
- Gallery: feed cards и top-day switch.
- Guest Studio: явный auth gate, а не blank screen.
- Authenticated Studio: prompt → generation request.
- Account: hash routing billing → referrals.
- Admin navigation: видна только admin user.
- Mobile 390 px: нет горизонтального overflow.
- API failure: public shell остаётся доступным.
- На ключевых экранах сохраняются screenshots в Playwright report.

## 11. Автоматические проверки

Из `artflow/`:

```bash
python -m compileall api bot core db main.py
node --check landing/js/prototype-premium.js
pytest -q
```

Из `artflow/webapp/`:

```bash
npm ci
npm run build
```

Из `artflow/tests/e2e/`:

```bash
npm install
npx playwright install chromium
npm test
```

Инфраструктура:

```bash
nginx -t
docker compose config
```

## 12. Staging/manual smoke

Mock E2E не заменяет реальные интеграции. Перед production release проверить:

- `GET /api/web/health`;
- реальный Telegram Login;
- `/app` внутри Telegram WebView;
- Studio generation с тестовой моделью;
- WebSocket lifecycle через nginx;
- payment sandbox/webhook;
- `/static/upload/missing.jpg` fallback;
- большой video/audio result;
- viewport 390 px на реальном Android/iPhone WebView.
