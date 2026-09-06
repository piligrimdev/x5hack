# Implementation Plan: Лидерборд экономии магазина

**Branch**: `010-savings-leaderboard` | **Date**: 2026-09-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/010-savings-leaderboard/spec.md`

## Summary

Персональный рейтинг «своего» магазина по **проценту экономии** за текущий месяц (Europe/Moscow). Home store = мода `store_id` в последних 20 чеках. `GET /leaderboard` считает снимок на чтении (без новых таблиц). Мобильный клиент открывает экран по тапу на блок статистики экономии на Аппи и только рисует ответ сервера.

## Technical Context

**Language/Version**: Python 3.11+ (бэкенд); TypeScript strict (Expo / React Native, клиент)

**Primary Dependencies**: FastAPI (sync), SQLAlchemy (sync), Pydantic, structlog, pytest; мобильный — существующие `apiFetch`, state-навигация в `index.tsx`

**Storage**: PostgreSQL, только чтение `receipts` / `receipt_items` / `stores`. Новых таблиц и обязательных миграций нет

**Testing**: pytest, зеркало `web/tests/webx5/`; unit на `LeaderboardService` (home store, ранг, пустые статусы); route-тест 401/200. Клиент — ручной прогон quickstart Сценарий 7

**Target Platform**: Linux server (Docker) + iOS/Android через Expo; Web — вспомогательно

**Project Type**: mobile + API

**Performance Goals**: ответ и первый кадр рейтинга < 3 с в 95% (SC-006); PoC-нагрузка (сотни пользователей)

**Constraints**: клиент не считает чужие места; в JSON нет ПД; рубли не тай-брейк; RSI + DI; без side effects на импорте

**Scale/Scope**: синтетические пользователи хакатона; топ-10 + строка «Вы»; один экран поверх Аппи

## Constitution Check

_GATE: до Phase 0 и повторно после Phase 1._

| Принцип                                 | Статус        | Обоснование                                                                                                                                                         |
| --------------------------------------- | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| I — Экономия как метрика                | ✅            | Место = доля сэкономленных рублей (скидки + кешбек) / база месяца, не очки активности. Рублёвая сводка на Аппи не убирается                                         |
| II — ≤2 действия / три механики         | ✅            | Это механика **рейтинга** (уже в конституции), не четвёртая игра. Вход: 1 тап с Аппи                                                                                |
| III — ИИ-персонализация                 | ✅ н/п        | Челленджи и LLM не трогаем                                                                                                                                          |
| IV — Юнит-экономика                     | ✅            | Наград за место нет, бюджет лояльности не тратится. Демонстрация жюри как «пилот с призами за топ» запрещена, пока нет расчёта — но призов в скоупе нет             |
| V — Privacy                             | ⚠️ отклонение | Строки анонимны (нет ФИО/адреса/телефона/UUID). Единица когорты — **магазин**, не дом/район. Запрошено спекой; `address` не отдаём                                  |
| RSI                                     | ✅            | `crud/leaderboard.py` + `services/leaderboard.py` + `routes/leaderboard.py`                                                                                          |
| DI                                      | ✅            | Репозиторий в конструктор сервиса; wiring в `core/leaderboard.py`                                                                                                   |
| Контролируемая инициализация            | ✅            | Без side effects на импорте crud/services/routes; сервис собирается в `core/`                                                                                       |
| Тесты                                   | ✅            | Unit на Service: мода/тай-брейк, процент vs рубли, competition rank, `no_home_store`, `me is null`                                                                  |
| Mobile Technical Standards              | ✅            | Функциональный экран + хук; `StyleSheet`; навигация через существующий state-router (не прямой `react-navigation`); Expo managed                                    |

Повтор после Phase 1: те же статусы. Дизайн не добавляет таблиц ПД, не вводит награды за место и не считает рейтинг на клиенте. Отклонение V (магазин vs район) не усилилось.

## Project Structure

### Documentation (this feature)

```text
specs/010-savings-leaderboard/
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
web/src/webx5/
├── core/
│   ├── leaderboard.py          # NEW: wiring LeaderboardRepository + LeaderboardService
│   └── server.py               # include leaderboard_router
├── crud/
│   └── leaderboard.py          # NEW: list_recent_store_votes, list_monthly_savings
├── services/
│   └── leaderboard.py          # NEW: home store, percent, rank, snapshot
├── schemas/
│   └── leaderboard.py          # NEW: LeaderboardOut, StoreOut, MeOut, EntryOut
└── routes/
    └── leaderboard.py          # NEW: GET /leaderboard

web/tests/webx5/
├── services/
│   └── test_leaderboard_service.py
└── routes/
    └── test_leaderboard_routes.py

x5mobile/src/
├── app/index.tsx               # Screen 'leaderboard'; keep Appi mounted; tab=appi
├── hooks/useSavingsLeaderboard.ts
└── components/screens/
    ├── appi-view.tsx           # Pressable chartCard → onOpenLeaderboard
    └── savings-leaderboard-view.tsx
```

**Structure Decision**: бэкенд в пакете `web/src/webx5` (RSI как 007–009) плюс клиент `x5mobile/` — без экрана рейтинг не выполняется FR-001. Отдельного native-модуля нет.

## Complexity Tracking

| Violation                                      | Why Needed                                                                 | Simpler Alternative Rejected Because                                      |
| ---------------------------------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Принцип V: когорта = магазин, не дом/район     | Явное требование спеки (последние 20 покупок → самый частый магазин)       | Районный рейтинг из бэклога — другая фича, нет geo-агрегации пользователей |

Принцип I не нарушен: процент — нормированные рубли экономии. Принцип II не нарушен: это сам рейтинг, не новая мини-игра.

## Phase 0 / Phase 1 outputs

- [research.md](research.md) — R1–R14, без открытых NEEDS CLARIFICATION
- [data-model.md](data-model.md) — вычисляемые HomeStore / MonthlySavingsRate / LeaderboardSnapshot
- [contracts/api-contracts.md](contracts/api-contracts.md) — `GET /leaderboard`
- [quickstart.md](quickstart.md) — curl + мобильный вход
