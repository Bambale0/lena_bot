# APIX UX2: execution roadmap

Baseline: `d97184f4a9587a8237df6504de1fe58ff8142c22`. Source of current status: GitHub issues.

Program: https://github.com/Bambale0/lena_bot/issues/209

One active vertical slice. E01.1 / #220 was delivered in #221. Current slice: [E01.2 / #222](E01-2.md). GitHub issues hold the current verification/release status. Do not close the parent epic after one child is delivered.

| Epic | Issue | Scope |
| --- | --- | --- |
| E01 | #210 | [[UX2-E01] Материалы и черновики без потери данных](epics/E01.md) |
| E02 | #211 | [[UX2-E02] Единый редактор: понятные сценарии, основные и расширенные настройки](epics/E02.md) |
| E03 | #212 | [[UX2-E03] Тренды и повторы: единый понятный путь без раскрытия авторских данных](epics/E03.md) |
| E04 | #213 | [[UX2-E04] Запуск, ожидание, восстановление и доставка результата](epics/E04.md) |
| E05 | #214 | [[UX2-E05] Библиотека работ, просмотр, скачивание и безопасная публикация](epics/E05.md) |
| E06 | #215 | [[UX2-E06] Навигация, лента и поиск идей без тупиков и потери контекста](epics/E06.md) |
| E07 | #216 | [[UX2-E07] Баланс, оплата и профиль: понятная цена и безопасное возвращение](epics/E07.md) |
| E08 | #217 | [[UX2-E08] Дизайн-система, доступность и реальный Telegram WebView](epics/E08.md) |
| E09 | #218 | [[UX2-E09] Единый контракт возможностей, управляемая конфигурация и наблюдаемость](epics/E09.md) |
| E10 | #219 | [[UX2-E10] Пользовательская проверка, управляемый пилот и выпуск UX2](epics/E10.md) |

## E01 status at this revision (2026-10-10)

- Completed: E01.1 #220; E01.2 #222; E01.3 #225; E01.4.1 #229 (PR #231).
- Contract-only work: [E01.4.2 owner-bound media](E01-4-2.md), issue #232.
- Architectural decision: [ADR-UX2-001](../adr/ADR-UX2-001-owned-media.md).
- Execution plan: [owned media registry implementation](../superpowers/plans/2026-10-10-owned-media-registry.md).
- E01.4 #226 and E01 #210 remain open. GitHub issues remain authoritative for current state.
- This revision changes documentation only: no new ownership backend, migration or URL renewal is deployed.
