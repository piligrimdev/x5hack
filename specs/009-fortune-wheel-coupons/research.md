# Research: Колесо фортуны и купоны

## R1 — Счёт купонов по образцу баллов

**Decision**: Отдельные таблицы `coupon_account` + `coupon_transaction` (зеркало `points_account` / `points_transaction`). Баланс денормализован на счёте, леджер иммутабелен.

**Rationale**: Уже обкатанный паттерн в `web/src/webx5/crud/points.py`: ленивое создание, `SELECT … FOR UPDATE`, `CHECK (balance >= 0)`. Купоны — тот же «кошелёк», только единица другая. Общая колонка на `users` смешает контуры и усложнит историю (FR-012).

**Alternatives considered**:
- Поле `users.coupon_balance` — нет аудита и идемпотентности недели/задания.
- Только леджер без баланса — каждый запрос считает `SUM`; для спина под локом приемлемо, но расходится со стилем баллов.

---

## R2 — Идемпотентность еженедельной выдачи

**Decision**: Ключ недели — дата понедельника (`week_start DATE`) в поясе `Europe/Moscow`. Частичный уникальный индекс на `coupon_transaction (coupon_account_id, week_start) WHERE type = 'weekly_grant'`. Отдельная таблица `weekly_coupon_grant` не нужна.

**Rationale**: FR-008/FR-009: один пакет на календарную неделю, без доначисления прошлых недель. Дата понедельника однозначно задаёт неделю и удобна в API/логах.

**Alternatives considered**:
- Таблица `weekly_coupon_grant` — лишний JOIN при том же инварианте.
- Пара `(iso_year, iso_week)` — два поля вместо одного, легче ошибиться на границе года.

---

## R3 — Ленивая выдача пакета, не Celery Beat

**Decision**: `CouponService.ensure_weekly_grant(session, user_id)` вызывается в начале `GET /wheel` и `POST /wheel/spin` под тем же `FOR UPDATE`, что и списание.

**Rationale**: FR-013 явно требует ленивую выдачу для демо. Спин в новую неделю не должен «не увидеть» только что положенные купоны (edge case спеки). Отдельный понедельник-джоб не обязателен.

**Alternatives considered**: Celery Beat в 00:00 пн — нужен воркер всегда включён; гонка «спин до джоба» всё равно требует ленивого догона.

---

## R4 — Каталог секторов: провайдер, сейчас фиксированный

**Decision**: Протокол `PrizeCatalogProvider.get_sectors(user_id) -> list[WheelSector]`. Реализация `FixedPrizeCatalog` возвращает один и тот же список из 4 секторов (спека, допущения). ИИ-провайдер — следующий этап, тот же метод.

Сектора имеют стабильный `code` (`small_cashback`, `medium_cashback`, `gift_chocolate`, `large_cashback`) для анимации клиента.

**Rationale**: FR-003 — контракт персональный, содержимое пока общее. Смена источника не меняет `GET /wheel` → `POST /wheel/spin`.

**Alternatives considered**:
- Таблица `wheel_sector` в БД — избыточна, пока каталог константа; ИИ всё равно сгенерирует список на лету.
- Генерация ИИ сразу — вне скоупа спеки.

**Подарочный сектор**: `criterion_type='category'`, сущность резолвится в рантайме по имени категории `кондитерка` (уже есть в сиде каталога и вайбе «Побаловать себя»). Если категории нет — спин откатывается целиком (атомарность FR-018).

---

## R5 — Случайный выбор только на сервере

**Decision**: `random.SystemRandom().choices(population, weights, k=1)`. Веса — целые проценты каталога (40/30/20/10). Тело `POST /wheel/spin` пустое: клиент не передаёт сектор. Лишние поля игнорируются (Pydantic extra ignore).

**Rationale**: FR-004. `SystemRandom` достаточен для PoC (не предсказуем из ответа предыдущего спина). Клиентский RNG отвергнут спекой.

**Alternatives considered**: `secrets.randbelow` + ручная рулетка — то же самое; таблица предгенерированных исходов — оверкилл.

---

## R6 — Кешбэк спина через существующие баллы

**Decision**: Расширить `points_transaction` колонкой `related_spin_id UUID NULL FK wheel_spin.id`. Добавить `PointsService.award_for_spin(...)`. Формула совпадает с текущим `award_for_task`: `points = int(round(amount_rub * rate / 10) * 10)` — чтобы 10 ₽ на колесе = 10 ₽ награды за задание в тратимых баллах.

Частичный уникальный индекс `ux_points_tx_earn_spin ON (related_spin_id) WHERE type = 'earn' AND related_spin_id IS NOT NULL`.

**Rationale**: FR-015. Спека 007 писала «as-is = int(reward_rub)», но живой код (`PointsService.award_for_task`) умножает на курс. Колесо следует **коду**, иначе одинаковая сумма в рублях даёт разный баланс.

**Ловушка**: `PointsRepository.insert_earn` при `IntegrityError` делает `session.rollback()` и снесёт всю транзакцию спина. Новый `insert_earn_for_spin` НЕ вызывает `rollback`; конфликт проверяется уникальным индексом + существование спина (один earn на спин по конструкции).

**Alternatives considered**: отдельный «кошелёк колеса» — дублирует баллы и ломает единую экономию (принцип I).

---

## R7 — Подарок спина = существующий `gift_reward`

**Decision**: Добавить `gift_reward.related_spin_id UUID NULL FK wheel_spin.id ON DELETE SET NULL`. `task_id` остаётся NULL. `valid_to = now() + 7 days`. Создание через `GiftRewardRepository.create` (уже принимает `task_id=None`). Применение в корзине/чеке не меняется (`DiscountCalculatorService.apply_gift_rewards`).

Порядок в одной транзакции: lock купонов → списать купон → вставить `wheel_spin` → создать gift или points earn → закоммитить.

**Rationale**: FR-016/FR-017. `task_id` уже nullable (спека 008). Отдельная таблица подарков колеса заставила бы дублировать apply-логику.

**Alternatives considered**: циклический FK `wheel_spin.gift_reward_id` ↔ `gift_reward.related_spin_id` — достаточно одной ссылки со стороны подарка; история спина денормализует тип/лейбл/сумму.

---

## R8 — Купон за выполненное задание

**Decision**: В конце `TaskCompletionService.apply_receipt`, после выдачи основной награды (gift или points), вызвать `CouponService.award_for_task(session, task)` (+1 купон). Идемпотентность: частичный UNIQUE `(related_task_id) WHERE type = 'task_complete'`. Истечение задания купон не даёт (хук только на ветке «выполнено»).

**Rationale**: FR-010/FR-011. Точка «задание закрыто» уже атомарна с наградой; купон — ещё одна запись в той же сессии.

**Alternatives considered**: купон как третий `reward_type` задания — ломает «сверх основной награды». Отдельная celery-задача — лишняя гонка.

---

## R9 — N из окружения

**Decision**: Переменная `FORTUNE_WHEEL_WEEKLY_COUPONS` (целое ≥ 0, дефолт `3`), читается в `web/src/webx5/core/wheel.py` так же, как `CHALLENGE_LLM_MODEL` / `TERMINAL_TOKEN`. Невалидное значение → ошибка конфигурации при чтении (сервис не раздаёт купоны с мусорным N). Пояс: константа `Europe/Moscow` (допущение спеки); отдельный env не требуется.

**Rationale**: Пользователь явно просил N в env. Стиль проекта — `os.environ.get`, не pydantic-Settings.

**Alternatives considered**: строка в `points_settings`-подобном singleton — можно менять без рестарта, но спека сказала env. Купоны за задание в env не выносим (фиксировано 1).

---

## R10 — Контракт API

**Decision**:
| Метод | Путь | Назначение |
|--------|------|------------|
| GET | `/wheel` | Сектора + баланс купонов + `can_spin` (ленивый weekly grant) |
| POST | `/wheel/spin` | Кручение; пустое тело; приз выбирает сервер |
| GET | `/wheel/spins` | История кручений, пагинация как у `/points/transactions` |
| GET | `/coupons/transactions` | Леджер купонов (FR-012) |

Один `GET /wheel` закрывает SC-007. Отдельный `GET /coupons/balance` не нужен.

**Auth**: `CurrentUserUUID` (`users.id` = `loyalty_card_id`, как баллы и награды). 401 без JWT. 409 `INSUFFICIENT_COUPONS` если баланс 0 после weekly grant.

**Alternatives considered**: `/fortune-wheel/*` — длиннее; RPC `POST /wheel` и на чтение, и на спин — хуже кэшируется клиентом.

---

## R11 — Параллельные спины

**Decision**: В `spin()`: `get_or_create` счёта → `SELECT coupon_account FOR UPDATE` → `ensure_weekly_grant` → проверка баланса → списание → приз. Второй параллельный запрос ждёт лок и видит уже уменьшенный баланс.

**Rationale**: FR-007/FR-019. Тот же приём, что `PointsRepository.lock_account_for_update`.

---

## R12 — Принцип II конституции (колесо как новая механика)

**Decision**: Фича реализуется как **демо-API хакатона**, не как «готово к пилоту». В Complexity Tracking плана — явное исключение. ИИ-каталог и расчёт юнит-экономики (принцип IV) — до показа жюри, не блокер Phase 1.

**Оценка стоимости спина** (для IV, не гейт):  
`0.4×10 + 0.3×30 + 0.2×~80 + 0.1×100 ≈ 39 ₽` ожидание приза. При N=3 ≈ 117 ₽/пользователь/неделя плюс 1 купон за задание. Пилоту нужен расчёт маржи; для PoC достаточно прозрачных вероятностей (SC-003).

**Alternatives considered**: отказаться от колеса из-за Принципа II — противоречит запросу команды и уже принятой спеке.

---

## R13 — Повтор спина при обрыве сети

**Decision**: Без `Idempotency-Key`. Повтор `POST /wheel/spin` = новый спин, если первый уже закоммичен. Клиент не ретраит кручение; при сомнении читает `GET /wheel` + `GET /wheel/spins`.

**Rationale**: Допущение спеки. Ключ идемпотентности — отдельная фича.

---

## Неразрешённых NEEDS CLARIFICATION нет

Все технические неизвестные закрыты решениями выше. Живой код (`award_for_task`, `gift_reward`, `CurrentUserUUID`) принят как источник истины для интеграций.
