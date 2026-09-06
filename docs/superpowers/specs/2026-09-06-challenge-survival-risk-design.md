# Персональные челленджи: отбор категорий через survival-анализ (Kaplan-Meier) вместо LLM

Date: 2026-09-06. Brainstormed interactively (`superpowers:brainstorming`).

## Проблема и мотивация

Сейчас `generate_challenge_for_user` (`synth/challenges.py:958`) заполняет 5
слотов (`CHALLENGE_SLOTS`, `synth/challenges.py:926`):
`llm_habit`, `llm_discovery`, `llm_basket`, `generic`, `vibe`.

Из них категорию под персонализацию сегодня выбирают:

- `llm_habit`/`llm_discovery` — реальный вызов LLM (`_run_llm_slot`,
  `synth/challenges.py:1020`), которому в промпте передаются
  `habitual_categories` (топ-5 по числу строк чека за **90 дней**,
  `ChallengeAdapter.build_profile`,
  `web/src/webx5/services/challenge_adapter.py:186`), а дальше LLM сама
  решает, какую конкретно категорию и товар предложить.
- `generic` — на уровне `synth` это фиксированный пул `GENERIC_CHALLENGES`
  (`_pick_distinct_generic_offer`), но на web-границе
  (`_use_deterministic_mechanics`, `web/src/webx5/services/challenge.py:43`)
  всегда подменяется на `build_category_expansion_challenge` — **наименее**
  покупаемую категорию из `config.categories` за train-период.

Ни один из этих путей не смотрит на **время**: сколько дней прошло с
последней покупки категории относительно того, как часто категорию вообще
принято повторно покупать. Единственное место в проекте, где эта величина
вообще фигурирует — скрытое (не наблюдаемое генератором) поле
`repurchase_intervals: dict[category, days]` в
`synth/simulation_truth.py:28,111`, которое используется только для
генерации синтетических чеков и для расчёта эталонного answer key (hit-rate
H2, `CONTEXT_PACK.md`). Задача этой фичи — оценивать **наблюдаемый** аналог
этой величины через survival-анализ и сделать его основным сигналом отбора
категории.

## Что меняется, что нет

Меняется отбор категории **только** для `llm_habit`, `llm_discovery`,
`generic`. Для всех трёх LLM выключается полностью (ни вызова, ни текста от
модели) — текст челленджа собирается из Python-шаблонов.

Не меняется:

- `llm_basket` (уже детерминирован, `build_basket_spend_challenge`) и `vibe`
  (LLM с темой месяца) — другая роль, не про категорийный отток, не трогаем.
- `compute_receptiveness`/`compute_frequency_saturation`/
  `build_spend_threshold_challenge`/`build_category_expansion_challenge` —
  остаются как есть, их единственный оставшийся потребитель —
  `synth/simulation.py` (офлайн-симуляция экономического эффекта), как и
  зафиксировано в `2026-09-05-challenge-mix-vibe-design.md`.
  `build_category_expansion_challenge` **перестаёт** быть тем, что
  подставляется в живой `generic`-слот (см. ниже), но продолжает
  существовать и тестироваться для симуляции.
- Структура `CHALLENGE_SLOTS`, `Task`/`TaskCriterion`/`TaskItem`, схема БД —
  без изменений.

## 1. `synth/survival.py` — KM-эстиматор (новый модуль, без новых зависимостей)

`web/pyproject.toml` сегодня не содержит ни одной численной библиотеки
(нет numpy/pandas/scipy, тем более `lifelines`/`scikit-survival`). Тянуть их
ради одной Kaplan-Meier кривой — избыточно (KISS): пишем свой минимальный
product-limit эстиматор на чистом Python.

```python
@dataclass(frozen=True)
class SurvivalCurve:
    times: tuple[int, ...]       # различные времена событий (дни), по возрастанию
    survival: tuple[float, ...]  # S(t) сразу ПОСЛЕ времени times[i]

    def survival_at(self, days: int) -> float:
        """Ступенчатая S(t). До первого события — 1.0. После последнего
        наблюдённого события — последнее посчитанное S (не экстраполируем
        к 0 — за пределами данных мы ничего не знаем)."""

    def median_survival_days(self) -> int | None:
        """Наименьшее t, при котором S(t) <= 0.5; None, если кривая ни разу
        не опускается до 0.5 в пределах наблюдений (используется для дедлайна)."""


def fit_km_curve(durations: list[int], censored: list[bool]) -> SurvivalCurve:
    """Стандартный product-limit оценщик:
    S(t) = произведение по всем временам событий t_i <= t из (1 - d_i / n_i),
    где d_i — число НЕцензурированных событий в момент t_i, n_i — число
    наблюдений "под риском" (duration >= t_i) в этот момент.
    Цензурированные наблюдения уменьшают n_i для более поздних t, но не
    дают события — стандартная обработка right-censoring."""


def fit_population_curves(
    purchase_dates_by_user: dict[str, dict[str, list[date]]],
    as_of: date,
) -> dict[str, SurvivalCurve]:
    """Вход: per-user per-category отсортированные даты покупок (ВСЯ
    история, без окна 90 дней — см. раздел 3). Для каждой категории строит
    список (interval_days, is_censored) по ВСЕМ пользователям:
      - между двумя последовательными покупками одной категории одним
        пользователем -> naблюдённый интервал, censored=False;
      - от последней покупки категории пользователем до `as_of` ->
        censored=True (пользователь мог купить категорию и после `as_of`,
        мы этого просто ещё не знаем — отбрасывать это наблюдение, а не
        цензурировать, сместило бы кривую в сторону завышенного риска).
    Пользователи с одной-единственной покупкой категории дают только
    цензурированное наблюдение — и это корректно, не мусор.
    Возвращает {category: fit_km_curve(...)} по каждой категории, где
    накопилось хотя бы одно наблюдение."""
```

DB-free, как и весь остальной `synth` (принимает только плоские
`dict`/`date`, без ORM) — сохраняет существующий контракт "generate — чистая
функция" (см. докстринг `web/src/webx5/services/challenge_adapter.py:1`).

## 2. Компонент популяционных кривых (web-слой)

Кривые нужны по **всем** пользователям — их не построить из профиля одного
человека и незачем считать заново на каждый запрос. Строим один раз при
старте процесса (подтверждено пользователем — для hackathon перезапуск при
обновлении данных приемлем, TTL/периодический refresh — сознательно не
делаем, YAGNI).

- Новый метод в `web/src/webx5/crud/` (Repository-слой, например
  `SurvivalRepository.fetch_purchase_dates(session) -> dict[str, dict[str, list[date]]]`)
  — один агрегирующий запрос по `Receipt`/`ReceiptItem`/`Product`/`Category`
  по всем пользователям, без окна по времени, группировка
  `loyalty_card_id -> category.name -> [purchase_date...]`.
- Новый класс `web/src/webx5/core/survival.py::SurvivalCurveStore`,
  собираемый в `core/` при wiring сервисов (как сегодня строится
  `SynthConfig`) — вызывает `SurvivalRepository.fetch_purchase_dates` +
  `synth.survival.fit_population_curves` один раз, хранит результат
  (`dict[str, SurvivalCurve]`) в памяти на весь процесс.
- `ChallengeService` получает `SurvivalCurveStore` через DI (конструктор,
  как уже получает `synth_config`/`model`/`api_key`,
  `web/src/webx5/services/challenge.py:90`) и прокидывает
  `store.curves` в `generate_challenge_for_user` новым параметром
  `category_curves: dict[str, SurvivalCurve]`.

Офлайн-потребители `synth` (`synth/cli.py`, референс-профили для hit-rate
скоринга) сами по себе уже держат весь синтетический датасет в памяти —
там `fit_population_curves` вызывается прямо на нём, без БД, тем же самым
кодом.

## 3. Признаки в `ChallengeAdapter.build_profile`

Сейчас профиль читает только последние 90 дней (`challenge_adapter.py:122`)
и считает `habitual_categories` (топ-5 по количеству строк). Меняем:

- Убираем 90-дневный `cutoff` — читаем всю историю пользователя (подтверждено
  пользователем: recency важна только per-категория, лишние старые данные не
  вредят, а укороченное окно занижает риск для категорий с длинным циклом
  повторной покупки).
- Добавляем в профиль `"category_last_purchase": dict[str, str]` — дата
  (ISO) последней покупки на каждую категорию, где была хотя бы одна
  покупка (вычисляется в том же цикле, где сейчас собирается
  `habit_counter`, `challenge_adapter.py:138-150`).
- Никакого кэширования `category_last_purchase` между вызовами: `build_profile`
  пересобирает его заново из БД при каждом обращении, поэтому личный риск
  пользователя (в отличие от популяционной кривой из раздела 2) всегда
  свежий на момент вызова `generate_batch`. Явное следствие: как только у
  пользователя появляется новая покупка категории (например, засчитан
  предыдущий челлендж), `days_since_last_purchase` для неё обнуляется, риск
  падает почти до 0 (`S(0) = 1`) — категория сама уходит из топ-3 при
  следующей генерации, без отдельного механизма "не повторять товар".
- `habitual_categories` (топ-5) оставляем как есть — используется другими
  путями (`vibe`, `build_basket_spend_challenge`), не трогаем.

## 4. Новый билдер `synth/challenges.py::build_survival_risk_challenge`

```python
def build_survival_risk_challenge(
    profile: dict,
    config: SynthConfig,
    category_curves: dict[str, SurvivalCurve],
    rank: int,
    slot: str,
    as_of: date | None = None,
) -> dict | None:
    """Ранжирует все категории из profile["category_last_purchase"] по
    риску оттока (1 - S(days_since_last_purchase)) по убыванию и возвращает
    челлендж на категорию с индексом `rank` (0 = самый рискованный).
    Категории без данных в `category_curves` (популяция никогда её не
    покупала — на практике не должно происходить, но не гарантировано)
    пропускаются. Возвращает None, если у пользователя нет истории покупок
    вообще ИЛИ рангов меньше, чем `rank + 1` — тогда вызывающий код
    откатывается на старый generic-пул, как и сегодня для новых
    пользователей."""
```

`as_of` по умолчанию (`None`) резолвится в `date.today()` — задаётся явно
только офлайн-вызовами (`synth/cli.py`, референс-профили), где нужна
воспроизводимость относительно `config.temporal_split`, как это уже принято
для остальных детерминированных билдеров.

Реализация — по образцу `build_category_expansion_challenge`
(`synth/challenges.py:438`): та же схема `reward_rub` (`discount_pct`% от
`config.category_economics[category].base_price_rub`, клампится
`estimate_max_reward_rub(profile)`), тот же `pick_sku_in_category` +
`item_action_description` для текста и `target_sku_id`, тот же набор ключей
результата (`challenge_title`, `description`, `target_categories`,
`mechanic`, `reward_rub`, `reasoning`, `target_sku_id`, `target_quantity`),
плюс новое поле `deadline_days` (см. ниже).

Текст — по шаблону на слот (не LLM), с урезанным до 2-3 вариантов набором
формулировок на слот для разнообразия (ротация по хешу `user_id`, как
`_pick_distinct_generic_offer`), а не единственная жёсткая строка:

- `llm_habit` → "Категория «{category}» — часто ваша, но вы давно её не
  брали ({days} дн.). Повторите покупку — {reward} ₽ кэшбэком."
- `llm_discovery` → похожий тон, но акцент на "самая рискованная из
  непривычных" (ранг обычно ниже, вторая по риску).
- `generic` → нейтральная формулировка, ближе к текущему
  `build_category_expansion_challenge` по духу.

`deadline_days = min(30, curve.median_survival_days() or 14)` — дедлайн
подгоняется под медианное время до повторной покупки этой категории по
популяции: челлендж истекает примерно тогда, когда пользователь и так
статистически близок к оттоку — осмысленная срочность, а не константа "7
дней всем".

## 5. Изменения в `generate_challenge_for_user`

Внутри `synth/challenges.py:958`:

- Новый параметр `category_curves: dict[str, SurvivalCurve] | None = None`.
- Слот `llm_habit` (`:1079-1081`): вместо `build_personal_prompt(focus="habit")`
  + `_run_llm_slot` — `build_survival_risk_challenge(profile, config,
  category_curves, rank=0, slot="llm_habit")`, при `None` — откат на
  `_generic("llm_habit", "generic_fallback")` (тот же путь, что сегодня для
  LLM-ошибок).
- Слот `llm_discovery` (`:1083-1085`) — то же самое, `rank=1`.
- Слот `generic` (`:1063-1070`, сейчас — первым делом
  `_pick_distinct_generic_offer`): пробуем
  `build_survival_risk_challenge(..., rank=2, slot="generic")` первым, при
  `None` — старый путь (`_pick_distinct_generic_offer` из
  `GENERIC_CHALLENGES`). Ранги 0/1/2 гарантированно указывают на разные
  категории (один и тот же отсортированный список), явная кросс-слотовая
  дедупликация внутри функции не нужна.
- `category_curves=None` (офлайн dry-run без построенных кривых, `dry_run=True`
  путь) — все три слота молча уходят в существующий generic-fallback,
  никаких новых веток отказа.

На web-границе (`web/src/webx5/services/challenge.py`):
`_use_deterministic_mechanics` (`:43`) и его подмена `generic` →
`category_expansion` **удаляются** — она больше не нужна, слот `generic`
теперь уже приходит из `generate_challenge_for_user` в нужном виде.
`_SLOTS_WITHOUT_NATURAL_VARIATION` (`:38`) теряет `"category_expansion"`
(слот больше не производится живым путём) — риск-скор сам по себе меняется
день ото дня по мере роста `days_since_last_purchase`, так что
`llm_habit`/`llm_discovery`/`generic` не нужно туда добавлять: у них
появляется естественный источник вариации, которого не было у LLM-версии
(там ротацию обеспечивала сама LLM своей недетерминированностью, а не
скор).

## 6. Плюмбинг дедлайна

Сегодня `TaskRepository.create` (`web/src/webx5/crud/task.py:143-151`)
всегда ставит `deadline = now + 7 дней`, если явно не передано — ни один
вызывающий код (`ChallengeAdapter.persist_challenge`,
`challenge_adapter.py:293`) сегодня deadline не передаёт. Добавляем:
`persist_challenge` читает `script_result.get("deadline_days")` и, если
есть, передаёт `deadline=datetime.now(UTC) + timedelta(days=deadline_days)`
в `task_repo.create`; если поля нет (все остальные слоты) — поведение не
меняется, дефолт 7 дней как сейчас.

## 7. Fallback / cold start

Пользователь без единой покупки (`category_last_purchase` пуст) — все три
слота уходят на существующий путь генерации (`_generic`/старый
`GENERIC_CHALLENGES` пул), как и сегодня для тонкой истории. Отдельного
порога на минимальное число покупок в категории не нужно: KM строится на
популяции (много пользователей), а скоринг конкретного пользователя требует
только дату последней покупки — работает даже при одной покупке категории.

## Тесты

- `tests/synth/test_survival.py` (новый) — `fit_km_curve` на маленьком
  вручную посчитанном датасете (сверка с эталонным значением KM,
  посчитанным вручную/по учебному примеру), включая обработку censoring;
  `SurvivalCurve.survival_at`/`median_survival_days` на граничных случаях
  (до первого события, после последнего, кривая не опускается до 0.5);
  `fit_population_curves` — интервалы и censoring строятся верно на
  синтетическом небольшом наборе `purchase_dates_by_user`.
- `tests/synth/test_challenges.py` — `build_survival_risk_challenge`:
  корректный ранг → категория, `None` при пустой истории/недостаточном
  ранге, `deadline_days` считается из медианы кривой;
  `generate_challenge_for_user` — новые слоты `llm_habit`/`llm_discovery`/
  `generic` больше не делают вызов `call_openrouter` (мокнуть и проверить,
  что не вызывался), откат на generic-fallback без `category_curves`.
- `tests/webx5/services/test_challenge*.py` — `_use_deterministic_mechanics`
  и связанный тест удаляются вместе с функцией;
  `_SLOTS_WITHOUT_NATURAL_VARIATION` обновляется под новый набор;
  новый тест на плюмбинг `deadline_days` в `persist_challenge`.
- `tests/webx5/crud/test_survival_repository.py` (новый, если заводим
  `SurvivalRepository` отдельным файлом) — агрегирующий запрос отдаёт
  ожидаемую форму `dict[str, dict[str, list[date]]]` на фикстурных чеках.

## Риск: hit-rate метрика хакатона

Как и в `2026-09-05-challenge-mix-vibe-design.md`: `CONTEXT_PACK.md` §H2
фиксирует hit-rate, посчитанный `synth/cli.py` поверх **текущей** версии
`generate_challenge_for_user`. Эта переработка меняет логику трёх из пяти
слотов — старая цифра перестаёт быть валидной. После реализации нужно
перезапустить скоринг и обновить `CONTEXT_PACK.md` — отдельная задача, не
часть implementation plan по коду.

Ожидаемый эффект — по построению этот дизайн целится ровно в скрытую
`repurchase_intervals` (`synth/simulation_truth.py`), которую и меряет
hit-rate, так что имеет смысл ожидать улучшения, а не только архитектурной
чистоты — но это гипотеза, не гарантия, проверяется тем же скорингом.

Экономическая симуляция (`synth/simulation.py`) не затрагивается — она
использует `compute_receptiveness`/`build_spend_threshold_challenge`/
`build_category_expansion_challenge` напрямую через `route_for_simulation`,
независимо от `generate_challenge_for_user`.

## Вне скоупа

- Сегментация кривых (по `loyalty_level`, каналу и т.д.) — считаем одну
  глобальную кривую на категорию. Естественное расширение на будущее,
  зафиксировать в `BACKLOG.md` при реализации.
- TTL/периодический refresh кривых — считаем один раз на старте процесса;
  протухание данных между рестартами — приемлемый компромисс PoC.
- Использование survival-риска для `llm_basket`/`vibe` — не входит в этот
  дизайн, у них другая роль.
- UI/показ пользователю самого risk-score или "почему именно эта
  категория" — текст челленджа человекочитаемый, но сырое число риска
  наружу не выводим.
