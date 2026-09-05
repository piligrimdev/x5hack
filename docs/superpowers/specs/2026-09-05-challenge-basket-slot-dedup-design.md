# Персональные челленджи: слот `llm_basket` + дедуп между поколениями

Date: 2026-09-05. Brainstormed interactively (`superpowers:brainstorming`).

## Проблема и мотивация

Текущий микс (`synth/challenges.py::CHALLENGE_SLOTS`) — 4 слота: `llm_habit`,
`llm_discovery`, `generic`, `vibe`. Запрос: добавить пятый слот, оборачивающий
уже существующую фичу "предложенная корзина на неделю"
(`BasketRepository.suggest_items` — детерминированный частотный анализ чеков,
используется в `GET /basket/suggested` из параллельной ветки), и обеспечить,
чтобы задания не повторялись **между последовательными генерациями** одного
пользователя (не только внутри одного батча — тот дедуп уже есть, см.
`ChallengeService.generate_batch`'s `existing_criteria`/`resolve_criterion`).

## Новый слот: `llm_basket`

Пятый элемент `CHALLENGE_SLOTS`: `("llm_habit", "llm_discovery", "llm_basket",
"generic", "vibe")`. Инвариант "макс. активных заданий" сам поднимется до 5 —
`ChallengeService.generate_batch` уже вычисляет `remaining_slots =
len(CHALLENGE_SLOTS) - len(active_tasks)` (не хардкод), правка не нужна.

**Генерация:** новая функция `build_basket_prompt(profile, config,
max_reward_rub, suggested_items) -> tuple[str, str]` в `synth/challenges.py`,
по структуре как `build_vibe_prompt`: LLM получает список `suggested_items`
(что пользователь обычно покупает каждую неделю) и оборачивает его в челлендж
вида "собери свою обычную недельную корзину — получи бонус". `target_categories`
ограничены категориями из `suggested_items` через уже существующий механизм
`parse_and_validate_challenge(..., allowed_categories=...)`.

**Источник данных:** `suggested_items: list[dict]` — не сырые ORM-объекты
`BasketRepository.suggest_items` возвращает `list[tuple[Product, int]]`,
поэтому `ChallengeAdapter.build_profile` конвертирует в
`[{"item": product.name, "category": product.category.name, "weekly_quantity": qty}, ...]`
перед тем как положить в `profile["suggested_basket_items"]`.

**Cold start:** если `suggest_items` вернул пустой список (нет чеков) — слот
`llm_basket` НЕ вызывает LLM вообще, сразу уходит в `generic_fallback` (как
детерминированные билдеры делали при отсутствии данных) — нет смысла звать
LLM с пустым контекстом, и это не противоречит принципу "без гейтинга по
receptiveness", потому что это структурное отсутствие входных данных, а не
эвристическая оценка "силы паттерна".

**DI:** `ChallengeAdapter.__init__` получает `basket_repo: BasketRepository`
вторым параметром. В `core/challenges.py` переиспользуется уже созданный
`basket_repo` из `core/basket.py` (импорт `from webx5.core.basket import
basket_repo`) — без цикличного импорта (`core/basket.py` ничего не импортирует
из `core/challenges.py` или `services/challenge*.py`).

## Дедуп между последовательными генерациями

Сейчас `ChallengeService.generate_batch` дедуплицирует только **внутри одного
батча** — сравнивает резолвленный `(criterion_type, criterion_entity_id)`
нового кандидата с уже персистнутыми в ЭТОМ ЖЕ вызове и с активными задачами
пользователя (`existing_criteria`). Новое требование — не повторять то же
самое **по конкретному слоту** между поколениями (следующий цикл генерации не
должен выдать тот же `target_sku_id`/категорию, что и в прошлый раз, для ТОГО
ЖЕ слота).

**Источник истории:** без новой таблицы — колонки `challenge_slot`,
`criterion_type`, `criterion_entity_id`, `issued_at` уже есть на `Task`.
Новый метод `TaskRepository.get_last_criterion_per_slot(session, user_id) ->
dict[str, tuple[str, uuid.UUID]]` — для каждого `challenge_slot` пользователя
берёт `criterion_type`/`criterion_entity_id` самой свежей по `issued_at`
записи (`DISTINCT ON` или оконная функция `ROW_NUMBER() OVER (PARTITION BY
challenge_slot ORDER BY issued_at DESC)`, независимо от `task_status`
— то есть завершённые и истёкшие тоже считаются "было").

**Применение:** `ChallengeService.generate_batch` вызывает этот метод один
раз в начале (рядом с построением `existing_criteria`), получает
`previous_by_slot`. После резолва кандидата через
`self.adapter.resolve_criterion(...)`, ПЕРЕД проверкой на `existing_criteria`
(cross-slot), добавляется вторая проверка: если резолвленный критерий совпадает
с `previous_by_slot.get(slot)` — тот же слот повторил свою же прошлую цель —
слот тоже пропускается (не персистится), с отдельным логом
(`generate_batch.repeats_previous_cycle_skip`). Пропущенный слот **не**
пытается перегенерироваться в этом же вызове — это тот же "просто пропусти,
не пытайся героически чинить" паттерн, что уже используется для cross-slot
коллизий и сбоев `persist_challenge`. Такой пользователь в этом цикле
недополучит один слот (как и при любом другом сбое билдера) — при следующем
триггере генерации (новый чек / завершение задания) `generate_batch` снова
попробует заполнить недостающий слот.

**Слот `generic`:** отдельный путь не нужен — `_pick_distinct_generic_offer`
уже устроен так, что принимает `used_indices: list[int]` и продвигает индекс,
если он уже занят. Досеиваем этот список индексом прошлого цикла для
`generic`-слота этого пользователя (если известен), передавая его как
предзаполненный `used_generic_indices` в `generate_challenge_for_user` —
новый необязательный параметр `previous_generic_index: int | None = None`.

**LLM-слоты (`llm_habit`/`llm_discovery`/`llm_basket`/`vibe`):** дедуп только
детектирует повтор постфактум (сравнение резолвленного критерия), не пытается
заранее подсказать LLM "не предлагай X снова" и не делает повторных попыток
внутри цикла с другим seed — это осознанное упрощение (YAGNI): раз в месяц
пропущенный слот и его перегенерация при следующем триггере — приемлемая цена
за простоту, ретрай-логика с вариацией seed — избыточна для этой итерации.

## Изменения по файлам

- `synth/challenges.py`: `CHALLENGE_SLOTS` → 5 элементов; `build_basket_prompt`
  (новая функция, после `build_vibe_prompt`); `generate_challenge_for_user`
  получает новые параметры `previous_generic_index: int | None = None`,
  читает `profile.get("suggested_basket_items")`; новый слот `llm_basket`
  между `llm_discovery` и `vibe`.
- `web/src/webx5/crud/task.py`: новый метод `get_last_criterion_per_slot`.
- `web/src/webx5/services/challenge_adapter.py`: конструктор принимает
  `basket_repo`; `build_profile` кладёт `suggested_basket_items` в профиль.
- `web/src/webx5/services/challenge.py`: `generate_batch` вызывает
  `get_last_criterion_per_slot`, добавляет проверку "повтор прошлого цикла"
  рядом с существующей cross-slot проверкой; прокидывает индекс прошлого
  `generic`-оффера в `generate_challenge_for_user`.
- `web/src/webx5/core/challenges.py`: DI — `ChallengeAdapter(task_repo,
  basket_repo)`, импорт `basket_repo` из `core/basket.py`.
- `web/tests/webx5/services/test_challenge_service.py`,
  `test_challenge_adapter.py`, `tests/synth/test_challenges.py` — новые/
  обновлённые тесты на 5-слотовый микс, `llm_basket`, дедуп между циклами.

## Вне скоупа (YAGNI)

- Ретрай LLM с явной инструкцией "не предлагай X снова" при обнаруженном
  повторе — просто fallback/пропуск слота.
- Подбор другого SKU внутри той же категории при повторе — не пытаемся,
  слот просто пропускается в этом цикле.
- Изменение мобильного UI под 5 карточек — на верификацию (как и при переходе
  3→4), не блокирует бэкенд-реализацию.
- Обновление `synth/simulation.py`/офлайн hit-rate инструментов под 5-слотовый
  микс — те же ограничения и риски, что уже задокументированы в
  `CONTEXT_PACK.md`/`BACKLOG.md` для 4-слотового перехода, актуальны и здесь;
  отдельно не дублируются.
