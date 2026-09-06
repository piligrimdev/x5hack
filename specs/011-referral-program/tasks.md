# Tasks: Реферальная программа

**Input**: Design documents from `specs/011-referral-program/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api-contracts.md, quickstart.md

**Organization**: Задачи сгруппированы по пользовательским историям. Каждая история независимо реализуема и тестируема.

**Tests**: Unit-тесты слоя Service и route-тесты включены (конституция + plan.md). Это не TDD-контрактные тесты: пишутся вместе с реализацией истории.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Можно выполнять параллельно (разные файлы, нет незавершённых зависимостей)
- **[Story]**: К какой пользовательской истории относится задача

## Path Conventions

Бэкенд — пакет `web/src/webx5/`. Клиент — `x5mobile/src/`.

- Entities: `web/src/webx5/entities/`
- CRUD: `web/src/webx5/crud/`
- Services: `web/src/webx5/services/`
- Schemas: `web/src/webx5/schemas/`
- Routes: `web/src/webx5/routes/`
- Core wiring: `web/src/webx5/core/`
- Migrations: `web/alembic/versions/`
- Tests: `web/tests/webx5/`
- Mobile: `x5mobile/src/components/screens/`, `x5mobile/src/hooks/`, `x5mobile/src/app/index.tsx`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Сущности, схемы контракта и env до миграции и сервисов.

- [X] T001 Добавить в `.env.example` `REFERRAL_INVITEE_DISCOUNT_PERCENT=10`, `REFERRAL_INVITER_COUPONS=2`, `REFERRAL_INVITER_CASHBACK_RUB=50`
- [X] T002 Создать `ReferralCode` и `ReferralLink` в `web/src/webx5/entities/referral.py` по `specs/011-referral-program/data-model.md` (code VARCHAR(6) UNIQUE + CHECK `^[A-Za-z0-9]{6}$`; link UNIQUE `referral_code_id`; `reward_status` ∈ awaiting_purchase|rewarded; снимки percent/coupons/cashback; окна `discount_valid_to` / `purchase_window_until`)
- [X] T003 [P] Расширить `CouponTransaction` в `web/src/webx5/entities/coupon.py`: CHECK type += `'referral'`; колонка `related_referral_link_id` UUID NULL FK `referral_link.id` ON DELETE SET NULL; частичный UNIQUE `ux_coupon_tx_referral`
- [X] T004 [P] Добавить `related_referral_link_id` и частичный UNIQUE `ux_points_tx_earn_referral` в `web/src/webx5/entities/points.py` у `PointsTransaction`
- [X] T005 Зарегистрировать `ReferralCode`, `ReferralLink` в `web/src/webx5/entities/__init__.py`
- [X] T006 [P] Создать схемы `ReferralOut`, `ReferralListOut` в `web/src/webx5/schemas/referral.py` по `specs/011-referral-program/contracts/api-contracts.md` (`status`: issued|awaiting_purchase|rewarded|expired; без телефона/ФИО/UUID друга)

**Checkpoint**: Entity-классы видны Alembic; контрактные схемы импортируются; env задокументирован.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Схема БД, репозиторий, env-хелперы, каркас `/referrals` и поле `referral_code` в auth. Без этого нельзя выдать код и активировать связку.

**⚠️ CRITICAL**: Пользовательские истории не начинать, пока фаза не закрыта.

- [X] T007 Написать миграцию `web/alembic/versions/o3d4e5f6a7b8_referral_program.py` (`down_revision = n2c3d4e5f6a7`): `referral_code` → `referral_link` → `coupon_transaction` type/FK/unique → `points_transaction.related_referral_link_id` + unique earn; `INSERT discount_link_types ('all') ON CONFLICT DO NOTHING` (сид уже мог появиться в `d2e3f4a5b6c7`); downgrade — обратный порядок
- [ ] T008 Применить миграцию: `poetry -C web run alembic -c web/alembic.ini upgrade head`
- [X] T009 Создать `ReferralRepository` в `web/src/webx5/crud/referral.py`: `insert_code`, `get_by_code` + `lock_code_for_update` (`SELECT … FOR UPDATE`), `insert_link`, `get_link_by_code_id`, `list_codes_for_inviter`, `get_active_link_for_invitee(now)`, `has_recent_receipt(invitee_id, since)`
- [X] T010 [P] Создать `web/src/webx5/core/referral.py`: чтение трёх env (percent 0–100, coupons ≥ 0, cashback ≥ 0, иначе `RuntimeError`), константы `REFERRAL_TZ = Europe/Moscow`, `INACTIVE_DAYS = 180`, `WINDOW_DAYS = 7`; wiring `referral_repo` + `referral_service` без side effects на импорте crud
- [X] T011 Добавить в `UserRepository` в `web/src/webx5/crud/user.py` метод `add(session, phone) -> User` (flush, **без** `commit`); существующий `create` оставить или перевести на `add`+commit, чтобы `AuthService.register` мог атомарно активировать код
- [X] T012 [P] Добавить опциональное `referral_code: str | None = None` в `PhoneRequest` в `web/src/webx5/schemas/auth.py` с валидатором: если задан — ровно `[A-Za-z0-9]{6}`, иначе 422; регистр не менять
- [X] T013 Создать `ReferralService` в `web/src/webx5/services/referral.py` с DI на `ReferralRepository` (и позже discount/coupon/points): каркас методов `issue`, `activate`, `award_on_receipt`, `list_for_inviter` (пока могут бросать `NotImplementedError`, кроме того что понадобится сразу в US1)
- [X] T014 Добавить `referral_router` в `web/src/webx5/routes/referral.py` (`POST /referrals`, `GET /referrals`, `CurrentUserUUID` + `SessionDep`) и подключить в `web/src/webx5/core/server.py`; без токена — 401

**Checkpoint**: `alembic current` = HEAD. `POST /referrals` без JWT = 401. `PhoneRequest` принимает `referral_code`.

---

## Phase 3: User Story 1 — Сгенерировать и отправить уникальный код (Priority: P1) 🎯 MVP

**Goal**: Держатель карты за один тап с главной получает новый 6-символьный код `[A-Za-z0-9]`, копирует или шарит его. Каждый запрос — новый код; старые неиспользованные живы.

**Independent Test**: Два `POST /referrals` с JWT → два разных кода длины 6. `GET /referrals` содержит оба со `status=issued`. Без JWT — 401. На главной «Пригласить» открывает экран с кодом.

### Implementation for User Story 1

- [X] T015 [US1] Реализовать `ReferralService.issue(session, inviter_id)` в `web/src/webx5/services/referral.py`: `secrets.choice` из 62 символов × 6; до 8 повторов при UNIQUE; иначе ошибка для 503; не инвалидировать предыдущие коды
- [X] T016 [US1] Реализовать `POST /referrals` в `web/src/webx5/routes/referral.py`: 201 `ReferralOut` (`status=issued`, окна null); пустое тело/`{}`
- [X] T017 [P] [US1] Unit-тесты в `web/tests/webx5/services/test_referral_service.py`: два `issue` подряд — разные коды, оба `[A-Za-z0-9]{6}`; регистр сохраняется
- [X] T018 [US1] Route-тесты в `web/tests/webx5/routes/test_referral_routes.py`: 401 без JWT; 201 дважды — разные `code`
- [X] T019 [P] [US1] Добавить `apiIssueReferral` и `apiListReferrals` в `x5mobile/src/api/client.ts` (Bearer, пути `/referrals`)
- [X] T020 [P] [US1] Установить `expo-clipboard` в `x5mobile/` через `npx expo install expo-clipboard` (SDK 57)
- [X] T021 [US1] Хук `useReferrals` в `x5mobile/src/hooks/useReferrals.ts`: при монтировании `GET /referrals`, метод `issue()` → `POST /referrals` и обновить список; `{ items, latest, loading, error, issue, refetch }`
- [X] T022 [P] [US1] Экран `ReferralView` в `x5mobile/src/components/screens/referral-view.tsx`: пропсы `{ token, goBack }`; крупно показать `latest.code`; кнопки «Скопировать» (`expo-clipboard`) и «Отправить» (`Share.share` из `react-native`); `StyleSheet.create`; цвета как на Аппи (`#138F3E`, `#164E2B`, `#17211A`)
- [X] T023 [US1] Добавить `'referral'` в `Screen` в `x5mobile/src/app/index.tsx` и QuickAction «Пригласить» в `x5mobile/src/components/screens/home-view.tsx` (1 тап с главной → `navigate('referral')`)

**Checkpoint**: Quickstart сценарий 1 и сценарий 7 (шаги 1). Код можно скопировать и отправить.

---

## Phase 4: User Story 2 — Зарегистрироваться с реферальным кодом (Priority: P1)

**Goal**: Регистрация с валидным чужим кодом атомарно создаёт аккаунт, гасит код, пишет `referral_link` со снимками env и персональную скидку X% на 7 суток. Без кода — как 003. Плохой код — аккаунта нет.

**Independent Test**: Код A → register B с кодом → 200, у B есть скидка, код `awaiting_purchase`. Повтор кода — 409. Register с `"12"` — 422, повтор register без кода на тот же номер не даёт 409 «уже есть».

### Implementation for User Story 2

- [X] T024 [US2] Реализовать `ReferralService.activate(session, invitee_id, raw_code, *, is_new_user)` в `web/src/webx5/services/referral.py`: FOR UPDATE по коду; 409 если нет/уже есть link/свой код/есть активная связка invitee; снять снимки env на момент активации; вставить `referral_link` (`reward_status=awaiting_purchase`, окна `now+7d`); создать `Discount` (тип `персональная`, link_type `all`, `value_type=percent`, `loyalty_card_id=invitee`, `scope=all`, `valid_from/to`); для `is_new_user=True` проверку 180 дней не делать
- [X] T025 [US2] В `AuthService.register` в `web/src/webx5/services/auth.py`: если `referral_code` задан — `UserRepository.add` (без commit) + loyalty card + `activate(..., is_new_user=True)` + один `commit`; если кода нет — прежнее поведение; при ошибке активации rollback, user не остаётся
- [X] T026 [US2] Unit-тесты в `web/tests/webx5/services/test_referral_service.py`: успешная активация нового invitee; повтор того же кода — отказ; `AbC12x` ≠ `abc12x`; самоприглашение; невалидный код не зовёт insert_link
- [X] T027 [US2] Дописать `web/tests/webx5/routes/test_auth.py` (или новый `test_auth_referral.py`): register с валидным кодом → 200 и повтор кода 409; register с коротким кодом → 422 и телефон свободен; register без кода → 200 как раньше

**Checkpoint**: Quickstart сценарий 2. Регистрация без кода не сломана.

---

## Phase 5: User Story 3 — Реактивировать аккаунт или получить отказ (Priority: P1)

**Goal**: Логин с кодом проходит только если нет чеков за 180 дней (Europe/Moscow). Иначе 409, JWT нет, код не гасится. Логин без кода всегда как 003. 403 не использовать.

**Independent Test**: User с чеком вчера + валидный код → 409, вход без кода → 200. User без чеков 180 дней + код → 200, скидка стартует. Несуществующий номер + код → 404, код `issued`.

### Implementation for User Story 3

- [X] T028 [US3] В `ReferralService.activate` в `web/src/webx5/services/referral.py` для `is_new_user=False`: если `has_recent_receipt` за 180 дней — 409 «Реактивация недоступна: недавно были покупки. Войдите без кода»; иначе та же активация, что US2
- [X] T029 [US3] В `AuthService.login` в `web/src/webx5/services/auth.py`: без кода — как сейчас; с кодом — найти user (404 если нет) → `activate(..., is_new_user=False)` → JWT только после успеха; 409 не маскировать в 403
- [X] T030 [US3] Тесты в `web/tests/webx5/services/test_referral_service.py` и `web/tests/webx5/routes/test_auth.py`: чек внутри 180 дней → отказ, код жив; чек старше 180 дней → успех; 404 на неизвестный телефон не гасит код; активная незакрытая связка блокирует второй код
- [X] T031 [US3] В `x5mobile/src/components/screens/login-view.tsx` для 409/422 показывать `ApiError` detail (не «номер не зарегистрирован»); 404/403 оставить как сейчас

**Checkpoint**: Quickstart сценарий 3. Обычный логин без кода не меняется.

---

## Phase 6: User Story 4 — Награда приглашающему после покупки за неделю (Priority: P1)

**Goal**: Приглашающий ничего не получает на активации. Первый новый чек invitee внутри 7 суток атомарно даёт снимок купонов + кешбек. Повтор чека и второй чек — без второй пачки. После окна — 0 наград.

**Independent Test**: Активация → чек на 3-й день → у A +N купонов (`type=referral`) и earn баллов, `status=rewarded`. Второй чек — без прироста. Связка без чека 8 дней → `expired`, наград нет.

### Implementation for User Story 4

- [X] T032 [US4] Добавить `CouponService.award_for_referral(session, inviter_id, amount, referral_link_id)` в `web/src/webx5/services/coupon.py`: если amount=0 — no-op; иначе lock счёта, +amount, tx `type=referral`; при UNIQUE не делать `session.rollback()`
- [X] T033 [P] [US4] Добавить `PointsService.award_for_referral(session, inviter_id, amount_rub, referral_link_id)` в `web/src/webx5/services/points.py`: формула как `award_for_spin`; amount_rub=0 — no-op; без `rollback` на IntegrityError; прокинуть `related_referral_link_id` в crud
- [X] T034 [P] [US4] Добавить `type: "referral"` в схему купонов `web/src/webx5/schemas/coupon.py` и nullable `related_referral_link_id` в `web/src/webx5/schemas/points.py`
- [X] T035 [US4] Реализовать `ReferralService.award_on_receipt(session, invitee_id, receipt_id)` в `web/src/webx5/services/referral.py`: найти связку `awaiting_purchase` с `now <= purchase_window_until`; начислить купоны и кешбек по снимку; `reward_status=rewarded`, `qualifying_receipt_id`, `rewarded_at`; после окна — ничего не писать
- [X] T036 [US4] Вызвать `award_on_receipt` в `ReceiptService.create_receipt` в `web/src/webx5/services/receipt.py` до `session.commit()`, только если `is_new` и есть `loyalty_card_id`; не вызывать из Celery `process_receipt`
- [X] T037 [US4] Unit-тесты в `web/tests/webx5/services/test_referral_service.py`: награда один раз; второй чек 0; чек после окна 0; нулевые снимки не пишут леджер; идемпотентный replay чека не удваивает

**Checkpoint**: Quickstart сценарий 5. История купонов/баллов A показывает «за реферала».

---

## Phase 7: User Story 5 — Недельная скидка приглашённого (Priority: P2)

**Goal**: Пока `valid_to` не истек, калькулятор и чек применяют персональные X% (best-price-wins). После окна скидки нет. Экономия в `total_saved`.

**Independent Test**: Calculate корзины B внутри окна — есть percent-скидка (если не проиграла более выгодной). После `valid_to` та же корзина без неё.

### Implementation for User Story 5

- [X] T038 [US5] Проверить/дописать `DiscountRepository.find_applicable_for_cart` в `web/src/webx5/crud/discount.py`: скидка `link_type=all` + `loyalty_card_id=invitee` попадает в кандидаты и фильтр персональной карты; best-price-wins не менять
- [X] T039 [US5] Тесты в `web/tests/webx5/services/test_referral_service.py` или `web/tests/webx5/services/test_discount_calculator.py`: внутри окна percent X применяется; после `valid_to` — нет; более выгодная акция побеждает реферал на той же позиции
- [X] T040 [P] [US5] Route-тест `POST /receipts/calculate` в `web/tests/webx5/routes/test_receipts.py` (или рядом): карта invitee с живой реферальной скидкой → `total_saved` учитывает её

**Checkpoint**: Quickstart сценарий 4.

---

## Phase 8: User Story 6 — Статус своих приглашений (Priority: P2)

**Goal**: `GET /referrals` отдаёт все коды приглашающего с вычисляемым статусом. Экран показывает список. ПД друга нет.

**Independent Test**: Коды в состояниях issued / awaiting_purchase / rewarded / expired видны в JSON и на экране. Пустой список — `{items:[]}` и CTA «создать код».

### Implementation for User Story 6

- [X] T041 [US6] Реализовать `ReferralService.list_for_inviter` и `GET /referrals` в `web/src/webx5/services/referral.py` и `web/src/webx5/routes/referral.py`: JOIN код↔link; статус по правилам data-model; сортировка `created_at DESC`; в JSON нет invitee_id/телефона
- [X] T042 [US6] Тесты в `web/tests/webx5/routes/test_referral_routes.py`: четыре статуса; пустой список; 401; тело без идентификаторов друга
- [X] T043 [US6] Список статусов (человекочитаемые подписи) в `x5mobile/src/components/screens/referral-view.tsx` под текущим кодом; пустое состояние + кнопка «Создать код» зовёт `issue()`

**Checkpoint**: Quickstart сценарий 7 шаг 3. Экран не угадывает, сработал ли код.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Согласованность ошибок, история баллов, прогон quickstart.

- [X] T044 [P] Прокинуть `related_referral_link_id` в ответ `GET /points/transactions` (`web/src/webx5/schemas/points.py`, `web/src/webx5/routes/points.py`)
- [X] T045 [P] Сообщения 409/422 в `ReferralService` — русские тексты из `specs/011-referral-program/research.md` R5; самоприглашение — quickstart сценарий 6
- [X] T046 Прогнать сценарии 1–6 из `specs/011-referral-program/quickstart.md` (curl + pytest); ручной сценарий 7 на мобильном
- [X] T047 Убедиться, что register/login без `referral_code` и существующие тесты `web/tests/webx5/routes/test_auth.py` / чеков / колеса не сломаны

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: нет зависимостей
- **Foundational (Phase 2)**: после Setup — **блокирует все истории**
- **US1 (Phase 3)**: после Foundational — MVP
- **US2 (Phase 4)**: после US1 (`issue` нужен, чтобы было чем активировать; в тестах можно вставить код через репозиторий)
- **US3 (Phase 5)**: после US2 (`activate` общий)
- **US4 (Phase 6)** и **US5 (Phase 7)**: после US2 (нужна связка + скидка); можно параллелить между собой
- **US6 (Phase 8)**: после US1 (список issued); полные статусы — после US2–US4
- **Polish (Phase 9)**: после нужных историй

### User Story Dependencies

- **US1 (P1)**: только фундамент
- **US2 (P1)**: нужен `issue` / строка `referral_code`
- **US3 (P1)**: нужен `activate` из US2
- **US4 (P1)**: нужна связка `awaiting_purchase`
- **US5 (P2)**: нужна скидка, созданная в US2
- **US6 (P2)**: список кодов из US1; статусы reward/expired — после US4

### Within Each User Story

- Репозиторий/сервис до роута
- Роут до клиентского хука
- Хук до экрана
- Тесты сервиса вместе с реализацией истории

### Parallel Opportunities

- Phase 1: T003/T004/T006 параллельно с T002
- Phase 2: T010 и T012 параллельно с T009
- US1: T017 ∥ T019 ∥ T020; T022 после хука T021
- US4: T032 ∥ T033 ∥ T034
- US4 и US5 после US2 — разные файлы (receipt vs discount tests)
- US5 T040 ∥ T039

---

## Parallel Example: User Story 1

```bash
# После T015–T016:
Task: "Unit-тесты issue в web/tests/webx5/services/test_referral_service.py"
Task: "apiIssueReferral в x5mobile/src/api/client.ts"
Task: "npx expo install expo-clipboard в x5mobile/"

# После клиента и хука:
Task: "ReferralView в x5mobile/src/components/screens/referral-view.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 Setup
2. Phase 2 Foundational
3. Phase 3 US1 — выдача и шаринг кода
4. **STOP**: два разных кода + экран с главной
5. Дальше US2 — иначе код нельзя активировать на регистрации

### Incremental Delivery

1. Setup + Foundational
2. US1 → демо «пригласи друга» (код есть, активации ещё нет)
3. US2 → регистрация со скидкой
4. US3 → реактивация / отказ
5. US4 → экономика приглашающего
6. US5 → скидка на кассе (может частично закрыться уже в US2)
7. US6 → статусы на экране
8. Polish + quickstart

### Parallel Team Strategy

1. Вместе: Setup + Foundational
2. Dev A: US1 (API + мобильный экран)
3. Dev B: после `issue` — US2/US3 (auth)
4. Dev C: после связки — US4 (чек) и US5 (калькулятор)

---

## Notes

- Код: ровно 6 символов `[A-Za-z0-9]`, регистр значим
- На логине с кодом — **409, не 403**
- Награда приглашающему — в транзакции чека, не в Celery
- `[P]` = разные файлы, нет незакрытых зависимостей
- Коммитить по истории или логической группе, только если попросили
