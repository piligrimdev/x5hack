# Персональные челленджи: единый микс из 4 слотов + vibe-категория месяца

Date: 2026-09-05. Brainstormed interactively (`superpowers:brainstorming`).

## Проблема и мотивация

Текущая генерация (`synth/challenges.py::generate_challenge_for_user`) делит
пользователей на два класса ещё до персонализации:

- `compute_frequency_saturation` — пользователи с ≥85 чеками в train-период
  получают **0 заданий** (`path="no_challenge"`).
- `compute_receptiveness` — пользователи со слабым/неконцентрированным
  паттерном покупок получают **все 3 слота из фиксированного пула**
  `GENERIC_CHALLENGES` (`path="generic"`) — никакой персонализации, включая
  LLM-слот, для них не пытается строиться вообще.

Запрос: убрать это ветвление. Каждый пользователь — включая тех, кто сейчас
считается "невосприимчивым" — должен получать один и тот же микс:
**2 персональных задания от LLM + 1 generic + 1 новая категория "vibe"**.
"Vibe" — тема месяца (например, "Здоровье", "Экономия"), которую в будущем
выберет сам пользователь; сейчас, до появления UI выбора, категория
назначается случайно и хранится, чтобы не меняться в течение месяца.

## Новый набор слотов

Заменяем текущие 3 слота на 4:

| Было (`ALL_SLOTS` / `PERSONAL_CHALLENGE_SLOTS`) | Стало |
|---|---|
| `llm` | `llm_habit` |
| `spend_threshold` (детерминированный) | `llm_discovery` |
| `category_expansion` (детерминированный) | `generic` |
| — | `vibe` (новый) |

- **`llm_habit`** — LLM-промпт на основе топ-категорий пользователя: усилить
  уже сложившуюся привычку (повторная покупка любимого товара/категории).
  По духу — LLM-версия того, что раньше делал детерминированный
  `build_spend_threshold_challenge`, но без жёсткого порога
  `min_purchase_count=6` — LLM работает и на тонких данных.
- **`llm_discovery`** — LLM-промпт на редко покупаемую категорию:
  стимулировать инкрементальную (не замещающую) покупку. LLM-версия духа
  `build_category_expansion_challenge`.
- **`generic`** — без изменений по механике: один оффер из фиксированного
  пула `GENERIC_CHALLENGES` (8 захардкоженных партнёрских офферов), выбор
  детерминированный по хешу `user_id`. Раньше это был fallback только для
  нерецептивных пользователей; теперь — штатный четвёртый слот для всех.
- **`vibe`** — новый, LLM-промпт с темой месяца (см. ниже), `target_categories`
  ограничены подмножеством категорий этой темы.

Оба LLM-слота теперь всегда вызывают LLM, для любого пользователя, включая
тех с пустой/тонкой историей покупок — существующий `build_personal_prompt`
уже корректно деградирует на скудных данных (пишет "—" в отсутствующих полях),
отдельный cold-start промпт не нужен.

## Важная поправка: что НЕ удаляется

`compute_receptiveness`, `compute_frequency_saturation`,
`build_spend_threshold_challenge`, `build_category_expansion_challenge` —
**остаются в `synth/challenges.py` без изменений**. Это не мёртвый код: их
использует `synth/simulation.py` (`route_for_simulation`,
`simulate_user_response`) — офлайн-симуляция экономического эффекта на
1-10 тыс. синтетических пользователей (гипотеза H2, `CONTEXT_PACK.md` §6),
полностью независимая от живой генерации челленджей. Удаление этих функций
сломало бы `synth/simulation.py` и три экономических канала
(frequency/basket/expansion), которые она считает.

Меняется только `generate_challenge_for_user` — единственная точка, где эти
функции определяли, какой микс слотов получит живой пользователь. Она
перестаёт их вызывать для этой цели и переходит на безусловный 4-слотовый
микс. Сами функции остаются доступны и протестированы как были, только
переориентируются на единственного оставшегося потребителя
(`synth/simulation.py`).

## Что удаляется из живого пути генерации (не файлы, а вызовы/ветки)

Из `synth/challenges.py::generate_challenge_for_user`:
- Вызов `compute_receptiveness` и ветка "не receptive → все слоты generic".
- Вызов `compute_frequency_saturation` и ветка `no_challenge`.
- Вызовы `build_spend_threshold_challenge`/`build_category_expansion_challenge`
  для построения слотов — их место занимают `llm_habit`/`llm_discovery`.

Из `web/src/webx5`:
- `EmptyReason.saturated` (`schemas/challenge.py`) и соответствующая ветка в
  `ChallengeService.get_current` (`services/challenge.py:219-226`), которая
  проверяла последний лог на `path == "no_challenge"` — с уходом
  saturation-гейта из живой генерации эта ветка недостижима.

Только сам факт "эти правила больше не решают, что получит живой
пользователь" фиксируется в `BACKLOG.md` — не как удалённая реализация, а
как переориентация: rule-based экономия LLM-вызовов и защита от переспама
были осмысленными компромиссами PoC для живой выдачи, от которых отказались
в пользу единого микса, но те же правила остаются рабочим инструментом
офлайн-симуляции эффекта.

`task.path` CHECK-constraint (`personal/generic/generic_fallback/
no_challenge/personal_dry_run`) не трогаем — значение `no_challenge` просто
перестаёт производиться, лишний allowed-value в CHECK не мешает и не требует
миграции для удаления (упрощение: не трогаем схему там, где не обязано).

## Vibe-категория: модель данных

Новые колонки на `users` (миграция Alembic, additive, nullable):

```python
class User(Base):
    ...
    vibe_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    vibe_month: Mapped[date | None] = mapped_column(Date, nullable=True)
```

Без CHECK-constraint на допустимые значения `vibe_category` — по аналогии с
`task.challenge_slot`, который тоже не ограничен CHECK'ом: список тем — это
поведение приложения, не инвариант схемы, и должен меняться без миграций.

**Назначение темы:** в `ChallengeAdapter.build_profile` (единственное место,
где уже есть доступ и к `User`, и к сборке профиля для синтетического
генератора):
- Если `user.vibe_month` уже равен первому числу текущего месяца —
  используется сохранённая `user.vibe_category`.
- Иначе — тема выбирается детерминированно-случайно (хеш от
  `f"{user_id}:{year}-{month}"`, в стиле уже существующего `_hash_index` в
  `synth/challenges.py`) и немедленно сохраняется в `users.vibe_category` /
  `users.vibe_month`.

Хранение (а не чистый пересчёт хешем на лету) — осознанный задел под будущий
ручной выбор темы пользователем: тогда просто эти же две колонки будут
перезаписываться выбором из UI, а не хешем.

**Набор тем** — новая константа `VIBE_CATEGORIES` в `synth/challenges.py`
(конфиг `config/synth_schema.yaml` не трогаем — он заморожен с 2026-09-04).
Партиция всех 20 разрешённых категорий каталога (исключая
`forbidden_categories`: `алкоголь`, `детское питание`) на 6 тем:

```python
VIBE_CATEGORIES: dict[str, list[str]] = {
    "Здоровье и лёгкость": [
        "молочные продукты и яйца", "овощи", "фрукты",
        "мясо и птица", "рыба и морепродукты", "орехи и сухофрукты",
    ],
    "Экономия и запасы": [
        "бакалея", "консервация", "масла и жиры", "соусы и приправы",
    ],
    "Побаловать себя": [
        "кондитерка", "сладости и снеки", "напитки",
    ],
    "Уют и порядок дома": [
        "товары для дома", "бытовая химия", "личная гигиена",
    ],
    "Быстро и просто": [
        "готовая еда", "хлеб и выпечка", "заморозка",
    ],
    "Забота о питомце": [
        "товары для животных",
    ],
}
```

## Vibe-слот: генерация

Новая функция `build_vibe_prompt(profile, config, max_reward_rub) ->
tuple[str, str]` в `synth/challenges.py`, структурно как
`build_personal_prompt`, но:
- Указывает тему месяца (`profile["vibe_category"]`) прямо в system-промпте.
- Ограничивает допустимые `target_categories` списком
  `VIBE_CATEGORIES[profile["vibe_category"]]` (пересечение с
  forbidden уже пусто по построению словаря).

`parse_and_validate_challenge` получает новый опциональный параметр
`allowed_categories: set[str] | None = None`: если передан, `target_categories`
из ответа LLM обязаны быть его подмножеством (иначе `ValueError`, как и для
`forbidden_categories`). Обратно совместим — существующие вызовы для
`llm_habit`/`llm_discovery` его не передают.

`profile["vibe_category"]` для офлайн-вызовов (`synth/cli.py`,
`reference_profiles.py`), где нет доступа к `users`-таблице, вычисляется тем
же хешем внутри `generate_challenge_for_user`, если ключ отсутствует в
профиле — так синтетический генератор остаётся чистой функцией без
зависимости от БД, а веб-слой лишь опционально передаёт уже сохранённое
значение через `profile`.

## Изменения в web/src/webx5

- `entities/user.py` — добавить `vibe_category`, `vibe_month`.
- Новая Alembic-миграция (head → новая ревизия): `ALTER TABLE users ADD
  COLUMN vibe_category VARCHAR(50), ADD COLUMN vibe_month DATE`.
- `services/challenge_adapter.py::build_profile` — логика назначения/чтения
  vibe-темы (см. выше), плюс запись `vibe_category` в возвращаемый профиль.
- `services/challenge.py`:
  - `ALL_SLOTS = ("llm_habit", "llm_discovery", "generic", "vibe")`.
  - `remaining_slots = 4 - len(active_tasks)` (было `3 -`).
  - Удалить ветку `saturated` в `get_current`.
- `schemas/challenge.py` — убрать `EmptyReason.saturated`.
- `tasks/generation.py` — дефолт `count: int = 4` (было `3`).

## Mobile

`x5mobile/src/hooks/useChallenges.ts` и
`x5mobile/src/components/screens/challenges-view.tsx` рендерят список без
жёсткой завязки на количество (просто карточки active/history) — по отчёту
исследования там нет хардкода "3". Требуется точечная проверка при
реализации, что 4-я карточка отображается корректно (скролл/сетка), но
архитектурных изменений экрана не предполагается.

## Тесты

- `tests/synth/test_challenges.py` — **сохранить** существующие тесты
  `compute_receptiveness`/`compute_frequency_saturation`/
  `build_spend_threshold_challenge`/`build_category_expansion_challenge`
  как есть (эти функции продолжают жить и тестируются независимо от
  `generate_challenge_for_user`). Удалить/переписать нужно только тесты,
  которые проверяли СТАРОЕ поведение `generate_challenge_for_user`,
  завязанное на них (маршрутизацию в `no_challenge`/полный generic-fallback
  через эти функции) и старые имена слотов. Добавить тесты на
  `build_vibe_prompt`, `VIBE_CATEGORIES` (партиция покрывает все 20
  разрешённых категорий без пересечений — инвариант стоит проверить тестом),
  `parse_and_validate_challenge` с `allowed_categories`, и на
  `generate_challenge_for_user` — теперь всегда 4 записи для любого профиля
  (включая профиль с 0 чеками), с новыми именами слотов.
- `tests/synth/test_simulation.py` — не трогать: `synth/simulation.py`
  не меняется в этой фиче, его тесты продолжают проверять
  `compute_receptiveness`/`build_spend_threshold_challenge`/etc. через
  `route_for_simulation`, что остаётся валидным.
- `tests/webx5/services/test_challenge*.py` (если есть) — обновить под новый
  `ALL_SLOTS`/лимит 4; добавить тест на назначение/персистентность
  `vibe_category`/`vibe_month` в `build_profile`.

## Риск: hit-rate метрика хакатона

`CONTEXT_PACK.md` §H2 фиксирует hit-rate 87.5% (35/40) на 40 эталонных
профилях, посчитанный офлайн-скриптом `synth/cli.py` поверх **текущей**
версии `generate_challenge_for_user`. Эта переработка меняет функцию
полностью — старая цифра перестаёт быть валидной для новой логики.

Не блокирует реализацию, но: после мержа нужно перезапустить
`synth/cli.py` скоринг и обновить статус в `CONTEXT_PACK.md` (дата, новое
значение hit-rate) — иначе документ будет утверждать неактуальный результат.
Отдельная задача, не часть implementation plan этой фичи по коду.

Экономическая симуляция эффекта (`synth/simulation.py`, тот же §6 H2) —
**не затрагивается и её результаты не устаревают**: она использует
`compute_receptiveness`/`build_spend_threshold_challenge`/etc. напрямую
через `route_for_simulation`, независимо от `generate_challenge_for_user`,
и эта фича их не меняет.

## Вне скоупа

- UI выбора vibe-категории пользователем — по запросу сейчас категория
  только назначается случайно; сам выбор — будущая фича.
- Кросс-слотовая дедупликация категорий между `llm_habit`/`llm_discovery`/
  `vibe` (чтобы 4 карточки не могли случайно указывать на одну и ту же
  категорию) — YAGNI для этой итерации, риск минимальный (4 независимых
  подмножества из ~20 категорий), можно добавить позже при необходимости.
