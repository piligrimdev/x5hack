# X5 Loyalty Mobile App — Проект на хакатон

ИИ-программа лояльности с персональными челленджами, прогрессией аватара и отслеживанием экономии.

## Структура проекта

- **`/x5mobile`** — мобильное приложение на React Native + Expo (iOS/Android)
- **`/web`** — Python бэкенд (FastAPI + PostgreSQL)

```
web/
├── pyproject.toml           # Зависимости (Poetry)
├── poetry.lock
├── alembic.ini              # Конфиг Alembic
├── alembic/
│   ├── env.py               # Читает Base из entities, DATABASE_URL из env
│   └── versions/            # Ревизии миграций
└── src/webx5/
    ├── main.py              # Точка входа: load_dotenv + logging + uvicorn
    ├── core/
    │   ├── db.py            # Инстанс Database
    │   ├── server.py        # FastAPI app + роутеры
    │   └── logging_config.py
    ├── database/
    │   └── database.py      # class Database (get_db, get_sync_session)
    ├── entities/            # SQLAlchemy DeclarativeBase + таблицы
    ├── crud/                # Репозитории (доступ к данным)
    ├── services/            # Бизнес-логика
    ├── routes/              # FastAPI endpoints
    │   └── health.py        # GET /health
    ├── schemas/             # Pydantic request/response модели
    ├── dependencies/
    │   └── db.py            # SessionDep
    └── utils/

tests/webx5/
└── routes/
    └── test_health.py
```

## Запуск через Docker (рекомендуется)

### Требования

- **Docker Desktop** установлен и запущен

### Запуск

```bash
# 1. Скопировать .env (значения по умолчанию работают без правок)
cp .env.example .env

# 2. Собрать и запустить весь стек
docker compose up --build

# Для работы AI-ассистента корзины (POST /basket/assistant) нужен реальный
# OPENROUTER_API_KEY в .env — с плейсхолдером по умолчанию этот один
# эндпоинт не работает, остальное приложение — без изменений.

# Сервис доступен на http://localhost:8000
# Проверка: curl http://localhost:8000/health → {"status":"ok"}
# Документация: http://localhost:8000/docs (Scalar UI)
```

### Полезные команды

```bash
docker compose up -d          # Запуск в фоне
docker compose down           # Остановить стек
docker compose down -v        # Остановить и удалить данные БД
docker compose logs -f web    # Логи веб-сервера
docker compose build          # Пересобрать образ без запуска
```

> Миграции БД применяются автоматически при каждом старте контейнера.

### Заполнение данными (seed-скрипты)

Все скрипты идемпотентны: повторный запуск не создаёт дубликатов.

#### 1. Товары (из JSON/JSONL файла)

```bash
docker compose run --rm --entrypoint python \
  -v "/абсолютный/путь/к/unique_products.json:/tmp/products_data.json" \
  -e SEED_FILE_PATH=/tmp/products_data.json \
  web scripts/seed_products.py
```

#### 2. Магазины (из датасета)

```bash
docker compose run --rm --entrypoint python \
  -e SEED_FILE_PATH=/data/dataset \
  web scripts/seed_stores.py
```

> Сканирует датасет и создаёт StoreFormat на каждую сеть и Store на каждую (сеть, район) пару.

#### 3. Скидки (синтетические, из датасета)

```bash
docker compose run --rm --entrypoint python \
  -e SEED_FILE_PATH=/data/dataset \
  web scripts/seed_discounts.py
```

> Создаёт Discount записи для каждой уникальной пары (категория, процент скидки) из промо-товаров.

#### 4. Чеки и карты лояльности (из датасета)

```bash
# Все пользователи (10 000, медленно)
docker compose run --rm --entrypoint python \
  -e SEED_FILE_PATH=/data/dataset \
  web scripts/seed_receipts.py

# Ограниченная выборка (рекомендуется для теста)
docker compose run --rm --entrypoint python \
  -e SEED_FILE_PATH=/data/dataset \
  -e SEED_LIMIT=100 \
  web scripts/seed_receipts.py
```

> Требует предварительного запуска seed_products.py, seed_stores.py и seed_discounts.py.
> Также создаёт `User` на каждую синтетическую карту лояльности и в конце печатает
> несколько демо-логинов (`user_id=... phone=...`) — по этому телефону можно
> залогиниться (`POST /login`) пользователем с реальной историей покупок.

#### Генерация демо-данных без датасета

```bash
# Магазины: X5-сети × московские округа (24 магазина)
docker compose exec web python scripts/generate_stores.py

# Скидки: акции / лояльность / персональные / уценки (47 записей)
docker compose exec web python scripts/generate_discounts.py
```

> Скрипты идемпотентны и не требуют файла датасета — данные захардкожены.
> Запускать в порядке: сначала `generate_stores`, затем `generate_discounts`
> (скидки типа `by_format` ссылаются на форматы магазинов).

#### Порядок запуска для полного сидирования из датасета

```bash
seed_products → seed_stores → seed_discounts → seed_receipts
```

---

## Сетап бэкенда (без Docker)

### Требования

- **Python** >= 3.12
- **Poetry** (`pip install poetry`)
- **PostgreSQL** (локально или через Docker)

### Установка и запуск

```bash
# 1. Скопировать и заполнить .env
cp .env.example .env
# Отредактировать DATABASE_URL в .env

# 2. Установить зависимости
cd web
poetry install

# 3. Применить миграции
poetry run alembic upgrade head

# 4. Запустить сервер
poetry run python -m webx5
# Сервер доступен на http://localhost:8000
# Проверка: curl http://localhost:8000/health → {"status":"ok"}
```

## Сетап мобильного приложения

### Требования

- **Node.js** >= 18
- **npm** или **yarn**
- **Xcode Command Line Tools** (для iOS):
  ```bash
  xcode-select --install
  ```

### Установка

```bash
cd x5mobile
npm install
```

### Запуск приложения

#### Режим разработки (с горячей перезагрузкой)

```bash
npm start
```

Затем выбери платформу:

- Нажми `i` для iOS Simulator
- Нажми `a` для Android Emulator
- Нажми `w` для веб-версии
- Отсканируй QR-код приложением **Expo Go** (физическое устройство)

#### Быстрый запуск конкретной платформы

```bash
npm run ios      # iOS Simulator
npm run android  # Android Emulator
npm run web      # Веб-браузер
```

### Сборка для продакшена

#### iOS

```bash
# Требует полной установки Xcode
cd x5mobile/ios
pod install
cd ..
eas build --platform ios
```

### Структура проекта

```
x5mobile/
├── src/
│   ├── app/              # Страницы Expo Router
│   │   ├── _layout.tsx   # Корневой layout
│   │   └── index.tsx     # Экран приветствия
│   ├── components/       # Переиспользуемые компоненты
│   ├── constants/        # Тема, отступы, etc.
│   └── hooks/            # Кастомные React hooks
├── assets/               # Изображения, иконки, шрифты
├── app.json              # Конфиг Expo
├── tsconfig.json         # Конфиг TypeScript
└── package.json          # Зависимости и скрипты
```

### Безопасность и игнорируемые файлы

**Уже настроено в `.gitignore`:**

- `node_modules/` — зависимости
- `.env*.local` — переменные окружения
- `ios/`, `android/` — сгенерированные нативные папки
- `*.p8`, `*.p12`, `*.mobileprovision` — сертификаты подписи
- `.DS_Store`, `*.pem` — системные/SSL файлы

**Секретов, API ключей и больших файлов не найдено** ✓

### Основные зависимости

- **Expo** — фреймворк для кроссплатформенной разработки
- **React Native** — фреймворк для мобильного UI
- **Expo Router** — файловая маршрутизация (как Next.js)
- **React Native Reanimated** — плавные анимации
- **TypeScript** — типизация

### Советы по разработке

**Горячая перезагрузка:**

- Измени любой файл в `src/` → автоматическая перезагрузка в эмуляторе/устройстве
- Для изменений нативного кода нужна пересборка

**Меню отладки (в Simulator/Emulator):**

- iOS: `cmd+d`
- Android: `cmd+m`

**claude code**

(Паша) для работы со спеккитом юзайте команду ниже

```
specify init --here --integration claude
```

без нее, но с указанием пути до репо спеккита у меня не работало + с указнием пути до репо я бы не коммитил `.claude/settings.json`
