# Аудит bot-side ленты и инструкция интеграции

Документ описывает только ленту внутри Telegram-бота APIX. Mini app, `webapp/`, `api/web/*`, `api/miniapp_routes.py`, `landing/` и публичные web-экраны намеренно не входят в scope.

## 1. Короткий вывод

Лента в боте устроена не как простая галерея, а как социальный слой поверх завершённых image generations:

- показывает только публичные готовые изображения;
- даёт действия лайка, шаринга, навигации и повтора;
- хранит происхождение повторов через `source_feed_gen_id`;
- скрывает публикацию и копирование промпта у производных работ от чужой ленты;
- начисляет автору исходного поста 5% royalty в кредитах при успешном ремиксе/повторе от другого пользователя;
- интегрирована с image session UX: после повтора пользователь продолжает работу в серии.

Главная UX-идея: пользователь не видит промпт в карточке, но может повторить результат через контролируемый flow. Поэтому в другом проекте ленту лучше переносить как "витрину для вдохновения и remix/repeat", а не как открытый каталог промптов.

## 2. Scope и исключения

В scope:

- `bot/handlers/feed.py` - основной router ленты, карточки, callbacks.
- `bot/keyboards/feed.py` - клавиатуры карточек ленты и legacy-клавиатура результата.
- `db/models.py` - поля `generations`, нужные ленте.
- `db/repository.py` - выборки ленты, метрики, публикация, удаление, royalty.
- `bot/handlers/image_gen.py` - публикация результата, защита prompt actions, повтор/ремикс через image sessions.
- `bot/handlers/marketplace.py` - переиспользование PromptUseFSM для `feed:use`.
- `bot/handlers/start.py` и `bot/utils/deep_links.py` - deep links на посты.
- `main.py` - регистрация router и отправка post-generation кнопок из webhook.
- bot UI render helpers: `bot/ui/main_menu.py`, `bot/ui/router.py`, `bot/ui/image_menu.py`.
- тесты `tests/test_feed.py`, `tests/test_repository_feed.py`, часть `tests/test_keyboards_and_ui.py`, `tests/test_kie_webhook.py`, `tests/test_image_gen_references.py`.

Вне scope:

- mini app/API routes, даже если используют те же поля БД;
- web feed endpoint;
- landing;
- frontend assets.

## 3. Пользовательская архитектура

### Входы в ленту

1. Главное меню:
   - кнопка `🔥 Лента` с callback `menu:feed`;
   - расположена в content-блоке рядом с `📚 Библиотека` (`bot/ui/main_menu.py:121`).

2. Команда:
   - `/feed`, обработчик `open_feed` (`bot/handlers/feed.py:330`).

3. Deep link:
   - ссылка вида `https://t.me/<bot>?start=ref_<code>__feed_<generation_id>`;
   - парсится в `parse_start_payload` (`bot/utils/deep_links.py:17`);
   - `/start` открывает конкретный feed card через `show_feed_card_by_id` (`bot/handlers/start.py:133`).

4. После генерации:
   - текущий активный путь использует `image_session_kb` / `after_generation_kb` с callback `gen:share:<id>` и `gen:library:<id>`;
   - KIE webhook отправляет эти кнопки после завершения генерации (`main.py:923`);
   - direct/sync image result делает то же в `_launch_session_generation` (`bot/handlers/image_gen.py:794`).

5. Legacy-контур:
   - `get_generation_result_keyboard` создаёт `feed:remix`, `feed:publish`, `feed:again`, но в текущем bot-side коде функция практически не подключена, кроме импорта в `main.py`;
   - handlers под эти callbacks существуют для совместимости со старыми сообщениями (`bot/handlers/feed.py:441`, `532`, `591`).

### Что видит пользователь в карточке

Карточка ленты отправляется как фото, подпись и inline-клавиатура:

- автор: username, full name или `anon`;
- модель;
- формат кадра, если есть `ImageSession.aspect_ratio`;
- количество лайков и шарингов;
- без промпта.

Кнопки карточки (`bot/keyboards/feed.py:7`):

- `❤️` - лайк;
- `📤` - получить share/deep link;
- `➡️` - следующий пост;
- `🔁 Повторить` - открыть flow выбора модели;
- `🗑 Удалить из ленты` - только для автора;
- `📚 Библиотека промптов`;
- `🏠 Главная`.

Пустая лента показывает empty state с CTA:

- `🎨 Создать изображение`;
- `📚 Библиотека промптов`;
- `🏠 Главная`.

### Активные пользовательские сценарии

**Открыть ленту**

`/feed` или `menu:feed`:

1. очищает FSM state;
2. загружает до 30 карточек через `repo.get_feed_generations`;
3. показывает карточку по индексу `0`;
4. если карточек нет, показывает empty state.

**Перейти к следующей работе**

`feed:next:<source>:<index>`:

1. заново получает список карточек;
2. вычисляет `index % len(cards)`;
3. если текущее сообщение уже фото, пытается `edit_media`;
4. если текущее сообщение текстовое или Telegram не может открыть URL, отправляет новое фото/фолбэк.

**Лайк**

`feed:like:<gen_id>:<source>:<index>`:

1. `repo.like_feed_generation` увеличивает `likes_count`;
2. update защищён фильтрами `is_public_feed`, `done`, `result_url is not null`;
3. карточка перерисовывается.

Лайк не уникален по пользователю. Это счётчик кликов, а не social-like с toggle.

**Поделиться**

`feed:share:<gen_id>`:

1. `repo.increment_feed_share` увеличивает `shares_count`;
2. бот формирует deep link с ref code и target `feed_<id>`;
3. пользователю отправляется ссылка на пост и отдельная партнёрская ссылка.

Шаринг считается в момент генерации ссылки, не в момент фактического внешнего перехода.

**Повторить публичную работу**

`feed:use:<gen_id>`:

1. получает generation и её prompt;
2. переводит пользователя в `PromptUseFSM.model_select`;
3. кладёт в state:
   - `feed_use_gen_id`;
   - `feed_use_prompt`;
   - `feed_use_model`;
4. показывает выбор image-модели через `prompt_use_model_kb`;
5. затем marketplace flow обрабатывает выбор модели и опциональный референс;
6. новая генерация запускается через `_launch_session_generation` с `source_feed_gen_id = feed_use_gen_id`.

Важно: карточка не показывает промпт, но backend использует prompt как скрытый seed для повтора.

**Ремикс по картинке**

Legacy callback `feed:remix:<gen_id>`:

1. проверяет наличие `result_url`;
2. проверяет, поддерживает ли модель img2img;
3. архивирует активные image sessions пользователя;
4. создаёт новую `ImageSession` в режиме `image`;
5. сохраняет `reference_url = gen.result_url`;
6. ставит `source_feed_gen_id = gen.id`;
7. показывает пользователю "Ремикс готов, напиши что изменить";
8. публикация производного результата запрещена (`allow_publish=False`).

Текущий UX чаще идёт через active image session callbacks `img_session:remix`, где source attribution вычисляется аккуратнее через parent/state.

**Публикация своего результата**

Текущий путь:

1. после генерации пользователь видит `📤 В ленту`;
2. callback `gen:share:<id>` проверяет `_generation_prompt_actions_allowed`;
3. `repo.share_to_feed` публикует только done-result, принадлежащий пользователю, с `result_url`;
4. если результат является производным от чужой ленты, публикация блокируется;
5. пользователь получает deep link на пост.

Отдельно `gen:library:<id>` сохраняет промпт в библиотеку с той же защитой.

Legacy путь `feed:publish:<id>` одновременно выставляет `is_public_feed=True` и `is_prompt_library=True`. Он проверяет владельца и отсутствие `source_feed_gen_id`, но не использует repo helper и слабее валидирует статус/result_url.

**Удаление из ленты**

Кнопка удаления видна только автору карточки:

1. первый callback показывает подтверждение;
2. confirm вызывает `repo.remove_from_feed`;
3. `is_public_feed` сбрасывается в `False`;
4. пользователь возвращается в текущий источник ленты.

Удаление из ленты не удаляет generation и не снимает `is_prompt_library`.

## 4. Data model

Лента живёт в таблице `generations`, отдельной таблицы feed posts нет.

Ключевые поля (`db/models.py:112`):

- `gen_type` - для ленты выбираются только `GenerationType.image`;
- `status` - только `done`;
- `result_url` / `result_urls` - публичная карточка требует основной `result_url`;
- `is_public_feed` - флаг присутствия в ленте;
- `is_prompt_library` - отдельный флаг библиотеки промптов;
- `source_feed_gen_id` - self-FK на исходный публичный пост, если работа создана из чужой ленты;
- `parent_generation_id` - parent для repeat/remix внутри серии;
- `action_type` - `initial`, `remix`, `repeat`, etc.;
- `likes_count`, `shares_count` - агрегированные счётчики;
- `credits_spent` - база для royalty.

DTO карточки `FeedGenerationCard` (`db/repository.py:62`) дополняет generation данными пользователя и image session:

- `username`;
- `full_name`;
- `author_photo_url`;
- `aspect_ratio`;
- `quality`;
- `count`;
- `reference_url`;
- `remix_count`;
- `score`.

## 5. Repository layer

### Выборка и сортировка

`get_feed_generations(limit=30/100)`:

- фильтры: image, done, result_url, public;
- берёт newest `limit * 3`;
- затем `_feed_cards_from_stmt` добавляет author/session/remix_count;
- сортирует в Python по score и created_at;
- возвращает первые `limit`.

`get_top_day_generations(limit=10)`:

- те же фильтры;
- плюс `created_at` за текущую UTC-date;
- берёт newest `limit * 5`;
- сортирует по score.

Score (`db/repository.py:900`):

```text
likes_count * 1
+ remix_count * 3
+ shares_count * 5
+ (1 + remix_count) * 4
```

Если пост младше 2 часов, score умножается на `1.5`.

Практический эффект: лента ранжируется как "новое + вовлечённость", но старые хиты могут исчезать, потому что SQL сначала ограничивает выборку newest-окном.

### Публикация и права

`share_to_feed` публикует generation, если:

- generation принадлежит user_id;
- status done;
- есть result_url;
- `source_feed_gen_id is null` или исходный source принадлежит этому же user_id.

Последний пункт важен: свой remix от своей же работы можно публиковать, чужой source нельзя.

`share_to_library` использует ту же ownership/source защиту.

`like_feed_generation` и `increment_feed_share` обновляют только публичные done-result записи.

`get_feed_generation_card` и `get_public_feed_generation` возвращают только публичные done-result записи.

### Royalty

При `finish_generation`:

1. generation переводится в done;
2. если `source_feed_gen_id` пустой, ничего не начисляется;
3. если source не найден, начисление пропускается;
4. если source принадлежит тому же пользователю, начисление пропускается;
5. если `credits_spent <= 0`, начисление пропускается;
6. иначе автору source начисляется 5% от `credits_spent` через `add_credits(..., entry_type="feed_remix_royalty")`.

Это делает `source_feed_gen_id` не просто метаданным, а финансово значимым полем.

## 6. State machine и source attribution

Главный invariant: если пользователь сделал работу на основе чужого feed post, новая generation должна получить `source_feed_gen_id` исходного поста. Тогда:

- пользователь не сможет выдать производный prompt как свой;
- кнопки публикации и копирования prompt будут скрыты;
- автор source получит royalty после successful finish.

За это отвечают:

- `_external_source_feed_id` - обнуляет source, если source принадлежит текущему пользователю;
- `_source_feed_id_from_parent` - переносит source от parent generation;
- `_source_feed_id_for_generation_or_state` - выбирает source из parent/state;
- `_generation_prompt_actions_allowed` - разрешает publish/copy только владельцу и только если source пустой или source свой.

`_launch_session_generation` нормализует source, создаёт generation с `source_feed_gen_id`, а затем вычисляет:

- `publish_actions_allowed = not bool(source_feed_gen_id)`;
- `prompt_actions_allowed = publish_actions_allowed and action_type != repeat`.

То есть чужой source скрывает publish/copy, а repeat дополнительно скрывает copy prompt.

## 7. UI/UX контракт в боте

### Основные UX-принципы

1. Лента не раскрывает prompt публично.
2. Основной CTA карточки - `Повторить`.
3. Social actions компактные: heart, share, next.
4. Удаление показывается только владельцу.
5. После повтора пользователь попадает в привычный image generation flow, а не в отдельный "feed generator".
6. Производные от чужой ленты не получают кнопки `В ленту`, `В библиотеку`, `Скопировать промпт`.
7. Share link совмещает referral и deep link на пост.

### Текущие тексты

Карточка:

```text
👤 <author>
🎨 <model>
📐 <ratio>

❤️ <likes>
📤 <shares>
────────────
```

Empty state:

```text
🔥 <b>Лента</b>

Пока нет готовых публичных изображений. Самое время создать первый пост.
```

Repeat flow:

```text
🎨 <b>Повторить генерацию</b>

<i>Выбери модель:</i>
```

Remix ready:

```text
✨ <b>Ремикс готов</b>

Референс из выбранной генерации сохранён.
Теперь напиши, что изменить.
```

Publish success:

```text
📤 <b>Фото добавлено в ленту</b>

🔗 Ссылка на пост для повтора:
<link>
```

## 8. Audit findings and risks

### Сильные стороны

- Feed logic reuse минимальный: лента поверх `generations`, без отдельной сущности.
- Хороший privacy default: prompt не показывается в карточке.
- Source attribution проведён через generation lifecycle, а не только через UI.
- Публикация и сохранение в библиотеку защищены на repo уровне.
- Fallback отправки фото учитывает Telegram limits: скачивание, сжатие JPEG, текстовый fallback.
- Deep link строится одним helper и поддерживает referral.
- Есть тесты на основные handlers, keyboard visibility, repo filters, prompt hiding.

### Риски

1. `feed:use` читает generation через `get_generation_by_id`, а не через `get_public_feed_generation` или `get_feed_generation_card`.
   - Нормальный пользователь получает эту кнопку только с публичной карточки.
   - Но старые inline-кнопки после удаления поста могут продолжать запускать повтор.
   - Для новой интеграции лучше валидировать public/done/result_url прямо в handler.

2. `feed:remix` также читает raw generation по id.
   - Если callback остался в старом сообщении, hidden/removed post может использоваться как reference.
   - Для переноса лучше использовать `get_public_feed_generation`.

3. Legacy `feed:publish` не использует `repo.share_to_feed` / `repo.share_to_library`.
   - Проверяет owner/source, но не проверяет `status=done` и `result_url`.
   - В новом UX лучше не использовать `feed:publish`, а оставить только `gen:share` и `gen:library`.

4. `remove_from_feed` возвращает generation после update без проверки, была ли строка реально обновлена.
   - UI-кнопка показывается только владельцу, поэтому штатно не ломает сценарий.
   - Для жёсткого contract лучше возвращать `None`, если `UPDATE` не затронул строку.

5. Лайки не уникальны.
   - Это допустимо как "реакции/клики", но не как честный user-like.
   - Если в другом проекте нужен social graph, добавлять таблицу likes с unique `(user_id, generation_id)`.

6. Share count считает генерацию ссылки.
   - Это не фактические переходы и не реальные shares.
   - Для аналитики нужен отдельный open/click tracking.

7. Feed ranking ограничивает кандидатов newest-window.
   - Старые сильные посты могут не попасть в выборку.
   - Для полноценного discovery лучше хранить/обновлять score или выбирать шире.

8. Top day handler есть, но entrypoint из main menu специально не показан.
   - `menu:top_day` и `feed:top` существуют, но обычный пользователь не видит кнопку.
   - В новой интеграции либо убрать hidden route, либо явно вернуть вкладку "Топ дня".

9. При открытии ленты из текстового меню бот отправляет новое photo message, а не всегда редактирует старое.
   - Это нормальная Telegram-реальность: `edit_media` доступен только когда текущее сообщение уже media.
   - В новом UX это нужно принять как паттерн: старт может создать новую карточку, дальше navigation редактирует media.

10. `get_generation_result_keyboard` выглядит неактуальным для текущего result UX.
    - Его callbacks всё ещё поддерживаются.
    - В переносе лучше не копировать эту клавиатуру как primary.

## 9. Инструкция интеграции в UX/UI другого проекта

### 9.1. Ментальная модель

Интегрируй ленту как "социальное вдохновение с безопасным повтором", а не как "бесплатный список промптов".

Правильная иерархия:

1. Сначала пользователь смотрит результат.
2. Потом выбирает действие:
   - повторить;
   - поделиться;
   - лайкнуть;
   - перейти дальше.
3. Prompt остаётся скрытым, пока пользователь не владелец и пока результат не разрешён для copy.

### 9.2. Навигация

Размести вход в ленту в content/discovery блоке рядом с библиотекой:

```text
🔥 Лента     📚 Библиотека
📋 История
```

Не ставь ленту выше основного создания, если проект primarily generation-first. Лента должна усиливать создание, а не заменять его.

Если добавляешь вкладки:

- `Лента` - общий discovery;
- `Топ дня` - только если ranking действительно стабилен;
- `Мои посты` - полезно, если есть управление публикациями;
- `Библиотека` - отдельный prompt catalog, не смешивать с feed card.

### 9.3. Карточка

Минимальный набор данных на карточке:

- изображение;
- автор;
- модель;
- формат кадра;
- лайки;
- shares;
- primary CTA `Повторить`.

Не показывать prompt в публичной карточке. Если в другом проекте нужно preview prompt, показывать только безопасный "style summary", сгенерированный отдельно и не являющийся исходным prompt.

Рекомендуемая раскладка кнопок для Telegram:

```text
❤️    📤    ➡️
🔁 Повторить
📚 Библиотека     🏠 Главная
```

Для владельца:

```text
🗑 Удалить из ленты
```

Для web/native UI:

- изображение как главный объект;
- actions под изображением;
- `Repeat` как primary/filled button;
- like/share/next как icon buttons;
- delete в overflow menu или destructive secondary action;
- не перегружать карточку настройками генерации.

### 9.4. Повтор и ремикс

Repeat flow:

1. пользователь нажимает `Повторить`;
2. выбирает модель;
3. опционально добавляет референс;
4. генерация создаётся с `source_feed_gen_id`;
5. после результата показывается обычный image session toolbar;
6. publish/copy скрыты, если source чужой.

Remix flow:

1. проверяй, что модель поддерживает img2img;
2. используй `result_url` исходной карточки как reference;
3. создавай image session в mode `image`;
4. сохраняй `source_feed_gen_id`;
5. явно говори пользователю: "Референс сохранён, напиши что изменить";
6. не показывай `В ленту` для производной работы от чужого source.

### 9.5. Публикация результата

После генерации показывай:

- `📤 В ленту`;
- `📚 В библиотеку`;
- `📋 Скопировать промпт` или `📋 Показать промпт`, только если разрешено;
- `✨ Ремикс`;
- `🔁 Ещё вариант`;
- `⚙️ Настройки`;
- `🆕 Новая серия`;
- `🏠 Главное меню`.

Правила видимости:

```text
if generation.source_feed_gen_id is null:
    allow_publish = true
else if source.user_id == current_user.id:
    allow_publish = true
else:
    allow_publish = false

allow_copy_prompt = allow_publish and action_type != "repeat"
```

Для нового проекта лучше держать эту логику на backend/API уровне и только дублировать в UI для чистоты интерфейса.

### 9.6. Deep links

Сохрани формат с двумя независимыми частями:

```text
ref_<referral_code>__feed_<generation_id>
```

Плюсы:

- один link одновременно открывает пост и привязывает referral;
- парсер может игнорировать неизвестные части;
- можно добавлять `prompt_<id>` без ломки.

При открытии deep link всегда проверяй:

- post существует;
- `is_public_feed=True`;
- `status=done`;
- `result_url` есть.

### 9.7. Финансовая логика

Если в другом проекте есть credits/revenue sharing, переноси royalty вместе с `source_feed_gen_id`.

Минимальная формула APIX:

```text
royalty = credits_spent * 0.05
```

Начислять только когда:

- generation успешно завершилась;
- source exists;
- source owner отличается от remixer;
- credits_spent > 0.

Не начислять в момент нажатия repeat/remix, только после `done`.

### 9.8. Анти-паттерны

Не делай так:

- не показывай исходный prompt всем в ленте;
- не разрешай публиковать derivative от чужой карточки как новый независимый пост;
- не доверяй только видимости кнопок в UI;
- не считай share count настоящими переходами;
- не смешивай prompt library и visual feed в одну сущность;
- не запускай generation из feed без `source_feed_gen_id`;
- не удаляй source attribution при repeat/remix внутри серии.

## 10. Минимальный backend contract для переноса

Таблица/модель generation должна иметь:

```text
id
user_id
model
gen_type
prompt
result_url
result_urls
status
created_at
finished_at
credits_spent
is_public_feed
is_prompt_library
source_feed_gen_id
parent_generation_id
action_type
likes_count
shares_count
```

Методы:

```text
get_feed_generations(limit)
get_top_day_generations(limit)
get_feed_generation_card(gen_id)
get_public_feed_generation(gen_id)
share_to_feed(gen_id, user_id)
remove_from_feed(gen_id, user_id)
share_to_library(gen_id, user_id)
like_feed_generation(gen_id)
increment_feed_share(gen_id)
create_generation(..., parent_generation_id, action_type, source_feed_gen_id)
finish_generation(...)
```

State для repeat/remix:

```text
feed_use_gen_id
feed_use_prompt
feed_use_model
source_feed_gen_id
remix_mode
remix_parent_generation_id
remix_reference_url
image_session_id
model_key
mode / image_mode
aspect_ratio
quality
count
```

## 11. Тестовый чеклист для интеграции

Обязательные bot-side тесты:

- `/feed` открывает ленту и очищает state;
- `menu:feed` открывает ленту и очищает state;
- empty state показывается без карточек;
- карточка не показывает prompt;
- next циклично обходит список;
- like увеличивает только публичный done-result;
- share увеличивает только публичный done-result и строит deep link;
- deep link `/start ...__feed_<id>` открывает только публичный post;
- repeat кладёт source id в state;
- repeat запускает generation с `source_feed_gen_id`;
- remix требует img2img support;
- remix создаёт image session с `reference_url`;
- publish блокирует чужой source derivative;
- library save блокирует чужой source derivative;
- own-source derivative можно публиковать;
- webhook result скрывает publish/copy для чужого source;
- royalty начисляется только после successful finish;
- remove доступен только владельцу;
- removed post не открывается по deep link.

Желательные тесты:

- old inline buttons после удаления не дают использовать hidden post;
- duplicate likes либо разрешены явно, либо блокируются unique constraint;
- большие изображения сжимаются ниже Telegram лимита;
- прямой URL fallback работает, если upload не прошёл;
- top day использует UTC/current project timezone осознанно.

## 12. Практический план переноса

1. Сначала перенести data contract: поля generation, source attribution, feed flags, metrics.
2. Затем перенести repository filters: public/done/result_url везде, где пост открывается извне.
3. Подключить publish из результата через `gen:share`-аналог, а не через legacy `feed:publish`.
4. Подключить feed card UX: image + компактная подпись + actions.
5. Подключить repeat через существующий generation flow, не создавать отдельный generator.
6. Встроить source attribution в create/finish generation.
7. Скрыть copy/publish для производных работ от чужого source.
8. Подключить deep links с referral и target.
9. Добавить tests на public gating, source gating и royalty.
10. Только после этого добавлять ranking/top/day/analytics.

