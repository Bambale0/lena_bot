# APIX — Экраны и состояния для v0

Бот: Telegram, aiogram 3, FSM-навигация через callback_data.
Дизайн: тёмный, AI/creative стиль. Компактный мобильный UI.

---

## 1. Главное меню

**Триггер:** `/start`, `menu:main`

**Текст:**
> 👋 Добро пожаловать в **APIX**!
> Твой арсенал AI-генерации:
> 🎨 Изображения — Gemini, WAN, GPT Image, Seedream
> 🎬 Видео — Kling, Veo, Grok, Seedance и другие
> 🖌️ Midjourney — Imagine, Blend, Describe, Video
> 🎁 На твой счёт зачислено **{N} стартовых кредитов**!

**Кнопки (2 колонки):**
| Кнопка | callback_data |
|---|---|
| 🎨 Изображение | `menu:image` |
| 🎬 Видео | `menu:video` |
| 🖌️ Midjourney | `menu:mj` |
| 💎 Баланс | `menu:balance` |
| 💳 Пополнить | `menu:topup` |
| 🗂 Промпты | `menu:prompts` |
| 📋 История | `menu:history` |
| 👥 Рефералы | `menu:referral` |
| ❓ Помощь | `menu:help` |

---

## 2. Генерация изображений

### 2.1 Выбор модели
**Триггер:** `menu:image`
**State:** `ImageGenFSM.model_select`

**Текст:** объяснение каждой модели + список сильных сторон

**Кнопки (1 в ряд):**
| Кнопка | callback_data |
|---|---|
| 🌸 Seedream 4.5 · 2 кр | `img_model:seedream-4.5` |
| 🍌 Nano Banano Pro · 4 кр | `img_model:nano-banano-pro` |
| 🍌 Nano Banano 2 · 2 кр | `img_model:nano-banano-2` |
| 🌊 WAN 2.7 · 3 кр | `img_model:wan-2.7` |
| 🌊 WAN 2.7 Image Pro · 5 кр | `img_model:wan-2.7-pro` |
| 🤖 GPT Imagine 2 · 4 кр | `img_model:gpt-image-1` |
| ← Назад | `menu:main` |

**Описания моделей (под кнопками или тултип):**
- `seedream-4.5` → Топ качество · реализм · детали · медленнее
- `nano-banano-pro` → Gemini Pro · точное следование промпту · img2img
- `nano-banano-2` → Gemini Flash · быстро · стиль · иллюстрации
- `wan-2.7` → WAN · кино-стиль · персонажи · фэнтези
- `wan-2.7-pro` → WAN Pro · kie.ai · высокое разрешение · async
- `gpt-image-1` → GPT Image · понимает сложные описания · творчество

### 2.2 Загрузка референса
**State:** `ImageGenFSM.reference_upload`

**Текст:** объяснение референса, что это такое и зачем

**Кнопки:**
| Кнопка | callback_data |
|---|---|
| ⏭ Пропустить (без референса) | `ref:skip` |
| ← Назад | `menu:image` |

**Также:** принимает фото → переходит к промпту

### 2.3 Ввод промпта
**State:** `ImageGenFSM.prompt_input`

**Текст:** советы по написанию промпта, примеры, параметры

**Кнопки:**
| Кнопка | callback_data |
|---|---|
| 🏠 Главное меню | `menu:main` |

**Также:** принимает текст → запускает генерацию

### 2.4 Генерация (ожидание)
**State:** `ImageGenFSM.generating`

Статусное сообщение:
> ⏳ **Генерирую...** · `{model_key}` · это займёт от 10 сек до пары минут

### 2.5 Результат
**Контент:** фото с подписью

**Подпись:** ✅ Готово! + промпт + подсказка

**Кнопки:**
| Кнопка | callback_data |
|---|---|
| 🔄 Ещё вариант | `regen:image:{gen_id}` |
| ✏️ Новый промпт | `reprompt:image:{gen_id}` |
| 🏠 Главное меню | `menu:main` |

---

## 3. Генерация видео

### 3.1 Выбор модели
**Триггер:** `menu:video`
**State:** `VideoGenFSM.model_select`

**Текст:** описание видео-моделей и возможностей

**Кнопки (1 в ряд):**
| Кнопка | callback_data |
|---|---|
| ⚡ Kling 3.0 · 30 кр | `vid_model:kling-3.0` |
| 🎭 Kling 2.6 Motion · 35 кр | `vid_model:kling-2.6-motion` |
| 🐦 Grok Video · 40 кр | `vid_model:grok-video` |
| 🐦 Grok Imagine Video · 45 кр | `vid_model:grok-imagine-video` |
| 🌱 Seedance 2.0 · 30 кр | `vid_model:doubao-seedance-2-0` |
| 🎬 Veo 3.1 Pro · 50 кр | `vid_model:veo3.1-pro` |
| 🐎 HappyHorse T2V · 25 кр | `vid_model:happyhorse-1.0-text-to-video` |
| 🐎 HappyHorse I2V · 30 кр | `vid_model:happyhorse-1.0-image-to-video` |
| ← Назад | `menu:main` |

**Описания:**
- `kling-3.0` → Плавное движение · text & img2video
- `kling-2.6-motion` → Управление камерой (pan/zoom/tilt)
- `grok-video` → Быстрая генерация · реализм
- `grok-imagine-video` → Творческие сцены
- `doubao-seedance-2-0` → Плавная анимация · текст→видео
- `veo3.1-pro` → Google · высшее качество · img2video
- `happyhorse-1.0-text-to-video` → text2video · быстро
- `happyhorse-1.0-image-to-video` → Анимация фото

### 3.2 Выбор режима
**State:** `VideoGenFSM.mode_select`

**Текст:** описание выбранной модели + объяснение режимов

**Кнопки (зависят от модели):**
| Кнопка | callback_data |
|---|---|
| ✍️ Текст | `vid_mode:text:{model_key}` |
| 🖼️ С референсом | `vid_mode:image:{model_key}` |
| ← Назад | `menu:video` |

> Кнопка «С референсом» показывается только для моделей, поддерживающих img2video:
> `kling-3.0`, `kling-2.6-motion`, `grok-video`, `happyhorse-1.0-image-to-video`, `doubao-seedance-2-0`, `veo3.1-pro`

### 3.3a Motion Control (только Kling 2.6 Motion, режим text)
**State:** `VideoGenFSM.motion_select`

**Кнопки (2 колонки):**
| Кнопка | callback_data |
|---|---|
| ◄ Pan Left | `motion:pan_left` |
| ► Pan Right | `motion:pan_right` |
| ▲ Tilt Up | `motion:tilt_up` |
| ▼ Tilt Down | `motion:tilt_down` |
| 🔍 Zoom In | `motion:zoom_in` |
| 🔎 Zoom Out | `motion:zoom_out` |
| ↺ Orbit | `motion:orbit_left` |
| ↻ Roll | `motion:roll_clockwise` |
| ← Назад | `menu:video` |

### 3.3b Загрузка изображения (режим image)
**State:** `VideoGenFSM.image_upload`

**Текст:** советы по выбору изображения

**Кнопки:**
| Кнопка | callback_data |
|---|---|
| 🏠 Главное меню | `menu:main` |

**Также:** принимает фото → переходит к промпту

### 3.4 Ввод промпта
**State:** `VideoGenFSM.prompt_input`

**Текст:** советы по промпту для видео, примеры

**Кнопки:**
| Кнопка | callback_data |
|---|---|
| 🏠 Главное меню | `menu:main` |

### 3.5 Генерация (ожидание)
Статус:
> ⏳ **Генерирую видео...** · это займёт 1–5 минут

### 3.6 Результат
**Контент:** видео с подписью

**Кнопки:**
| Кнопка | callback_data |
|---|---|
| 🔄 Ещё вариант | `regen:video:{gen_id}` |
| ✏️ Новый промпт | `reprompt:video:{gen_id}` |
| 🏠 Главное меню | `menu:main` |

---

## 4. Midjourney

### 4.1 Главное меню MJ
**Триггер:** `menu:mj`

**Текст:** описание всех 4 возможностей MJ

**Кнопки (2 колонки):**
| Кнопка | callback_data |
|---|---|
| 🎨 Imagine | `mj:imagine` |
| 🖼️ Blend | `mj:blend` |
| 🔍 Describe | `mj:describe` |
| 🎞️ Video | `mj:video` |
| ← Назад | `menu:main` |

### 4.2 Imagine — выбор бота
**Триггер:** `mj:imagine`
**State:** `MidjourneyFSM.bot_type_select`

**Кнопки:**
| Кнопка | callback_data |
|---|---|
| 🎨 Midjourney | `mj_bt:MID_JOURNEY` |
| 🌸 Niji Journey | `mj_bt:NIJI_JOURNEY` |
| ← Назад | `menu:mj` |

### 4.3 Imagine — выбор скорости
**State:** `MidjourneyFSM.speed_select`

**Кнопки (3 колонки):**
| Кнопка | callback_data |
|---|---|
| ⚡ Fast | `mj_sp:FAST` |
| 😌 Relax | `mj_sp:RELAX` |
| 🚀 Turbo | `mj_sp:TURBO` |
| ← Назад | `menu:mj` |

### 4.4 Imagine — загрузка референса
**State:** `MidjourneyFSM.reference_upload`

**Кнопки:**
| Кнопка | callback_data |
|---|---|
| ⏭ Без референса | `mj_ref:skip` |
| ← Назад | `menu:mj` |

**Также:** принимает фото → переходит к промпту

### 4.5 Imagine — ввод промпта
**State:** `MidjourneyFSM.prompt_input`

**Текст:** параметры MJ (`--ar`, `--v`, `--style raw`, `--q`), примеры

**Кнопки:**
| Кнопка | callback_data |
|---|---|
| 🏠 Главное меню | `menu:main` |

### 4.6 Imagine — результат (4 варианта)
**State:** `MidjourneyFSM.viewing_result`

**Контент:** изображение с 4 вариантами (grid)

**Кнопки:** динамические из API (U1–U4, V1–V4, 🔄 и другие)
```
callback_data = mj_btn:{index}  (index = 0..N)
```
| Кнопка | callback_data |
|---|---|
| U1 / U2 / U3 / U4 | `mj_btn:0..3` |
| V1 / V2 / V3 / V4 | `mj_btn:4..7` |
| 🔄 | `mj_btn:8` |
| Zoom Out / Pan / Vary... | `mj_btn:{N}` |
| 🏠 Главное меню | `menu:main` |

### 4.7 Imagine — ожидание Action
**State:** `MidjourneyFSM.action_polling`

> ⏳ Обрабатываю **{label}**...

### 4.8 Modal input (Vary Region / Custom Zoom)
**State:** `MidjourneyFSM.waiting_modal_input`

**Кнопки:**
| Кнопка | callback_data |
|---|---|
| ⏭ Без промпта | `mj_skip_prompt` |
| ✖️ Отмена | `menu:mj` |

---

### 4.9 Blend
**Триггер:** `mj:blend`
**State:** `MidjourneyFSM.blend_collecting`

**Текст:** инструкция, советы

**Кнопки (появляются по мере добавления фото):**
| Состояние | Кнопки |
|---|---|
| 0–1 фото | ✖️ Отмена |
| 2 фото | ✅ Блендить (2 фото) · ➕ Добавить ещё · ✖️ Отмена |
| 3 фото | ✅ Блендить (3 фото) · ➕ Добавить ещё · ✖️ Отмена |
| 4 фото | ✅ Блендить (4 фото) · ➕ Добавить ещё · ✖️ Отмена |
| 5 фото | ✅ Блендить (5 фото) · ✖️ Отмена |

callback_data кнопок: `mj_blend:submit`, `mj_blend:add`, `menu:mj`

### 4.10 Blend — выбор ориентации
**State:** (после submit, до запуска)

**Кнопки (3 колонки):**
| Кнопка | callback_data |
|---|---|
| 🖼 Портрет | `mj_dim:PORTRAIT` |
| ⬛ Квадрат | `mj_dim:SQUARE` |
| 🏞 Пейзаж | `mj_dim:LANDSCAPE` |

### 4.11 Blend — результат
Аналогично Imagine (grid + action buttons)

---

### 4.12 Describe
**Триггер:** `mj:describe`
**State:** `MidjourneyFSM.describe_upload`

**Текст:** зачем нужно + инструкция

**Кнопки:**
| Кнопка | callback_data |
|---|---|
| 🏠 Главное меню | `menu:main` |

### 4.13 Describe — результат
**Контент:** текстовое сообщение с 4 промптами от MJ

**Кнопки:**
| Кнопка | callback_data |
|---|---|
| 🏠 Главное меню | `menu:main` |

---

### 4.14 Video
**Триггер:** `mj:video`
**State:** `MidjourneyFSM.video_upload`

**Текст:** инструкция, советы по изображению

**Кнопки:**
| Кнопка | callback_data |
|---|---|
| 🏠 Главное меню | `menu:main` |

### 4.15 Video — интенсивность движения
**State:** `MidjourneyFSM.video_speed_select`

**Кнопки:**
| Кнопка | callback_data |
|---|---|
| 🐢 Low | `mj_vmot:low` |
| 🏎 High | `mj_vmot:high` |
| ← Назад | `menu:mj` |

### 4.16 Video — промпт (опционально)
**State:** `MidjourneyFSM.video_prompt`

**Кнопки:**
| Кнопка | callback_data |
|---|---|
| ⏭ Без промпта | `mj_skip_prompt` |
| ✖️ Отмена | `menu:mj` |

### 4.17 Video — результат
**Контент:** видео

**Кнопки:**
| Кнопка | callback_data |
|---|---|
| 🏠 Главное меню | `menu:main` |

---

## 5. Баланс

**Триггер:** `menu:balance`

**Текст:** кредиты, статус подписки, стоимость операций

**Кнопки:**
| Кнопка | callback_data |
|---|---|
| 🏠 Главное меню | `menu:main` |

---

## 6. Пополнение баланса

### 6.1 Выбор способа
**Триггер:** `menu:topup`

**Кнопки (тарифы + способы оплаты):**
| Кнопка | callback_data |
|---|---|
| 100 кр — 199 ₽ | `topup:rub:credits_100` |
| 300 кр — 499 ₽ | `topup:rub:credits_300` |
| 1000 кр — 1490 ₽ | `topup:rub:credits_1000` |
| 🪙 Оплатить криптой | `topup:crypto` |
| 🏠 Главное меню | `menu:main` |

### 6.2 Выбор тарифа для крипты
**Триггер:** `topup:crypto`

**Кнопки:**
| Кнопка | callback_data |
|---|---|
| 100 кр — ~2.21 USDT | `topup:crypto_plan:credits_100` |
| 300 кр — ~5.54 USDT | `topup:crypto_plan:credits_300` |
| 1000 кр — ~16.56 USDT | `topup:crypto_plan:credits_1000` |
| ← Назад | `menu:topup` |

### 6.3 Инвойс крипты
Ссылка на оплату через CryptoBot + кнопка «Оплатить»

### 6.4 Успешная оплата
> ✅ Оплата прошла! Зачислено **+{N} кредитов**. Баланс: **{total}**

---

## 7. История генераций

**Триггер:** `menu:history`

**Список** последних 10 генераций:
```
1. 🎨 ✅ seedream-4.5
   futuristic city at sunset...
   -2 кр
```

Статусы: ✅ done · ⏳ pending · 🔄 processing · ❌ failed

**Кнопки:**
| Кнопка | callback_data |
|---|---|
| 🏠 Главное меню | `menu:main` |

---

## 8. Рефералы

**Триггер:** `menu:referral`

**Текст:** реф-ссылка `https://t.me/{bot}?start={code}` + уровни бонусов

**Кнопки:**
| Кнопка | callback_data |
|---|---|
| 🏠 Главное меню | `menu:main` |

---

## 9. Маркетплейс промптов

### 9.1 Каталог
**Триггер:** `menu:prompts`, `/prompts`

**Кнопки категорий:**
| Кнопка | callback_data |
|---|---|
| Все | `prompts:cat:all` |
| 🎨 Изображения | `prompts:cat:image` |
| 🎬 Видео | `prompts:cat:video` |
| 🖌️ Midjourney | `prompts:cat:midjourney` |
| + Добавить промпт | `prompts:add` |
| Мои промпты | `prompts:my` |
| 🏠 Главное меню | `menu:main` |

### 9.2 Список промптов
Карточки промптов с навигацией по страницам

**Кнопки:**
| Кнопка | callback_data |
|---|---|
| {название промпта} | `prompt_detail:{id}` |
| ← Пред | `prompts:page:{page-1}:{cat}` |
| → След | `prompts:page:{page+1}:{cat}` |

### 9.3 Детали промпта
**Текст:** название, описание, категория, автор, цена (кредиты), кол-во использований

**Кнопки:**
| Кнопка | callback_data |
|---|---|
| ✅ Использовать · {N} кр | `prompt_use:{id}` |
| ← Назад | `prompts:cat:all` |

### 9.4 Добавление промпта (FSM)
**State flow:** `PromptUploadFSM` → title → description → category → prompt_text → confirm

**Шаги:**
1. Название
2. Описание
3. Выбор категории (кнопки: image / video / midjourney / other)
4. Текст промпта
5. Подтверждение → отправляется на модерацию

### 9.5 Мои промпты
**Список** своих промптов со статусами (approved / pending / rejected)

---

## 10. Помощь

**Триггер:** `menu:help`

**Текст:** полное руководство — как пользоваться, советы по промптам, стоимость, реф-программа

**Кнопки:**
| Кнопка | callback_data |
|---|---|
| 🏠 Главное меню | `menu:main` |

---

## Общие компоненты

### Уведомления об ошибке
> ❌ Ошибка генерации. Кредиты возвращены.
> Попробуй ещё раз или выбери другую модель.

**Кнопки:** `menu:main`

### Недостаточно кредитов
> ❌ Недостаточно кредитов! Нужно {N}, у тебя {M}.

`show_alert=True` (всплывающее окно Telegram)

### Кнопка «← Назад»
Везде, где есть вложенность — возврат на предыдущий экран.

---

## Цветовая палитра / стиль для v0

- **Фон:** `#0d0d0d` или `#111827`
- **Акцент:** `#6366f1` (indigo) или `#8b5cf6` (violet)
- **Успех:** `#10b981`
- **Ошибка:** `#ef4444`
- **Текст:** `#f9fafb`
- **Второстепенный текст:** `#9ca3af`
- **Карточки:** `#1f2937` с border `#374151`
- **Кнопки основные:** gradient indigo→violet
- **Кнопки навигации:** ghost / outline

**Типографика:** Inter или Geist, sans-serif

**Стиль:** glassmorphism-карточки, subtle glow на AI-элементах, иконки из Lucide или Heroicons.
