# Specification Quality Checklist: Кешбек в баллах вместо скидочной награды за задания

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-04
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Спека сознательно упоминает названия эндпоинтов и полей БД (`points_account`, `receipt.cashback_applied_rub`) — это диктует продуктовое требование «названия полей не переименовывать» из спеки 006 (FR-019) и потребность зафиксировать точки интеграции с уже существующими /receipts, /receipts/calculate. Технические детали (SQLAlchemy, миграции, celery, engine, event loop) не упоминаются.
- FR-001 явно заменяет FR-010/FR-011/FR-011a спеки 006 в части формы награды — это критичный контракт для избежания двойной семантики.
- Курс `rate_points_per_rub` зафиксирован как целое, чтобы избежать float в деньгах. Дробные курсы — BACKLOG.
- Все критичные решения приняты через reasonable defaults (курс на момент закрытия задания, курс на момент фиксации чека, capping-поведение, атомарность, идемпотентность). Ни одного [NEEDS CLARIFICATION].
- Возврат чека, сгорание баллов, доля чека к оплате баллами, cleanup orphan-счетов — явно вынесены в BACKLOG.
