# REST API на FastAPI

**Когда применять:** написание или ревью кода в `src/**/routes/`, `src/**/crud/`,
`src/**/schemas/`, `src/**/entities/`, `src/**/dependencies/`, `src/**/database/`,
`src/**/core/`, `src/**/utils/`, `src/**/main.py`.

SOLID, RSI, DI, structlog, тесты и lint — в [scripts-and-services.md](scripts-and-services.md).
Здесь только пакет и FastAPI-wiring.

Не клади API в `src/rag/` или `src/data/scripts/` (скрипты). Сервис — отдельный пакет под `src/`.

## Пакет

```text
src/<service>/
  main.py          # composition root: env, logging, serve
  core/            # сборка: логгер, DB-инстанс, wiring сервисов, server
  database/        # класс Database, mixins, session factory
  entities/        # SQLAlchemy-таблицы
  crud/            # Repository
  services/        # бизнес-логика
  routes/          # endpoints
  schemas/         # pydantic request/response
  dependencies/    # FastAPI Depends
  utils/           # хелперы (хеш пароля); не бизнес-логика и не SQL
```

| RSI | Каталог |
|---|---|
| Repository | `crud/` |
| Service | `services/` |
| Interface | `routes/` |

`core/` не дублирует слои — только создаёт объекты. `entities/` ≠ `schemas/`.

## Session

Sync engine. В запросе — `get_db` через Depends; вне запроса (worker, скрипт) — `get_sync_session`.

```python
class Database:
    def __init__(self, db_uri: str):
        self.engine = create_engine(db_uri, pool_pre_ping=True)
        self.session = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

    def get_db(self) -> Generator[Session, None, None]:
        with self.session() as session:
            yield session

    @contextmanager
    def get_sync_session(self) -> Generator[Session, None, None]:
        session = self.session()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
```

В `dependencies/`: `SessionDep = Annotated[Session, Depends(db.get_db)]`. Роут передаёт
`session` в service; service сессию не открывает.

## Routes

Роут принимает schema и session, вызывает service, возвращает schema. Без SQL и валидации бизнеса.

```python
# ❌ BAD — SQL в роуте
@router.post("/create")
def create_image(form: CreateImageForm, session: SessionDep) -> None:
    session.add(Image(**form.model_dump()))
    session.commit()

# ✅ GOOD
images_routes = APIRouter(prefix="/image", tags=["Image"])

@images_routes.post("/create")
async def create_image(form: CreateImageForm, session: SessionDep) -> None:
    await image_service.create(form, session)
```

Сервисы в роут попадают из `core/` (уже собранные), не `Service(...)` внутри хендлера.

## main.py

Side effects (dotenv, logging, serve) — только `main.py` и явная сборка в `core/`. Модули
`crud` / `services` / `routes` / `entities` на импорте БД и логгер не трогают.

```python
import asyncio
import os
from pathlib import Path

import structlog
from dotenv import load_dotenv

from .core.logging_config import configure_logging, default_log_dir
from .core.server import api

_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env")
load_dotenv()
configure_logging()
structlog.get_logger("app.startup").info(
    "app.starting",
    service=os.getenv("SERVICE_NAME", "api"),
    log_dir=str(default_log_dir()),
)

def main() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(api.server.serve())
    loop.run_forever()
```

## Авторизация

JWT stateless. Access — в JSON-теле, refresh — только HttpOnly cookie. Ролей в проверках нет:
либо есть валидный access, либо 401. Хеш пароля и encode/decode JWT — `utils/auth.py`; ключи
и TTL — из env.

```text
POST /register | /login
  → UserService выдаёт пару токенов
  → body: { "access_token": "..." }
  → Set-Cookie: refresh=...; HttpOnly; Path=/; SameSite=Lax; Secure (prod)
  register открытый, пользователь получает basic-роль в БД (для будущих задач, не для Depends)

Клиент хранит access сам и шлёт Authorization: Bearer на защищённые роуты.

GET  /health                              публичный
POST /register /login /refresh /logout   публичные
POST /answer и прочий RAG                CurrentUserUUID → 401 без Bearer

POST /refresh
  → cookie refresh → decode_refresh_token
  → новая пара: access в body, новый refresh в cookie (ротация)

POST /logout
  → сброс refresh-cookie; сервер токены не хранит и не ревокает
```

Cookie ставит только refresh. Не клади access в cookie и не читай refresh из Bearer.

```python
REFRESH_COOKIE = "refresh"

def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh_token,
        httponly=True,
        samesite="lax",
        secure=True,  # False только вне prod
        path="/",
    )

def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE, path="/")
```

```python
# ❌ BAD — access в cookie; refresh из Bearer; /answer без проверки
@answer_routes.post("/answer")
def post_answer(form: AnswerRequest, session: SessionDep) -> AnswerResponse:
    return rag_service.answer(form, session)

# ✅ GOOD
CurrentUserUUID = Annotated[uuid.UUID, Depends(_get_current_user_id)]  # HTTPBearer → decode_access_token

@answer_routes.post("/answer")
def post_answer(
    form: AnswerRequest,
    session: SessionDep,
    _user_id: CurrentUserUUID,
) -> AnswerResponse:
    return rag_service.answer(form, session)
```

Роуты auth тонкие: schema + session + `Response` → service. 409 только на конфликт username;
401 на неверный логин / битый refresh. `except Exception` → 409 нельзя. `is_user_admin` и
admin-Depends в этот API не добавлять.
