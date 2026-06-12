# ArtFlow Audit Report

## Дата: 2026-05-11

## Результаты тестов
- **Всего тестов:** 188
- **Пройдено:** 188 ✅
- **Упавших:** 0

## Найденные и исправленные проблемы

### 1. VIDEO_CAPS — ключи словаря (Критично)
- **Проблема:** `VIDEO_CAPS` в `bot/keyboards/models.py` использовал `VideoModel` enum как ключи, но lookup выполнялся по строкам (`VIDEO_CAPS.get(model_key, {})`). Из-за разницы в хешировании StrEnum vs str, lookup возвращал пустой dict.
- **Последствия:** `_has_params()` всегда возвращал `False`, из-за чего видео-модели пропускали экран параметров и шли сразу к промпту.
- **Исправление:** Все ключи `VIDEO_CAPS` заменены на строковые значения.

### 2. Тесты FSM — устаревшие состояния
- **Проблема:** Тесты `tests/test_fsm.py` проверяли состояния (`settings`, `viewing_result` для ImageGenFSM; `generating` для MusicFSM; `params_select` для PromptUseFSM), которых больше нет в текущей реализации.
- **Исправление:** Тесты обновлены в соответствии с актуальными FSM.

### 3. Тест video_gen — перепутаны аргументы
- **Проблема:** В `test_cb_video_model_single_mode` аргументы `session` и `state` были перепутаны при вызове хендлера.
- **Исправление:** Порядок аргументов исправлен.

### 4. Legacy меню не соответствовало UI
- **Проблема:** `main_menu_kb()` содержал кнопки "Топ дня" и "Midjourney", которых нет в новом UI `render_main_menu()`.
- **Исправление:** Legacy меню синхронизировано с UI.

## Проверка моделей

### Видео-модели (БД)
- **Всего:** 27 моделей
- **Активных:** 25 (2 неактивных: kling-2.6 motion control 1080p/720p)
- **Соответствие API specs:** ✅ Все активные модели есть в `VIDEO_SPECS`

### Модели изображений (БД)
- **Всего:** 38 моделей
- **Активных:** 28
- **Соответствие API specs:** ✅ Все активные базовые модели есть в `IMAGE_SPECS`
- **Варианты качества/разрешения:** Создаются динамически через `pricing_variant_key()` — это ожидаемое поведение

### Midjourney модели
- Обрабатываются отдельным сервисом (`midjourney_service.py`), не через KIE API

### Специальные случаи
- Устаревшая внешняя модель удалена; runtime-провайдеры ограничены KIE.AI и CometAPI.

## Проверка API интеграции

### KIE Model Specs
- `build_kie_input()` корректно строит payload для всех типов моделей:
  - ✅ Seedream (aspect_ratio, quality)
  - ✅ Kling 3.0 (mode, sound, duration, aspect_ratio, multi_shots)
  - ✅ WAN (duration, resolution, prompt_extend, watermark)
  - ✅ Grok (mode, duration, resolution)
  - ✅ Veo3 (aspect_ratio, duration, enableTranslation, enableFallback)

### Webhook обработка
- `kie_webhook.py` корректно обрабатывает различные форматы ответов:
  - ✅ Извлечение task_id
  - ✅ Определение успеха/ошибки
  - ✅ Извлечение result_urls (поддержка разных ключей: result_urls, resultUrls, video_urls и т.д.)

## Документация API
- Основная документация: https://docs.kie.ai
- Актуальные модели подтверждены документацией:
  - ✅ Seedream 4.5
  - ✅ Kling 3.0
  - ✅ Veo 3
  - ✅ WAN 2.7
  - ✅ Grok Imagine

## Рекомендации
1. Не добавлять сторонние forced-route модели обратно; держать runtime-путь KIE.AI → CometAPI.
2. Рассмотреть добавление новых моделей из документации KIE (например, Seedream 5.0 Lite, Flux-2, Ideogram V3)
3. Мониторить вебхуки на предмет изменений формата ответов KIE API
