# Artflow Admin Cabinet Plan

## Goal
Сделать полноценный owner/admin кабинет для `artflow` как единый пункт управления ботом, сайтом и mini app.

## Product position
Это не просто набор админ-кнопок, а отдельный защищённый web-контур для владельца/операторов.

## Access model
- Доступ только для `ADMIN_IDS`
- Web auth через существующий Telegram/web auth слой
- Backend guard: `is_admin == true`
- Все чувствительные действия логируются

## Phase 1 — Core cockpit
### Dashboard
- DAU / WAU / MAU
- новые пользователи
- регистрации по дням
- оплаты: count / revenue / ARPPU
- генерации: image / video / music
- success rate / failed rate
- топ моделей по использованию
- spent credits / purchased credits
- pending withdrawals
- prompts pending moderation

### Charts
- registrations by day
- revenue by day
- generations by day
- conversions: signup -> first generation -> payment
- provider/model usage share

### Users
- поиск по tg_id / username / name
- карточка пользователя
- баланс / транзакции / генерации / рефералы
- ban / unban
- add credits / deduct credits
- история действий администратора

### Payments
- список транзакций
- фильтры: provider / status / date
- revenue summary
- failed/pending payments
- ручная сверка спорных транзакций

### Withdrawals
- очередь заявок
- approve / reject
- комментарий админа
- user timeline

### Prompt moderation
- pending / approved / rejected
- preview / approve / reject / deactivate

## Phase 2 — Operations
- управление ценами
- управление доступностью моделей
- feature flags
- промокоды
- ручные алерты/баннеры на сайт
- контент/лента moderation
- webhook/provider monitor

## Phase 3 — Deep analytics
- cohort analysis
- retention
- LTV by source/provider
- referral funnel
- generation profitability by model
- anomaly alerts

## Technical architecture
### Backend
New web admin router group:
- `/api/web/admin/overview`
- `/api/web/admin/charts`
- `/api/web/admin/users`
- `/api/web/admin/users/{id}`
- `/api/web/admin/users/{id}/credits`
- `/api/web/admin/users/{id}/ban`
- `/api/web/admin/transactions`
- `/api/web/admin/withdrawals`
- `/api/web/admin/prompts`
- `/api/web/admin/models/usage`
- `/api/web/admin/audit-log`

### Frontend
New web screens:
- `admin_dashboard`
- `admin_users`
- `admin_user_detail`
- `admin_payments`
- `admin_withdrawals`
- `admin_prompts`
- `admin_ops`

### Data sources
Use existing tables first:
- `users`
- `generations`
- `transactions`
- `promo_codes`
- `promo_redemptions`
- `referral_withdrawal_requests`
- `credit_ledger`

### New tables
- `admin_audit_log`
- optional later: daily aggregated metrics table for faster charts

## Delivery order
1. admin overview + charts
2. users list + user detail + credit/ban actions
3. payments + withdrawals
4. prompt moderation in unified UI
5. ops section (prices/models/flags)

## Important rule
Сначала делаем рабочий owner cockpit для реального управления, потом уже "красивую BI-систему".

## Recommended immediate implementation slice
Start with:
- admin guard
- overview API
- charts API
- users list/detail
- withdrawals queue
- admin menu entry in web app
