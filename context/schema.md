# Database Schema — X5 Loyalty MVP

## Tables

---

### brand (Бренд)
| Field | Description |
|---|---|
| id | PK |
| name | Название бренда |

---

### category (Категория)
| Field | Description |
|---|---|
| id | PK |
| name | Название категории |

---

### product (Товар)
| Field | Description |
|---|---|
| id | PK |
| name | Название товара |
| current_price | Текущая цена (актуальная, справочная) |
| category_id | FK → category |
| brand_id | FK → brand |

---

### discount_type (Тип скидки)
| Field | Description |
|---|---|
| id | PK |
| name | акция / лояльность / персональная / уценка |

---

### discount_link_type (Тип связи скидки)
| Field | Description |
|---|---|
| id | PK |
| name | product / category / brand |

---

### discount (Скидка)
| Field | Description |
|---|---|
| id | PK |
| value | Значение скидки в процентах |
| discount_type_id | FK → discount_type |
| link_type_id | FK → discount_link_type (полиморфная связь) |
| entity_id | ID связанной сущности (product / category / brand) |
| scope | Область действия: all / by_format / by_store |
| valid_from | Дата начала действия (NULL = с момента создания) |
| valid_to | Дата окончания действия (NULL = бессрочно) |

> Все даты хранятся в московском часовом поясе (UTC+3).
> Бизнес-логика выбирает одну скидку по принципу best-price-wins.

---

### store_format (Формат сети)
| Field | Description |
|---|---|
| id | PK |
| name | Пятёрочка / Перекрёсток / Чижик |

---

### store (Магазин)
| Field | Description |
|---|---|
| id | PK |
| format_id | FK → store_format |
| geo_cluster | Геокластер / район (для анонимного рейтинга) |
| address | Адрес (только для администрирования, не для показа пользователям) |

---

### format_discount (M2M: скидка ↔ формат сети)
| Field | Description |
|---|---|
| discount_id | FK → discount |
| format_id | FK → store_format |

> Используется когда discount.scope = 'by_format'

---

### store_discount (M2M: скидка ↔ магазин)
| Field | Description |
|---|---|
| discount_id | FK → discount |
| store_id | FK → store |

> Используется когда discount.scope = 'by_store'

---

### segment (Сегмент)
| Field | Description |
|---|---|
| id | PK |
| name | подросток / семьянин / пожилой |

---

### loyalty_card (Карта лояльности / Пользователь)
| Field | Description |
|---|---|
| id | PK |
| loyalty_level | Уровень лояльности (номер или название) |
| name | Имя пользователя |
| phone | Номер телефона |
| gender | Пол |
| age | Возраст |
| segment_id | FK → segment |

---

### receipt (Чек)
| Field | Description |
|---|---|
| id | PK |
| purchase_date | Дата и время покупки |
| payment_card_uid | UID / хеш банковской карты оплаты (антифрод-сигнал) |
| loyalty_card_id | FK → loyalty_card |
| store_id | FK → store |
| channel | Канал: online / offline |

---

### receipt_item (Позиция чека)
| Field | Description |
|---|---|
| id | PK |
| receipt_id | FK → receipt |
| product_id | FK → product |
| quantity | Количество единиц товара |
| base_price_at_purchase | Полочная цена на момент покупки |
| paid_price | Фактически уплаченная цена за единицу |
| discounted_amount | Сумма скидки в рублях за единицу (base - paid) |
| discount_id | FK → discount (NULL если скидка не применялась) |

---

### task_status (Статус задания)
| Field | Description |
|---|---|
| id | PK |
| name | открыто / выполнено / провалено / истекло |

---

### task (Индивидуальное задание)
| Field | Description |
|---|---|
| id | PK |
| loyalty_card_id | FK → loyalty_card |
| task_status_id | FK → task_status |
| issued_at | Дата выдачи задания |
| deadline | Дедлайн выполнения |
| reward | Описание награды за выполнение |
| criterion_type | Тип критерия: product / category / brand |
| criterion_entity_id | ID целевой сущности (product / category / brand) |
| quantity_target | Целевое количество товаров |
| quantity_current | Текущий прогресс (обновляется при обработке чека) |

> Одно задание — один критерий. Бизнес-логика проверяет прогресс при каждом новом чеке пользователя.

---

## Relations

```
brand          ←─── product ───→ category
                        ↑
                  receipt_item ──→ discount
                        |              |
                      receipt    discount_type
                        |         discount_link_type
                   loyalty_card   format_discount ──→ store_format
                        |         store_discount  ──→ store ──→ store_format
                      segment
                        |
                   loyalty_card ──→ task ──→ task_status
```

## Key Constraints

- `receipt_item.discounted_amount = base_price_at_purchase - paid_price` (инвариант, проверяется бизнес-логикой)
- Выбор скидки: best-price-wins — бизнес-логика перебирает все скидки, применимые к товару (по product / category / brand), выбирает минимальную `paid_price`
- `discount.valid_to = NULL` означает бессрочную скидку
- `discount.scope = 'all'` → format_discount и store_discount пусты
- `discount.scope = 'by_format'` → строки в format_discount
- `discount.scope = 'by_store'` → строки в store_discount
- `task.quantity_current` обновляется при каждом новом чеке, если позиция соответствует criterion_type + criterion_entity_id
