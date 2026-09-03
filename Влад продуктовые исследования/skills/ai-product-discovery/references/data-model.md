# Структура результатов

Это семантический контракт для `discovery.json`, а не требование заполнять неизвестное выдумками. Используй корректный JSON, массивы вместо строк с разделителями и `null` для неизвестных чисел. Текст — на языке пользователя.

## Верхний уровень

`schema_version` = `1.0`; `brief` (направление/продукт, рынок, дата исследования, границы, язык); `sources`; `products`; `segments`; `hypotheses`; `ranking`; `selected_hypothesis_ids`; `lean_canvases`; `open_questions`; `next_experiment`.

`sources[]`: `id`, `title`, `url` или имя предоставленного файла, `accessed_at`, `source_type`, описание того, что источник подтверждает. Интервью также имеют ID и явно обозначенный тип.

Для отдельного утверждения/оценки: `value`, `evidence_status` (`observed`, `inferred`, `synthetic`, `unknown`), `source_ids`, `assumption`. Допущения должны оставаться видимыми в человекочитаемом отчёте.

`products[]`: `id`, `name`, `url`, `description`, `commercial_offer_evidence`, `source_ids`. URL не восстанавливать из названия наугад.

## Сегмент

`segments[]`: `id`, `product_id`, `name`, `benefit_description`, `icp`, `interview`, `pain_map`, `jtbd`, `value_proposition`.

ICP: `customer_type`, `industry`, `demographics`, `firmographics`, `geography`, `psychographics`, `behavior`, `needs_goals`, `purchase_triggers`, `decision_process`, `budget`, `channels`, `objections`. Для неактуальной демографии допустимо «не применимо».

Интервью: `id`, `kind` (`real`, `synthetic`, `question_guide`), `source_id`, `qa[]` с `id`, `question`, `answer`. В гайде `answer` = null. Реальные цитаты воспроизводить точно и кратко с указанием места в источнике.

## Карта болей

Для каждой боли: `id`, `pain`, `evidence_status`, `source_ids`, `evidence_quotes[]`, `severity`, `frequency`, `reach`, `confidence`, `priority_score`, `root_cause`, `current_workarounds`, `desired_outcome`, `related_jtbd_ids`, `opportunity_notes`.

Цитата: `text`, `interview_id`, `qa_ref`, `kind` (`real` или `synthetic`). Не создавай цитату, когда нет соответствующего текста.

Четыре оценки — целые от 1 до 5, вместе с обоснованием/статусом. Формула исходника:

`priority_score = round((severity*0.4 + frequency*0.3 + reach*0.2 + confidence*0.1)*10)`.

Её диапазон **10–50**, не 0–100. При неизвестной оценке итог = null. Не смешивать эту шкалу с `JTBD.priority_score` или RICE.

## JTBD

Для каждой работы: `id`, `pain_ids`, `job_statement`, `situation`, `struggle`, `desired_outcomes` (обычно 4–7), `forces` (`pushes`, `pulls`, `anxieties`, `habits`, обычно 2–5 на группу), `acceptance_criteria` (обычно 3–6), `moment_of_progress`, `related_quotes`, `priority_score` (0–100 либо null), `priority_rationale`, `evidence_status`, `source_ids`.

Оценка JTBD — объяснённое суждение на основе тяжести, частоты и охвата болей, а не механическая подстановка их оценки 10–50. Количества ориентировочные: не создавай лишние пункты или цитаты ради количества.

## Value Proposition Canvas

`customer_profile`: `customer_jobs` (`functional`, `social`, `emotional`), `pains`, `gains`.

`value_map`: `products_services`, `pain_relievers`, `gain_creators`.

`fit_links[]`: ссылки между `pain_id`/`jtbd_id`, соответствующим элементом value map и проверяемым механизмом пользы; статус `existing` или `proposed` для предложения продукта.

## Гипотезы и Lean Canvas

Гипотеза: `id`, `product_id`, `segment_id`, `jtbd_ids`, `pain_ids`, `hypothesis`, `rationale`, `metric`, `expected_outcome`, `experiment`, `success_criterion`, `evidence_status`, `source_ids`. Эксперимент содержит аудиторию, действие, период и правило принятия решения. Не объявляй A/B-тест осуществимым без понимания трафика; для раннего продукта уместен MVP или интервью с реальными людьми.

RICE: поля и формат входа скрипта описаны в `rice.md`. Каждый `ranking` хранит `scope`, `reach_period`, `effort_unit` и `items`. Область сравнения важна: лидер одной JTBD не автоматически лидер всего проекта.

`lean_canvases[]`: `hypothesis_id`, `problem`, `existing_alternatives`, `solution`, `unique_value_proposition`, `high_level_concept`, `unfair_advantage`, `customer_segments`, `early_adopters`, `key_metrics`, `channels`, `cost_structure`, `revenue_streams`. Сохраняй происхождение и допущения в каждом поле.
