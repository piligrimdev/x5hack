# Implementation Plan: Реферальная программа

**Branch**: `011-referral-program` | **Date**: 2026-09-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/011-referral-program/spec.md`

Уточнение к плану: код — ровно 6 символов из цифр и латинских букв разного регистра (`[A-Za-z0-9]`), регистр значим.

## Summary

Бэкенд (`web/`): одноразовые коды `referral_code` + связка `referral_link` с зафиксированными настройками. `POST /register` и `POST /login` принимают опциональный `referral_code` (мобильный клиент уже шлёт поле). Активация атомарна с регистрацией; реактивация на входе — только если нет покупок 180 дней. Скидка приглашённого — существующая персональная `Discount` (`percent`, `link_type=all`, 7 суток). Награда приглашающему — в той же транзакции, что квалифицирующий чек: купоны (`type=referral`) + кешбек через `PointsService`. Настройки из env. Мобильный: экран приглашения с копированием/share за 1 тап с главной; экран входа уже умеет 6-символьный код.

## Technical Context

**Language/Version**: Python 3.11+ (бэкенд); TypeScript strict (Expo SDK 57 / React Native)

**Primary Dependencies**: FastAPI (sync), SQLAlchemy (sync), Alembic, Pydantic 2, structlog, pytest; мобильный — `apiFetch`, state-навигация в `index.tsx`, `expo-clipboard`, RN `Share`

**Storage**: PostgreSQL; новые таблицы `referral_code`, `referral_link`; расширения `coupon_transaction` / `points_transaction`; сид `discount_link_types.name = 'all'`

**Testing**: pytest, зеркало `web/tests/webx5/`; unit на `ReferralService` (генерация, активация, 180 дней, окно 7 суток, идемпотентность награды); route-тесты auth + referrals

**Target Platform**: Linux server (Docker) + iOS/Android через Expo; Web — вспомогательно

**Project Type**: mobile + API

**Performance Goals**: выдача кода и вход/регистрация с кодом < 2 с (SC-001 / auth SC); начисление награды внутри той же операции, что фиксация чека

**Constraints**: обратимые миграции; не ломать auth без кода, скидки, баллы, купоны; код case-sensitive; RSI + DI; без side effects на импорте; Expo managed (не eject)

**Scale/Scope**: синтетические пользователи хакатона; настройки по умолчанию 10% / 2 купона / 50 ₽

## Constitution Check

_GATE: до Phase 0 и повторно после Phase 1._

| Принцип                                 | Статус        | Обоснование                                                                                                                                                                                                 |
| --------------------------------------- | ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| I — Экономия как метрика                | ✅            | Скидка приглашённого в рублях на чеке; кешбек приглашающего на счёте баллов; купоны конвертируются в рублёвую экономию на колесе                                                                            |
| II — ≤2 действия / запрет новых механик | ⚠️ исключение | Реферал в конституции и CONTEXT_PACK — концептуальный экран демо, не четвёртая игра. Вход: 1 тап с главной. **Не позиционировать жюри как готовую к пилоту** без юнит-экономики                             |
| III — ИИ-персонализация                 | ✅ н/п        | Челленджи и LLM не трогаем                                                                                                                                                                                  |
| IV — Юнит-экономика                     | ⚠️ PoC        | Стоимость связки ≈ скидка 10% чека недели + 2×ожидание приза колеса + 50 ₽. Для пилота нужен расчёт маржи; для демо достаточно прозрачных настроек                                                          |
| V — Privacy                             | ✅            | Список приглашений — код и статус, без ФИО/телефона друга                                                                                                                                                   |
| RSI                                     | ✅            | `crud/` + `services/` + `routes/`; роут только schema + session → service                                                                                                                                   |
| DI                                      | ✅            | Репозитории в конструктор; wiring в `core/referral.py`                                                                                                                                                      |
| Контролируемая инициализация            | ✅            | Без side effects на импорте crud/services/routes/entities                                                                                                                                                   |
| Тесты                                   | ✅            | Unit на Service: формат кода, самоприглашение, 180 дней, окно покупки, разовая награда                                                                                                                      |
| Mobile Technical Standards              | ✅            | Функциональный экран + хук; `StyleSheet`; state-router `index.tsx`; `npx expo install expo-clipboard`; RN `Share` без prebuild                                                                              |

Повтор после Phase 1: те же статусы. Дизайн не добавляет ПД друга, не вводит отдельную валюту и не выносит награду приглашающего в отложенный Celery (атомарность с чеком).

## Project Structure

### Documentation (this feature)

```text
specs/011-referral-program/
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
│   └── <hash>_referral_program.py   # referral_code, referral_link,
│                                    # coupon/points related_referral_link_id,
│                                    # type='referral', seed discount_link_types 'all'
└── src/webx5/
    ├── entities/
    │   ├── referral.py              # NEW: ReferralCode, ReferralLink
    │   ├── coupon.py                # + type referral, related_referral_link_id
    │   └── points.py                # + related_referral_link_id
    ├── crud/
    │   ├── referral.py              # NEW: lock code, insert, list by inviter
    │   └── user.py                  # + create без commit (flush) для атомарной регистрации
    ├── services/
    │   ├── referral.py              # NEW: issue, activate, award_on_receipt
    │   ├── auth.py                  # + optional referral_code
    │   ├── receipt.py               # + ReferralService.award_on_receipt до commit
    │   ├── coupon.py                # + award_for_referral
    │   └── points.py                # + award_for_referral
    ├── schemas/
    │   ├── referral.py              # NEW: ReferralCodeOut, ReferralListOut
    │   └── auth.py                  # PhoneRequest.referral_code optional
    ├── routes/
    │   ├── referral.py              # GET/POST /referrals
    │   └── auth.py                  # без смены путей; тело уже с кодом
    ├── core/
    │   ├── referral.py              # wiring + env helpers
    │   └── server.py                # include referral_router
    └── entities/__init__.py         # import referral
.env.example                         # REFERRAL_* defaults

x5mobile/src/
├── api/client.ts                    # apiIssueReferral, apiListReferrals
├── hooks/useReferrals.ts            # NEW
├── components/screens/
│   └── referral-view.tsx            # NEW: код, share, статусы
├── app/index.tsx                    # screen 'referral' + вход с главной
└── components/screens/home-view.tsx # QuickAction «Пригласить»
# login-view.tsx / client.ts уже шлют 6-символьный referral_code

web/tests/webx5/
├── services/
│   └── test_referral_service.py
└── routes/
    ├── test_referral_routes.py
    └── test_auth.py                 # + сценарии с referral_code
```

**Structure Decision**: пакет `web/src/webx5` по RSI (как 007/009) плюс мобильный экран в `x5mobile/` (как 010). Логин уже принимает код — доделываем только обработку на сервере и экран приглашающего.

## Complexity Tracking

| Violation                           | Why Needed                                                                                         | Simpler Alternative Rejected Because                                                                 |
| ----------------------------------- | -------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Принцип II: отдельный экран реферала | Конституция и кейс уже держат реферал как концептуальный 4-й экран демо; выгода в рублях (I)       | Зашить код в профиль без статусов — хуже проверяется и прячет экономику связки                       |
| Принцип IV: нет полного расчёта маржи | PoC/демо; настройки калибруемые                                                                    | Блокировать план — команда явно просит механику; показ жюри как «пилот» по-прежнему запрещён         |

## Phase 0 / Phase 1 outputs

- [research.md](research.md) — R1–R12, без открытых NEEDS CLARIFICATION
- [data-model.md](data-model.md) — `referral_code`, `referral_link`, расширения coupon/points/discount
- [contracts/api-contracts.md](contracts/api-contracts.md) — `/referrals`, дельта `/register` `/login`
- [quickstart.md](quickstart.md) — curl-сценарии валидации
