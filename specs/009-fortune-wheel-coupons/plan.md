# Implementation Plan: Колесо фортуны и купоны

**Branch**: `009-fortune-wheel-coupons` | **Date**: 2026-09-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/009-fortune-wheel-coupons/spec.md`

## Summary

Бэкенд API (`web/`): купоны как кошелёк по образцу баллов; ленивая еженедельная выдача N из `FORTUNE_WHEEL_WEEKLY_COUPONS`; +1 купон при закрытии задания; `GET /wheel` отдаёт сектора и баланс; `POST /wheel/spin` атомарно списывает 1 купон и выдаёт приз на сервере (кешбэк через `PointsService`, подарок через существующий `gift_reward`). Каталог секторов — `FixedPrizeCatalog`; слот под ИИ без смены контракта. Мобильная анимация вне скоупа.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: FastAPI (sync), SQLAlchemy (sync), Alembic, structlog, pytest

**Storage**: PostgreSQL (существующий инстанс, Alembic-миграции)

**Testing**: pytest, зеркалирование в `web/tests/webx5/`

**Target Platform**: Linux server (Docker); потребитель API — мобильный клиент (вне этой фичи)

**Project Type**: web-service (REST API)

**Performance Goals**: ответ спина < 3 с в 95% (SC-006); PoC-нагрузка

**Constraints**: обратимые миграции; не ломать баллы, подарки, задания; RNG только на сервере; N ≥ 0 из env

**Scale/Scope**: синтетические пользователи, фиксированный каталог из 4 секторов, демо хакатона

## Constitution Check

_GATE: до Phase 0 и повторно после Phase 1._

| Принцип                                 | Статус        | Обоснование                                                                                                                                                                                                   |
| --------------------------------------- | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| I — Экономия как метрика                | ✅            | Призы — кешбэк в рублях/баллах или бесплатный товар; экономия видна в корзине и на счёте баллов                                                                                                               |
| II — ≤2 действия / запрет новых механик | ⚠️ исключение | - Колесо — новая механика поверх аватара/челленджа/рейта. Запрошено командой в спеке. API: одно действие на просмотр, одно на спин. **Не позиционировать жюри как готовую к пилоту** без поправки конституции |
| III — ИИ-персонализация                 | ⚠️ отложено   | Челленджи не трогаем. Сектора колеса пока шаблонные (явно в спеке); контракт уже per-user для будущей LLM-замены                                                                                              |
| IV — Юнит-экономика                     | ⚠️ PoC        | Ожидание приза ≈ 39 ₽/спин (research R12). Для пилота нужен расчёт маржи; для демо достаточно прозрачных вероятностей                                                                                         |
| V — Privacy                             | ✅            | Нет новых ПД; ключ — `users.id`                                                                                                                                                                               |
| RSI                                     | ✅            | `crud/` + `services/` + `routes/`; роут только schema + session → service                                                                                                                                     |
| DI                                      | ✅            | Репозитории в конструктор сервиса / wiring в `core/`                                                                                                                                                          |
| Контролируемая инициализация            | ✅            | Без side effects на импорте crud/services/routes/entities                                                                                                                                                     |
| Тесты                                   | ✅            | Unit на Service: грант, спин, идемпотентность задания, отказ без купонов                                                                                                                                      |

Повтор после Phase 1: те же статусы. Дизайн не усугубляет II/III/IV: ИИ не притворяется готовым, экономика задокументирована, apply подарка переиспользуется.

## Project Structure

### Documentation (this feature)

```text
specs/009-fortune-wheel-coupons/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── api-contracts.md
└── tasks.md             # Phase 2: /speckit-tasks
```

### Source Code

```text
web/
├── alembic/versions/
│   └── <hash>_fortune_wheel_coupons.py    # coupon_account, wheel_spin,
│                                          # coupon_transaction, FK spin→gift/points
└── src/webx5/
    ├── entities/
    │   ├── coupon.py       # CouponAccount, CouponTransaction
    │   ├── wheel.py        # WheelSpin
    │   ├── reward.py       # + related_spin_id
    │   └── points.py       # + related_spin_id
    ├── crud/
    │   ├── coupon.py       # NEW: lock, grant, debit, list tx
    │   └── wheel.py        # NEW: insert spin, list spins
    ├── services/
    │   ├── coupon.py       # NEW: ensure_weekly_grant, award_for_task, debit
    │   ├── wheel.py        # NEW: get_state, spin (RNG + prize)
    │   ├── prize_catalog.py # NEW: PrizeCatalogProvider, FixedPrizeCatalog
    │   ├── points.py       # + award_for_spin (без session.rollback)
    │   └── task_completion.py # + CouponService.award_for_task
    ├── schemas/
    │   ├── wheel.py        # WheelStateOut, SectorOut, SpinOut, SpinPage
    │   └── coupon.py       # CouponTxOut, CouponTxPage
    ├── routes/
    │   ├── wheel.py        # GET /wheel, POST /spin, GET /spins
    │   └── coupons.py      # GET /coupons/transactions
    ├── core/
    │   ├── wheel.py        # wiring + FORTUNE_WHEEL_WEEKLY_COUPONS
    │   └── server.py       # include routers
    └── schemas/points.py   # + related_spin_id
.env.example                                # + FORTUNE_WHEEL_WEEKLY_COUPONS=3

web/tests/webx5/
    ├── services/
    │   ├── test_coupon_service.py
    │   ├── test_wheel_service.py
    │   ├── test_prize_catalog.py
    │   └── test_task_completion_coupon.py
    └── routes/
        └── test_wheel_routes.py            # 401, 409, сумма вероятностей
```

**Structure Decision**: только бэкенд-пакет `web/src/webx5` (как 007/008). `x5mobile/` не меняем: клиент рисует колесо по `GET /wheel` и крутит анимацию к `sector_code` из `POST /wheel/spin`.

## Complexity Tracking

| Violation                             | Why Needed                                                                                            | Simpler Alternative Rejected Because                                                                                                          |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Принцип II: новая механика «колесо»   | Явный запрос команды / спека 009; купоны замыкают контур челленджа, приз выражен в рублях (принцип I) | Не делать API — противоречит принятой спеке. Встроить спин в экран челленджа без отдельной сущности — всё равно новая игра и хуже тестируется |
| Принцип III: сектора пока не LLM      | Спека: «сейчас фиксированные, ИИ позже»; провайдер уже per-user                                       | Генерировать LLM сразу — вне скоупа и без hit-rate разметки                                                                                   |
| Принцип IV: нет полного расчёта маржи | PoC/демо; оценка ~39 ₽/спин в research                                                                | Блокировать план — команда сознательно берёт демо-скоуп; пилот жюри без расчёта по-прежнему запрещён                                          |

## Phase 0 / Phase 1 outputs

- [research.md](research.md) — R1–R13, без открытых NEEDS CLARIFICATION
- [data-model.md](data-model.md) — coupon\_\*, wheel_spin, расширения gift/points
- [contracts/api-contracts.md](contracts/api-contracts.md) — `/wheel`, `/wheel/spin`, `/wheel/spins`, `/coupons/transactions`
- [quickstart.md](quickstart.md) — curl-сценарии валидации
