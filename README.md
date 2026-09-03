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

## Сетап бэкенда

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
