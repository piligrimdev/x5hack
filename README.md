# X5 Loyalty Mobile App — Проект на хакатон

ИИ-программа лояльности с персональными челленджами, прогрессией аватара и отслеживанием экономии.

## Структура проекта

- **`/x5mobile`** — мобильное приложение на React Native + Expo (iOS/Android)
- **`/backend`** (TBD) — Python бэкенд для генерации ИИ-челленджей и рекомендаций

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
