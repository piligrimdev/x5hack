# Tasks: Dual-Consumer Authorization

**Input**: Design documents from `specs/003-auth/`

**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/auth.md ✓

**Organization**: Задачи сгруппированы по пользовательским историям. Каждая история независимо тестируема.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Можно запускать параллельно (разные файлы, нет зависимостей)
- **[Story]**: К какой пользовательской истории относится задача

---

## Phase 1: Setup (Зависимости и конфигурация)

**Purpose**: Подготовить зависимости и конфигурацию окружения перед реализацией

- [X] T001 Добавить `PyJWT>=2.8` и `phonenumbers` в `web/pyproject.toml` через `poetry add` и обновить `poetry.lock`
- [X] T002 Добавить в `.env.example` переменные: `JWT_SECRET_KEY`, `JWT_TTL_DAYS=7`, `JWT_REFRESH_TTL_DAYS=14`, `TERMINAL_TOKEN`
- [X] T003 [P] Обновить `specs/003-auth/contracts/auth.md` — добавить `refresh_token` к ответам `/register` и `/login`; добавить контракт `POST /refresh`

**Checkpoint**: Зависимости установлены, окружение настроено

---

## Phase 2: Foundational (Сущность, утилиты, схемы)

**Purpose**: Заложить фундамент, который блокирует все пользовательские истории

⚠️ **CRITICAL**: Без этой фазы ни одна история не может быть реализована

- [X] T004 Создать `web/src/webx5/entities/user.py` — SQLAlchemy-модель `User` (поля: `id: UUID PK`, `phone: str UNIQUE`, `created_at: datetime`); добавить импорт `User` в `web/src/webx5/entities/__init__.py`
- [X] T005 Создать Alembic-миграцию `web/alembic/versions/<hash>_add_users_table.py` — таблица `users` с `id UUID PK DEFAULT gen_random_uuid()`, `phone VARCHAR(20) UNIQUE NOT NULL`, `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- [X] T006 [P] Реализовать `web/src/webx5/utils/auth.py` — чистые функции: `normalize_phone(raw: str) -> str` (phonenumbers, E.164, ValueError при невалидном), `encode_access_jwt(user_id: UUID) -> str` (typ=access, exp=7d), `decode_access_jwt(token: str) -> UUID` (raises HTTPException 401), `encode_refresh_jwt(user_id: UUID) -> str` (typ=refresh, exp=14d), `decode_refresh_jwt(token: str) -> UUID` (проверяет typ=refresh, raises HTTPException 401)
- [X] T007 [P] Создать `web/src/webx5/schemas/auth.py` — Pydantic-схемы: `PhoneRequest(phone: str)` с `@field_validator` для нормализации телефона через `normalize_phone`, `TokenPairResponse(access_token: str, refresh_token: str)`, `RefreshRequest(refresh_token: str)`

**Checkpoint**: Сущность, миграция, утилиты и схемы готовы — можно начинать истории

---

## Phase 3: US1 + US4 — Регистрация и защита эндпоинтов (Priority: P1) 🎯 MVP

**Goal**: Новый пользователь регистрируется по телефону и получает пару токенов; защищённые эндпоинты требуют валидный access token

**Independent Test**: `POST /register` с новым телефоном → 200 + `{access_token, refresh_token}`; `GET /me` с токеном → 200; `GET /me` без токена → 401

### Implementation для US1 + US4

- [X] T008 [US1] Реализовать `web/src/webx5/crud/user.py` — класс `UserRepository` (stateless) с методами `get_by_phone(session, phone) -> User | None` и `create(session, phone) -> User` (UUID генерируется через `uuid.uuid4()` на стороне приложения)
- [X] T009 [US1] Реализовать `web/src/webx5/services/auth.py` — класс `AuthService(user_repo: UserRepository)` с методом `register(form: PhoneRequest, session: Session) -> TokenPairResponse`: нормализация → проверка уникальности → 409 при дубликате → создание → выдача пары токенов
- [X] T010 [US4] Реализовать `web/src/webx5/dependencies/auth.py` — `CurrentUserUUID: Annotated[UUID, Depends(_get_current_user_id)]` где `_get_current_user_id` декодирует Bearer-токен через `decode_access_jwt`; при ошибке → HTTPException 401
- [X] T011 [US1] Реализовать роутер `web/src/webx5/routes/auth.py` — `POST /register` (принимает `PhoneRequest`, `SessionDep`, вызывает `auth_service.register`) и `GET /me` (принимает `CurrentUserUUID`, возвращает `{"user_id": str(uuid)}`)
- [X] T012 [US1] Собрать синглтон сервиса в `web/src/webx5/core/auth.py` — `user_repo = UserRepository()`, `auth_service = AuthService(user_repo=user_repo)`; подключить `auth_router` в `web/src/webx5/core/server.py`

**Checkpoint**: `POST /register` работает, `GET /me` защищён — US1 и US4 полностью функциональны

---

## Phase 4: US2 — Повторный вход зарегистрированного пользователя (Priority: P2)

**Goal**: Существующий пользователь входит по телефону и получает новую пару токенов

**Independent Test**: Зарегистрироваться → `POST /login` с тем же номером → 200 + `{access_token, refresh_token}`; несуществующий номер → 404

### Implementation для US2

- [X] T013 [US2] Добавить метод `login(form: PhoneRequest, session: Session) -> TokenPairResponse` в `AuthService` в `web/src/webx5/services/auth.py`: нормализация → поиск → 404 если не найден → выдача пары токенов
- [X] T014 [US2] Добавить `POST /login` в `web/src/webx5/routes/auth.py` (принимает `PhoneRequest`, `SessionDep`, вызывает `auth_service.login`)

**Checkpoint**: `POST /login` работает независимо от регистрации

---

## Phase 5: US5 — Обновление токенов через refresh (Priority: P2)

**Goal**: Клиент обменивает refresh token на новую пару access + refresh без повторного входа

**Independent Test**: Получить пару токенов → `POST /refresh` с refresh_token → 200 + новая пара; просроченный/чужой тип токен → 401

### Implementation для US5

- [X] T015 [US5] Добавить метод `refresh(req: RefreshRequest, session: Session) -> TokenPairResponse` в `AuthService` в `web/src/webx5/services/auth.py`: `decode_refresh_jwt(req.refresh_token)` → получить user_id → проверить существование пользователя → выдать новую пару
- [X] T016 [US5] Добавить `POST /refresh` в `web/src/webx5/routes/auth.py` (принимает `RefreshRequest`, `SessionDep`, вызывает `auth_service.refresh`)

**Checkpoint**: `POST /refresh` работает; access token в теле `/refresh` отклоняется с 401

---

## Phase 6: US3 — Аутентификация кассового аппарата (Priority: P2)

**Goal**: Касса с `X-Terminal-Token` получает доступ к кассовым эндпоинтам; JWT пользователя на кассовых эндпоинтах → 401

**Independent Test**: `GET /terminal/ping` с `X-Terminal-Token: <valid>` → 200; без заголовка → 401; с неверным → 401

### Implementation для US3

- [X] T017 [US3] Добавить `TerminalTokenDep` в `web/src/webx5/dependencies/auth.py` — функция `verify_terminal_token(x_terminal_token: str = Header(...)) -> None` сравнивает с `os.environ["TERMINAL_TOKEN"]`; несовпадение → HTTPException 401; `TerminalTokenDep = Annotated[None, Depends(verify_terminal_token)]`
- [X] T018 [US3] Добавить `GET /terminal/ping` в `web/src/webx5/routes/auth.py` (использует `TerminalTokenDep`, возвращает `{"status": "ok"}`)

**Checkpoint**: Кассовый эндпоинт изолирован от пользовательских токенов

---

## Phase 7: Polish & Validation

**Purpose**: Тесты и финальная проверка по quickstart.md

- [X] T019 [P] Написать unit-тесты `web/tests/webx5/utils/test_auth.py` — `normalize_phone` (5+ форматов, невалидный номер), `encode/decode_access_jwt` (round-trip, истечение, неверный тип), `encode/decode_refresh_jwt` (round-trip, истечение, неверный тип)
- [X] T020 [P] Написать интеграционные тесты `web/tests/webx5/routes/test_auth.py` — `POST /register` (201/409/422), `POST /login` (200/404), `POST /refresh` (200/401), `GET /me` (200/401), `GET /terminal/ping` (200/401)
- [ ] T021 Применить миграцию и прогнать все 9 сценариев из `specs/003-auth/quickstart.md` вручную через curl

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: Нет зависимостей — можно начинать сразу
- **Phase 2 (Foundational)**: Зависит от Phase 1 — блокирует все истории
- **Phases 3–6 (Stories)**: Зависят от Phase 2; между собой — частично (US2/US5/US3 используют код из US1)
  - US2 (T013, T014) зависит от T008–T012 (нужен `AuthService` и `UserRepository`)
  - US5 (T015, T016) зависит от T006 (нужен `decode_refresh_jwt`) и T009 (нужен `AuthService`)
  - US3 (T017, T018) независима от US1/US2/US5 — можно реализовать после Phase 2
- **Phase 7 (Polish)**: Зависит от завершения всех историй

### Параллельные возможности

- T006 и T007 в Phase 2 параллельны (разные файлы)
- T003 в Phase 1 параллелен с T001/T002
- T019 и T020 в Phase 7 параллельны
- US3 (Phase 6) независима и может идти параллельно с US2 (Phase 4) или US5 (Phase 5)

---

## Parallel Example: Phase 2

```
Параллельно:
  T006 — web/src/webx5/utils/auth.py
  T007 — web/src/webx5/schemas/auth.py
Последовательно после T004:
  T005 — alembic migration (зависит от entities/user.py)
```

---

## Implementation Strategy

### MVP First (US1 + US4)

1. Phase 1: Setup (T001, T002)
2. Phase 2: Foundational (T004–T007)
3. Phase 3: US1 + US4 (T008–T012)
4. **STOP и проверить**: `POST /register` + `GET /me` работают
5. Задеплоить/задемонстрировать MVP

### Incremental Delivery

1. Setup + Foundational → Фундамент готов
2. US1 + US4 → Регистрация и защита (MVP демо)
3. US2 → Повторный вход
4. US5 → Refresh-токены
5. US3 → Кассовая авторизация
6. Polish → Тесты и валидация

---

## Notes

- `[P]` = разные файлы, без зависимостей между собой
- `[Story]` — метка пользовательской истории для трассируемости
- `UserRepository` stateless: session передаётся в каждый метод, не хранится в `__init__`
- `auth_service` — синглтон в `core/auth.py`, импортируется в роуты
- Миграцию применять через `docker compose exec web alembic upgrade head`
