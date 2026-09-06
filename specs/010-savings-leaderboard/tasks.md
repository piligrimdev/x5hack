# Tasks: Лидерборд экономии магазина

**Input**: Design documents from `specs/010-savings-leaderboard/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api-contracts.md, quickstart.md

**Organization**: Задачи сгруппированы по пользовательским историям. Каждая история независимо реализуема и тестируема.

**Tests**: Unit-тесты слоя Service и route-тесты 401/200 включены (конституция + plan.md). Это не TDD-контрактные тесты: пишутся вместе с реализацией истории.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Можно выполнять параллельно (разные файлы, нет незавершённых зависимостей)
- **[Story]**: К какой пользовательской истории относится задача

## Path Conventions

Бэкенд — пакет `web/src/webx5/`. Клиент — `x5mobile/src/`.

- CRUD: `web/src/webx5/crud/`
- Services: `web/src/webx5/services/`
- Schemas: `web/src/webx5/schemas/`
- Routes: `web/src/webx5/routes/`
- Core wiring: `web/src/webx5/core/`
- Tests: `web/tests/webx5/`
- Mobile screens: `x5mobile/src/components/screens/`
- Mobile hooks: `x5mobile/src/hooks/`
- Navigation: `x5mobile/src/app/index.tsx`

Новых таблиц и миграций нет.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Контрактные схемы и каркас слоёв RSI до запросов и экрана.

- [X] T001 Создать Pydantic-схемы `PeriodOut`, `LeaderboardStoreOut`, `LeaderboardMeOut`, `LeaderboardEntryOut`, `LeaderboardOut` в `web/src/webx5/schemas/leaderboard.py` по `specs/010-savings-leaderboard/contracts/api-contracts.md` (`status`: `no_home_store` \| `ready`; без `user_id` / адреса / ФИО)
- [X] T002 [P] Создать `LeaderboardRepository` в `web/src/webx5/crud/leaderboard.py` с пустыми методами `list_recent_store_votes(session, window)` и `list_monthly_savings(session, month_start, month_end)` (сигнатуры и docstring, без SQL)
- [X] T003 Создать `LeaderboardService` в `web/src/webx5/services/leaderboard.py` с DI на `LeaderboardRepository` (репозиторий только из конструктора) и методом-заглушкой `get_snapshot(session, user_id)`

**Checkpoint**: Схемы импортируются; сервис собирается без side effects на импорте crud.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Чтение чеков, пояс месяца, `GET /leaderboard` с 401 и статусом `no_home_store`. Без этого нельзя открыть рейтинг с Аппи.

**⚠️ CRITICAL**: Пользовательские истории не начинать, пока фаза не закрыта.

- [X] T004 Реализовать `list_recent_store_votes` в `web/src/webx5/crud/leaderboard.py`: чеки с `loyalty_card_id IS NOT NULL` и непустым `store_id`; `ROW_NUMBER() OVER (PARTITION BY loyalty_card_id ORDER BY purchase_date DESC, id DESC)`; окно `rn <= window`; вернуть по паре (user, store) `vote_count` и `last_purchase_at`
- [X] T005 Реализовать `list_monthly_savings` в `web/src/webx5/crud/leaderboard.py`: за `[month_start, month_end)` агрегировать на `loyalty_card_id` `total_saved = SUM(discounted_amount × qty) + SUM(cashback_applied_rub)` и `total_base = SUM(base_price_at_purchase × qty)`; строки с `total_base <= 0` не возвращать
- [X] T006 Создать `web/src/webx5/core/leaderboard.py`: `LEADERBOARD_TZ = ZoneInfo("Europe/Moscow")`, `HOME_STORE_WINDOW = 20`, `current_month_bounds(now=None) -> (start, end)`, wiring `leaderboard_repo` + `leaderboard_service` без импорт-side-effects crud
- [X] T007 Реализовать в `web/src/webx5/services/leaderboard.py` ветку `get_snapshot`: нет голосов у зрителя → `status="no_home_store"`, `store=null`, `me=null`, `entries=[]`, `participant_count=0`, `solo=false`, `period` из `current_month_bounds`
- [X] T008 Добавить `GET /leaderboard` в `web/src/webx5/routes/leaderboard.py` (`CurrentUserUUID` + `SessionDep` → `leaderboard_service.get_snapshot`) и подключить `leaderboard_router` в `web/src/webx5/core/server.py`
- [X] T009 [P] Тест маршрута в `web/tests/webx5/routes/test_leaderboard_routes.py`: без JWT → 401, тела рейтинга нет

**Checkpoint**: `curl /leaderboard` без токена = 401; с токеном пользователя без чеков = 200 `no_home_store`.

---

## Phase 3: User Story 1 — Открыть рейтинг с экрана Аппи (Priority: P1) 🎯 MVP

**Goal**: Тап по блоку статистики экономии на Аппи открывает экран. Данные приходят с `GET /leaderboard` (магазин, место, процент, список). Клиент не считает чужие места.

**Independent Test**: Пользователь с покупками и «своим» магазином. Нажать на «Экономия по месяцам» → экран рейтинга с магазином, местом и процентом из ответа сервера. Без JWT API даёт 401. Назад — снова Аппи.

### Implementation for User Story 1

- [X] T010 [US1] Дописать `LeaderboardService.get_snapshot` в `web/src/webx5/services/leaderboard.py`: home store зрителя (мода голосов), когорта с тем же store, процент `round(saved/base*100)` clamp 0…100, простой порядок по проценту DESC, заполнить `store` (`id`, `name` позже уточнит US3), `me`, `entries`; читать только через репозиторий
- [X] T011 [US1] Хук `useSavingsLeaderboard` в `x5mobile/src/hooks/useSavingsLeaderboard.ts`: `apiFetch<LeaderboardOut>('/leaderboard', token)` при монтировании; вернуть `{ data, loading, error, refetch }`; типы совпадают с контрактом
- [X] T012 [P] [US1] Экран `SavingsLeaderboardView` в `x5mobile/src/components/screens/savings-leaderboard-view.tsx`: пропсы `{ token, goBack }`; шапка «←» как в `fortune-wheel-view.tsx`; показать `store.name`, `me`, список `entries`; цвета Аппи (`#138F3E`, `#164E2B`, `#17211A`); `StyleSheet.create`
- [X] T013 [US1] Сделать блок `chartCard` нажимаемым в `x5mobile/src/components/screens/appi-view.tsx` (`Pressable` / `TouchableOpacity`) и добавить проп `onOpenLeaderboard`
- [X] T014 [US1] Добавить `'leaderboard'` в `Screen` в `x5mobile/src/app/index.tsx`: `onOpenLeaderboard` → `navigate('leaderboard')`; рендер `SavingsLeaderboardView`; Аппи **не размонтировать** при `screen === 'leaderboard'` (скрыть, не unmount); таб подсвечивать как `appi` (рядом с `wheel` / `challenges`)
- [X] T015 [US1] Дописать `web/tests/webx5/routes/test_leaderboard_routes.py`: авторизованный пользователь с чеками в одном магазине → 200, `status=ready`, есть `store`, `me.rank`, `me.savings_percent`, `entries`

**Checkpoint**: Quickstart сценарий 1 и сценарий 7 (шаги 1–4) проходят. Рейтинг открывается одним тапом.

---

## Phase 4: User Story 2 — Место по проценту экономии (Priority: P1)

**Goal**: Порядок только по проценту, не по рублям. Competition-места 1, 2, 2, 4. Шапка «N из M» и «опережаете X%». Топ-10; если зритель ниже — отдельная строка «Вы».

**Independent Test**: Два покупателя одного магазина: A 200 ₽ / 2 000 ₽ (10%), B 500 ₽ / 10 000 ₽ (5%). У A место выше. Одинаковый округлённый процент → одно место.

### Implementation for User Story 2

- [X] T016 [US2] В `web/src/webx5/services/leaderboard.py` считать competition rank (1, 2, 2, 4) только по `savings_percent`; рубли не тай-брейк; при равном проценте порядок строк стабильный по `loyalty_card_id`, место общее; `beats_percent = floor(count(percent < me) / M * 100)`; `entries` ≤ 10; `me.in_top`; если не в десятке — в `entries` нет `is_me`
- [X] T017 [US2] Анонимный `label` в `web/src/webx5/services/leaderboard.py`: `"Покупатель {100..999}"` из `sha256(loyalty_card_id)`; в ответ не класть UUID, телефон, адрес (research R8)
- [X] T018 [US2] В `x5mobile/src/components/screens/savings-leaderboard-view.tsx` показать «вы N из M», процент, формулировку «экономите большую долю, чем X%»; строка «Вы» из `me`, если `in_top === false`; в строках только место, подпись и %, без рублей как критерия
- [X] T019 [US2] Unit-тесты в `web/tests/webx5/services/test_leaderboard_service.py`: A(10%) выше B(5%) при меньших рублях; ничья процентов → одинаковый rank и схема 1,2,2,4; 11-й зритель → `len(entries)==10`, `me.in_top==false`, `me.rank==11`

**Checkpoint**: Quickstart сценарии 4–5. Абсолютные рубли не двигают место.

---

## Phase 5: User Story 3 — Рейтинг своего магазина (Priority: P1)

**Goal**: Home store = самый частый среди последних 20 чеков (или всех, если меньше). Ничья — более поздняя покупка, затем меньший `store_id`. В списке только те, чей home store совпал, не «хотя бы раз был в магазине».

**Independent Test**: 20 чеков (12 в А, 8 в Б) → `store.id` = А, повтор стабилен. Покупатель с home store Б в списке А отсутствует.

### Implementation for User Story 3

- [X] T020 [US3] Вынести `resolve_home_store(votes, window=HOME_STORE_WINDOW)` в `web/src/webx5/services/leaderboard.py`: окно 20; чеки без store не голосуют; ничья частоты → max `last_purchase_at`; ничья времени → min `store_id`; `store.name = "{format_name}, {geo_cluster}"` (подгрузить формат в crud или отдельным чтением `Store`, **без** `address`)
- [X] T021 [US3] Фильтровать участников в `web/src/webx5/services/leaderboard.py`: в рейтинг только пользователи с тем же resolved home store, что у зрителя (FR-008), не все, у кого есть чек в этом магазине за месяц
- [X] T022 [US3] Дописать `web/tests/webx5/services/test_leaderboard_service.py`: 12/8 → магазин А стабильно; 9 чеков / 5 в А → А; ничья 10/10 → магазин с более поздней покупкой; пользователь с другим home store не в `entries`

**Checkpoint**: Quickstart сценарий 3. Чужой магазин не попадает в список.

---

## Phase 6: User Story 4 — Пустые и одиночные состояния (Priority: P2)

**Goal**: Понятные состояния вместо пустого сбоя: нет покупок, нет места в этом месяце, один в магазине, ошибка сети с повтором. Аппи после закрытия ошибки не теряется.

**Independent Test**: Пользователь без чеков → приглашение купить, не список нулей. Чеки только в прошлом месяце → магазин виден, `me` нет, не «0%». Один в когорте → 1 из 1 и пояснение.

### Implementation for User Story 4

- [X] T023 [US4] Дописать ветки в `web/src/webx5/services/leaderboard.py`: `ready` + `me=null`, если home store есть, но зрителя нет в `list_monthly_savings`; `solo=true` при `participant_count==1` и зритель в таблице; `beats_percent=0` при M=1
- [X] T024 [US4] Состояния в `x5mobile/src/components/screens/savings-leaderboard-view.tsx`: `no_home_store` — «совершите покупку»; `ready` и `me==null` — магазин + список + «место после покупки в этом месяце» без нулей; `solo` — пояснение «пока нет других»; `error` — текст и кнопка `refetch`; `goBack` оставляет Аппи
- [X] T025 [US4] Тесты в `web/tests/webx5/services/test_leaderboard_service.py` и при необходимости `web/tests/webx5/routes/test_leaderboard_routes.py`: нет чеков → `no_home_store`; только прошлый месяц → `ready`, `me is null`; один участник → `solo`, rank 1 из 1

**Checkpoint**: Quickstart сценарии 2 и 6. Тап по статистике не выглядит как поломка.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Логи, проверка контракта и e2e.

- [X] T026 Добавить structlog-событие `leaderboard.snapshot` в `web/src/webx5/services/leaderboard.py` (status, store_id без ПД, participant_count; без `print`)
- [X] T027 [P] Сверить Scalar `GET /docs` с `specs/010-savings-leaderboard/contracts/api-contracts.md`: путь `/leaderboard`, 401, поля `status`/`me`/`entries`; в примере нет `user_id`
- [X] T028 Прогнать сценарии `specs/010-savings-leaderboard/quickstart.md` против живого API и тапа на Аппи (401, no_home_store, home store 12/8, процент vs рубли, анонимные label)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: сразу
- **Foundational (Phase 2)**: после Setup — **блокирует все истории**
- **US1 (Phase 3)**: после Phase 2 — MVP (тап + снимок)
- **US2 (Phase 4)**: после US1 (тот же `get_snapshot` и экран)
- **US3 (Phase 5)**: после US1 (уточняет home store / когорту); можно параллельно с US2, если не править одни и те же строки сервиса одновременно
- **US4 (Phase 6)**: после US1 (нужны `status` и экран); лучше после US2/US3
- **Polish (Phase 7)**: после выбранных историй

### User Story Dependencies

- **US1**: только фундамент — даёт рабочий вход и базовый снимок
- **US2**: патчит сервис и экран US1 — места и процент
- **US3**: патчит сервис US1 — магазин и состав
- **US4**: патчит сервис и экран — пустые состояния

```text
Phase 1 → Phase 2 → US1 ┬─ US2 ─┐
                         └─ US3 ─┴─ US4 → Polish
```

### Parallel Opportunities

- Phase 1: T001 ∥ T002, затем T003
- Phase 2: T009 ∥ (после T008)
- US1: T011 ∥ T012 после T010; затем T013 → T014
- US2 и US3: не править `web/src/webx5/services/leaderboard.py` одновременно
- Polish: T027 ∥ подготовка T028

---

## Parallel Example: User Story 1

```text
# После T010 (сервис отдаёт ready):
Task: "useSavingsLeaderboard in x5mobile/src/hooks/useSavingsLeaderboard.ts"
Task: "SavingsLeaderboardView in x5mobile/src/components/screens/savings-leaderboard-view.tsx"
# затем appi-view.tsx и index.tsx последовательно
```

## Parallel Example: After US1

```text
Dev A: Phase 4 US2 (ранг и % в сервисе + шапка экрана)
Dev B: не стартовать US3 в том же services/leaderboard.py, пока A не закроет T016–T017
# US3 стартует, когда методы rank и label стабильны
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 + Phase 2
2. Phase 3: US1
3. **STOP**: тап на Аппи открывает рейтинг, `GET /leaderboard` отвечает, 401 без токена

### Incremental Delivery

1. Setup + Foundational → 401 и `no_home_store`
2. US1 → демо входа (MVP)
3. US2 → честный процент
4. US3 → правильный магазин и когорта
5. US4 → пустые состояния
6. Polish → весь quickstart

### Suggested MVP scope

**US1**. Для показа жюри берите **US1 + US2 + US3** (все P1): иначе место может быть «нечестным» по рублям или в чужом магазине. US4 — второй инкремент, чтобы демо на свежих профилях не выглядело поломкой.

---

## Notes

- `[P]` только если разные файлы и нет дыр в зависимостях
- Клиент не агрегирует `/receipts` для рейтинга — только `GET /leaderboard`
- `address` магазина и UUID пользователей в JSON не отдавать
- Аппи не размонтировать на экране рейтинга (US1.4 / T014)
- Районный рейтинг из бэклога не реализовывать
- Не позиционировать как «пилот с призами за топ» — наград в скоупе нет
