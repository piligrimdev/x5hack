# Курс баллов, реальные челленджи, отображение списания, персистентная корзина — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Начисление баллов согласовано со списанием (курс ×10, округление до 10), секция «Задания» в корзине показывает реальные челленджи пользователя, «Итого» реагирует на списание баллов, а корзина на неделю сохраняется на устройстве и не пересобирается при каждом заходе на экран.

**Architecture:** Четыре независимые доработки поверх уже работающей корзины. (1) Бэкенд: `PointsService.award_for_task` использует уже существующий `PointsRepository.get_rate()` вместо хардкода 1:1. (2) Фронт: `savings-view.tsx` заменяет моковый `tasks`-пропс на уже существующий хук `useChallenges`. (3) Фронт: перестановка одной формулы в уже существующем totals-блоке. (4) Фронт: `useBasket` получает персистентность через `@react-native-async-storage/async-storage` (новая зависимость) вместо автозагрузки на каждом монтировании.

**Tech Stack:** FastAPI + SQLAlchemy (sync), Pydantic v2 (бэкенд `web/src/webx5`); Expo/React Native/TypeScript (фронт `x5mobile/`).

**Spec:** [docs/superpowers/specs/2026-09-05-basket-points-challenges-persistence-design.md](../specs/2026-09-05-basket-points-challenges-persistence-design.md)

## Global Constraints

- Курс: `PointsSettings.rate_points_per_rub = 10` (уже в БД, не менять). Начисление = `round(reward_rub * rate / 10) * 10`.
- Списание баллов, курс, авторизация и весь остальной чекаут-флоу — уже реализованы и не трогаются этим планом.
- Персистентность корзины — один ключ AsyncStorage на устройство, НЕ по пользователю (осознанное упрощение, см. BACKLOG.md).
- Кнопки на главном экране и в таб-баре, ведущие на экран «Экономия», не меняются — сбор корзины происходит только явным нажатием кнопки внутри самого экрана.
- Тесты бэкенда: `poetry -C web run pytest` (если `poetry` не в PATH — `python3 -m poetry -C web run pytest`; для тестов с `synth` нужен `PYTHONPATH=<repo-root>`).
- У фронта (`x5mobile/`) нет тестового фреймворка — верификация фронтенд-задач ручная (`npx tsc --noEmit` + curl/запуск в браузере).
- Новую npm-зависимость ставить через `npx expo install <pkg>`, не `npm install`/`yarn add` напрямую (резолвит версию под установленный Expo SDK).

---

### Task 1: Курс начисления баллов

**Files:**
- Modify: `web/src/webx5/services/points.py`
- Test: `web/tests/webx5/services/test_points_award.py`

**Interfaces:**
- Consumes: `PointsRepository.get_rate(session) -> int` (уже существует, `web/src/webx5/crud/points.py:124-129`).
- Produces: `PointsService.award_for_task(session, task) -> int` — сигнатура не меняется, меняется только формула внутри. Используется существующим вызывающим кодом (`services/task_completion.py`) без изменений с их стороны.

- [ ] **Step 1: Update the failing tests**

Замени содержимое `web/tests/webx5/services/test_points_award.py` целиком:

```python
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock

from webx5.entities.points import PointsAccount, PointsTransaction
from webx5.entities.task import Task
from webx5.services.points import PointsService


def _make_task(reward_rub: str = "50") -> Task:
    t = Task()
    t.id = uuid.uuid4()
    t.loyalty_card_id = uuid.uuid4()
    t.reward_rub = Decimal(reward_rub)
    return t


def _account(loyalty_card_id: uuid.UUID, balance: int = 0) -> PointsAccount:
    a = PointsAccount()
    a.id = uuid.uuid4()
    a.loyalty_card_id = loyalty_card_id
    a.balance = balance
    return a


def test_award_for_task_happy_path() -> None:
    task = _make_task("50")
    account = _account(task.loyalty_card_id)
    repo = MagicMock()
    repo.get_rate.return_value = 10
    repo.get_or_create_account.return_value = account
    tx = PointsTransaction()
    tx.id = uuid.uuid4()
    tx.rate_at_time = None
    repo.insert_earn.return_value = tx
    service = PointsService(repo=repo)
    session = MagicMock()

    awarded = service.award_for_task(session, task)

    # reward_rub=50, rate=10 -> 50*10=500, already a multiple of 10
    assert awarded == 500
    repo.get_rate.assert_called_once_with(session)
    repo.get_or_create_account.assert_called_once_with(session, task.loyalty_card_id)
    repo.insert_earn.assert_called_once_with(session, account.id, task.id, 500)
    repo.bump_balance.assert_called_once_with(session, account, 500)
    # rate_at_time is not applied on earn (feature 007 clarification)
    assert repo.insert_earn.call_args.args[3] == 500


def test_award_for_task_reward_zero_is_noop() -> None:
    task = _make_task("0")
    repo = MagicMock()
    repo.get_rate.return_value = 10
    service = PointsService(repo=repo)

    awarded = service.award_for_task(MagicMock(), task)

    assert awarded == 0
    repo.get_or_create_account.assert_not_called()
    repo.insert_earn.assert_not_called()
    repo.bump_balance.assert_not_called()


def test_award_for_task_idempotent_when_earn_conflicts() -> None:
    task = _make_task("50")
    account = _account(task.loyalty_card_id, balance=100)
    repo = MagicMock()
    repo.get_rate.return_value = 10
    repo.get_or_create_account.return_value = account
    repo.insert_earn.return_value = None  # simulate IntegrityError → duplicate
    service = PointsService(repo=repo)

    awarded = service.award_for_task(MagicMock(), task)

    assert awarded == 0
    repo.bump_balance.assert_not_called()
    assert account.balance == 100  # unchanged


def test_award_for_task_reward_rub_scaled_and_rounded_to_nearest_10() -> None:
    # Decimal("50.99") * rate(10) = 509.9 -> round to nearest 10 -> 510
    task = _make_task("50.99")
    account = _account(task.loyalty_card_id)
    repo = MagicMock()
    repo.get_rate.return_value = 10
    repo.get_or_create_account.return_value = account
    repo.insert_earn.return_value = PointsTransaction()
    service = PointsService(repo=repo)
    session = MagicMock()

    awarded = service.award_for_task(session, task)

    assert awarded == 510
    repo.insert_earn.assert_called_once_with(session, account.id, task.id, 510)


def test_award_for_task_uses_configured_rate() -> None:
    # reward_rub=20 at rate=5 -> 20*5=100, already a multiple of 10
    task = _make_task("20")
    account = _account(task.loyalty_card_id)
    repo = MagicMock()
    repo.get_rate.return_value = 5
    repo.get_or_create_account.return_value = account
    repo.insert_earn.return_value = PointsTransaction()
    service = PointsService(repo=repo)
    session = MagicMock()

    awarded = service.award_for_task(session, task)

    assert awarded == 100
    repo.insert_earn.assert_called_once_with(session, account.id, task.id, 100)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `poetry -C web run pytest tests/webx5/services/test_points_award.py -v`
Expected: FAIL — old tests expect `awarded == 50` etc., current code still returns `int(task.reward_rub)` unscaled; `repo.get_rate.assert_called_once_with` fails because `get_rate` is never called by the current implementation.

- [ ] **Step 3: Implement the rate-scaled formula**

В `web/src/webx5/services/points.py` замени:

```python
    def award_for_task(self, session: Session, task: Task) -> int:
        points = int(task.reward_rub)
        if points <= 0:
```

на:

```python
    def award_for_task(self, session: Session, task: Task) -> int:
        rate = self._repo.get_rate(session)
        raw = float(task.reward_rub) * rate
        points = int(round(raw / 10) * 10)
        if points <= 0:
```

(Остальное тело метода — блок `get_or_create_account`/`insert_earn`/`bump_balance`/логирование — не меняется.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `poetry -C web run pytest tests/webx5/services/test_points_award.py -v`
Expected: PASS, все 5 тестов (4 обновлённых + 1 новый про конфигурируемый курс) зелёные.

Затем прогони полный набор тестов бэкенда: `poetry -C web run pytest`.
Expected: те же 5 pre-existing failures (`test_auth.py`, `test_challenges.py`, нужна живая Postgres), всё остальное проходит, новых падений нет.

- [ ] **Step 5: Commit**

```bash
git add web/src/webx5/services/points.py web/tests/webx5/services/test_points_award.py
git commit -m "feat: scale task-completion points award by the configured spend rate"
```

---

### Task 2: Реальные челленджи в корзине

**Files:**
- Modify: `x5mobile/src/components/screens/savings-view.tsx`
- Modify: `x5mobile/src/app/index.tsx`

**Interfaces:**
- Consumes: `useChallenges(token) -> {current: ChallengeItem[], history, loading, error}` (уже существует, `x5mobile/src/hooks/useChallenges.ts`). `ChallengeItem` поля: `id, title, description, reward_rub, quantity_target, quantity_current, status` (среди прочих).
- Produces: `SavingsViewProps` больше не включает `tasks`.

Нет тестового фреймворка — верификация: `npx tsc --noEmit` + ручной просмотр экрана.

- [ ] **Step 1: Remove the mock `tasks` prop, wire `useChallenges`**

В `x5mobile/src/components/screens/savings-view.tsx` замени блок импортов:

```typescript
import { BrandColors } from '@/constants/theme';
import { BasketItem, useBasket } from '@/hooks/useBasket';
import { LeaderboardEntry, Savings, Task } from '@/mock-data';

interface SavingsViewProps {
  tasks: Task[];
  leaderboard: LeaderboardEntry[];
  savings: Savings;
  token: string;
  goHome: () => void;
  goHistory: () => void;
  goChallenges: () => void;
  onOrderPlaced: () => void;
}

export function SavingsView({ tasks, leaderboard, savings, token, goHome, goHistory, goChallenges, onOrderPlaced }: SavingsViewProps) {
  const insets = useSafeAreaInsets();
  const {
```

с:

```typescript
import { BrandColors } from '@/constants/theme';
import { BasketItem, useBasket } from '@/hooks/useBasket';
import { ChallengeItem, useChallenges } from '@/hooks/useChallenges';
import { LeaderboardEntry, Savings } from '@/mock-data';

interface SavingsViewProps {
  leaderboard: LeaderboardEntry[];
  savings: Savings;
  token: string;
  goHome: () => void;
  goHistory: () => void;
  goChallenges: () => void;
  onOrderPlaced: () => void;
}

export function SavingsView({ leaderboard, savings, token, goHome, goHistory, goChallenges, onOrderPlaced }: SavingsViewProps) {
  const insets = useSafeAreaInsets();
  const { current: challenges } = useChallenges(token);
  const {
```

- [ ] **Step 2: Render real challenges**

Найди:

```typescript
        {/* Tasks */}
        <Text style={styles.sectionTitle}>Задания</Text>
        <View style={styles.tasksList}>
          {tasks.map(task => (
            <TaskCard key={task.id} task={task} />
          ))}
        </View>
```

замени на:

```typescript
        {/* Tasks */}
        <Text style={styles.sectionTitle}>Задания</Text>
        <View style={styles.tasksList}>
          {challenges.map(challenge => (
            <TaskCard key={challenge.id} challenge={challenge} />
          ))}
        </View>
```

- [ ] **Step 3: Adapt `TaskCard` to `ChallengeItem` fields**

Найди:

```typescript
function TaskCard({ task }: { task: Task }) {
  const progressPct = Math.round((task.progress / task.total) * 100);

  return (
    <View style={styles.taskCard}>
      <View style={styles.taskTopRow}>
        <View style={styles.taskTextBlock}>
          <Text style={styles.taskTitle}>{task.title}</Text>
          <Text style={styles.taskSub}>{task.sub}</Text>
        </View>
        {task.done ? (
          <View style={styles.doneCircle}>
            <Text style={styles.doneCheck}>✓</Text>
          </View>
        ) : (
          <View style={styles.progressPill}>
            <Text style={styles.progressPillText}>{task.progress}/{task.total}</Text>
          </View>
        )}
      </View>

      {/* Task progress bar */}
      <View style={styles.taskProgressTrack}>
        <View
          style={[
            styles.taskProgressFill,
            {
              width: `${progressPct}%` as `${number}%`,
              backgroundColor: task.done ? BrandColors.green : BrandColors.red,
            },
          ]}
        />
      </View>

      {/* Reward */}
      <View style={[styles.rewardBlock, { backgroundColor: task.done ? BrandColors.greenLight : BrandColors.rewardOrangeBg }]}>
        <View style={[styles.rewardDot, { backgroundColor: task.done ? BrandColors.green : BrandColors.gold }]} />
        <Text style={styles.rewardText}>{task.reward}</Text>
      </View>
    </View>
  );
}
```

замени на:

```typescript
function TaskCard({ challenge }: { challenge: ChallengeItem }) {
  const progressPct = Math.min(100, Math.round((challenge.quantity_current / challenge.quantity_target) * 100));
  const done = challenge.status === 'выполнено';

  return (
    <View style={styles.taskCard}>
      <View style={styles.taskTopRow}>
        <View style={styles.taskTextBlock}>
          <Text style={styles.taskTitle}>{challenge.title}</Text>
          <Text style={styles.taskSub}>{challenge.description}</Text>
        </View>
        {done ? (
          <View style={styles.doneCircle}>
            <Text style={styles.doneCheck}>✓</Text>
          </View>
        ) : (
          <View style={styles.progressPill}>
            <Text style={styles.progressPillText}>{challenge.quantity_current}/{challenge.quantity_target}</Text>
          </View>
        )}
      </View>

      {/* Task progress bar */}
      <View style={styles.taskProgressTrack}>
        <View
          style={[
            styles.taskProgressFill,
            {
              width: `${progressPct}%` as `${number}%`,
              backgroundColor: done ? BrandColors.green : BrandColors.red,
            },
          ]}
        />
      </View>

      {/* Reward */}
      <View style={[styles.rewardBlock, { backgroundColor: done ? BrandColors.greenLight : BrandColors.rewardOrangeBg }]}>
        <View style={[styles.rewardDot, { backgroundColor: done ? BrandColors.green : BrandColors.gold }]} />
        <Text style={styles.rewardText}>+{challenge.reward_rub} ₽ при выполнении</Text>
      </View>
    </View>
  );
}
```

- [ ] **Step 4: Drop the `tasks` prop at the call site**

В `x5mobile/src/app/index.tsx` найди:

```typescript
        {screen === 'savings' && (
          <SavingsView
            tasks={data.tasks}
            leaderboard={data.leaderboard}
```

замени на:

```typescript
        {screen === 'savings' && (
          <SavingsView
            leaderboard={data.leaderboard}
```

(Остальные пропсы `<SavingsView>` — `savings`, `token`, `goHome`, `goHistory`, `goChallenges`, `onOrderPlaced` — не меняются.)

- [ ] **Step 5: Type-check**

Run: `cd x5mobile && npx tsc --noEmit`
Expected: no errors. (`data.tasks` в `useMockData()` остаётся неиспользуемым в этом месте, но сам `mock-data.ts` не трогаем — используется для лидерборда, а `tasks` может пригодиться другим экранам в будущем.)

- [ ] **Step 6: Manual verification in the running app**

С Docker-стеком и Expo web поднятыми (см. предыдущие задачи этой сессии): залогинься демо-пользователем с активными челленджами (после запуска `synth`-генерации при первом чеке пользователя должны быть заведены задания), открой «Экономия», убедись, что секция «Задания» показывает реальные названия/описания/прогресс, совпадающие с тем, что видно на отдельном экране «Челленджи» (кнопка 📋 в шапке того же экрана).

- [ ] **Step 7: Commit**

```bash
git add x5mobile/src/components/screens/savings-view.tsx x5mobile/src/app/index.tsx
git commit -m "feat: show real challenges instead of mock tasks in the savings screen"
```

---

### Task 3: «Итого» реагирует на списание баллов

**Files:**
- Modify: `x5mobile/src/components/screens/savings-view.tsx`

**Interfaces:**
- Consumes: `preview.cashback.{cashback_rub, total_paid_rub}` (уже существует, из Task 4 предыдущего плана этой сессии).

Нет тестового фреймворка — верификация: `npx tsc --noEmit` + ручная проверка.

- [ ] **Step 1: Update the totals block**

В `x5mobile/src/components/screens/savings-view.tsx` найди:

```typescript
          {preview && basketItems.length > 0 && (
            <View style={styles.basketTotals}>
              <View style={styles.basketTotalsRow}>
                <Text style={styles.basketTotalsLabel}>Итого</Text>
                <Text style={styles.basketTotalsValue}>{roundedItemsTotal} ₽</Text>
              </View>
              {preview.total_base > preview.total_paid && (
                <View style={styles.basketTotalsRow}>
                  <Text style={styles.basketTotalsLabel}>Скидка</Text>
                  <Text style={styles.basketTotalsDiscount}>
                    −{Math.round(preview.total_base - preview.total_paid)} ₽
                  </Text>
                </View>
              )}
              {preview.cashback && preview.cashback.points_available > 0 && (
                <View style={styles.basketTotalsRow}>
                  <Text style={styles.basketTotalsLabel}>
                    Списать баллы ({preview.cashback.points_available})
                  </Text>
                  <Switch
                    value={spendPoints}
                    onValueChange={setSpendPoints}
                    trackColor={{ false: BrandColors.cardBorder, true: BrandColors.green }}
                  />
                </View>
              )}
              {spendPoints && preview.cashback && preview.cashback.cashback_rub > 0 && (
                <View style={styles.basketTotalsRow}>
                  <Text style={styles.basketTotalsLabel}>Итого с баллами</Text>
                  <Text style={styles.basketTotalsValueGreen}>
                    {Math.round(preview.cashback.total_paid_rub)} ₽
                  </Text>
                </View>
              )}
            </View>
          )}
```

замени на:

```typescript
          {preview && basketItems.length > 0 && (
            <View style={styles.basketTotals}>
              <View style={styles.basketTotalsRow}>
                <Text style={styles.basketTotalsLabel}>Итого</Text>
                <Text style={styles.basketTotalsValue}>
                  {spendPoints && preview.cashback && preview.cashback.cashback_rub > 0
                    ? Math.round(preview.cashback.total_paid_rub)
                    : roundedItemsTotal} ₽
                </Text>
              </View>
              {preview.total_base > preview.total_paid && (
                <View style={styles.basketTotalsRow}>
                  <Text style={styles.basketTotalsLabel}>Скидка</Text>
                  <Text style={styles.basketTotalsDiscount}>
                    −{Math.round(preview.total_base - preview.total_paid)} ₽
                  </Text>
                </View>
              )}
              {preview.cashback && preview.cashback.points_available > 0 && (
                <View style={styles.basketTotalsRow}>
                  <Text style={styles.basketTotalsLabel}>
                    Списать баллы ({preview.cashback.points_available})
                  </Text>
                  <Switch
                    value={spendPoints}
                    onValueChange={setSpendPoints}
                    trackColor={{ false: BrandColors.cardBorder, true: BrandColors.green }}
                  />
                </View>
              )}
              {spendPoints && preview.cashback && preview.cashback.cashback_rub > 0 && (
                <View style={styles.basketTotalsRow}>
                  <Text style={styles.basketTotalsLabel}>Баллами</Text>
                  <Text style={styles.basketTotalsDiscount}>
                    −{preview.cashback.cashback_rub} ₽
                  </Text>
                </View>
              )}
            </View>
          )}
```

(Единственные смысловые изменения: значение строки «Итого» теперь зависит от `spendPoints`/`cashback_rub`; строка «Итого с баллами» заменена на «Баллами: −N ₽» тем же стилем `basketTotalsDiscount`, что и «Скидка». Стиль `basketTotalsValueGreen` в файле может остаться неиспользуемым — не удаляй его объявление в `StyleSheet.create`, просто в этом блоке он больше не применяется.)

- [ ] **Step 2: Type-check**

Run: `cd x5mobile && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Manual verification**

С поднятым стеком: открой корзину с товарами и доступными баллами (`preview.cashback.points_available > 0`), включи тумблер «Списать баллы» — убедись, что «Итого» уменьшилось, и под тумблером появилась строка «Баллами: −N ₽» (не «Итого с баллами»). Выключи тумблер — «Итого» должно вернуться к сумме без баллов.

- [ ] **Step 4: Commit**

```bash
git add x5mobile/src/components/screens/savings-view.tsx
git commit -m "feat: reflect points spend directly in basket Итого instead of a second total"
```

---

### Task 4: Персистентная корзина на неделю

**Files:**
- Modify: `x5mobile/package.json` (via `npx expo install`, not hand-edited)
- Modify: `x5mobile/src/hooks/useBasket.ts`
- Modify: `x5mobile/src/components/screens/savings-view.tsx`

**Interfaces:**
- Produces: `useBasket(token, onOrderPlaced?) -> {items, loading, message, sendInstruction, checkout, preview, spendPoints, setSpendPoints, hasCollected, hydrated, collectWeeklyBasket}` — `hasCollected`/`hydrated: boolean`, `collectWeeklyBasket: () => Promise<void>`. Used by this same task's `savings-view.tsx` edit.

Нет тестового фреймворка — верификация: `npx tsc --noEmit` + ручная проверка (перезаход на экран без потери корзины).

- [ ] **Step 1: Install the storage dependency**

```bash
cd /Users/dimonzhi/Documents/proga/x5hack/x5mobile
npx expo install @react-native-async-storage/async-storage
```

Run: `git -C /Users/dimonzhi/Documents/proga/x5hack diff x5mobile/package.json`
Expected: a new line adding `@react-native-async-storage/async-storage` to `dependencies`, plus `package-lock.json`/`yarn.lock` (whichever this repo uses) updated accordingly.

- [ ] **Step 2: Rewrite `useBasket.ts` with persistence**

Замени содержимое `x5mobile/src/hooks/useBasket.ts` целиком:

```typescript
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useEffect, useState } from 'react';

import { apiFetch } from '@/api/client';

const STORAGE_KEY = '@x5hack/weeklyBasket';

export interface BasketItem {
  product_id: string;
  name: string;
  quantity: number;
  price: number;
}

interface SuggestedBasketResponse {
  items: BasketItem[];
}

interface AssistantResponse {
  items: BasketItem[];
  applied: boolean;
  message: string | null;
}

interface CheckoutResponse {
  total_saved: number;
}

export interface BasketPreviewItem {
  product_id: string;
  product_name: string;
  quantity: number;
  base_price: number;
  paid_price: number;
  discount_id: string | null;
  discounted_amount: number;
}

export interface BasketPreviewCashback {
  points_available: number;
  points_to_apply: number;
  cashback_rub: number;
  total_paid_rub: number;
  points_balance_after: number;
  points_capped_by: 'none' | 'balance' | 'receipt_total';
  rate_points_per_rub: number;
}

export interface BasketPreview {
  items: BasketPreviewItem[];
  total_base: number;
  total_paid: number;
  total_saved: number;
  cashback: BasketPreviewCashback | null;
}

export function useBasket(token: string | null, onOrderPlaced?: () => void) {
  const [items, setItems] = useState<BasketItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [preview, setPreview] = useState<BasketPreview | null>(null);
  const [spendPoints, setSpendPoints] = useState(false);
  const [hasCollected, setHasCollected] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(STORAGE_KEY);
        if (raw !== null) {
          setItems(JSON.parse(raw));
          setHasCollected(true);
        }
      } catch {
        // corrupt or unavailable storage — start with an empty, uncollected basket
      } finally {
        setHydrated(true);
      }
    })();
  }, []);

  useEffect(() => {
    if (!hydrated || !hasCollected) return;
    AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(items)).catch(() => {});
  }, [items, hasCollected, hydrated]);

  useEffect(() => {
    if (!token || items.length === 0) {
      setPreview(null);
      return;
    }
    apiFetch<BasketPreview>('/basket/preview', token, {
      method: 'POST',
      body: JSON.stringify({
        items: items.map((i) => ({ product_id: i.product_id, quantity: i.quantity })),
        points_to_spend: spendPoints ? 'all' : null,
      }),
    })
      .then(setPreview)
      .catch(() => setPreview(null));
  }, [token, items, spendPoints]);

  async function collectWeeklyBasket() {
    if (!token) return;
    setLoading(true);
    try {
      const data = await apiFetch<SuggestedBasketResponse>('/basket/suggested', token);
      setItems(data.items);
      setHasCollected(true);
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : 'Ошибка сбора корзины');
    } finally {
      setLoading(false);
    }
  }

  async function sendInstruction(instruction: string) {
    if (!token || !instruction.trim()) return;
    setLoading(true);
    try {
      const res = await apiFetch<AssistantResponse>('/basket/assistant', token, {
        method: 'POST',
        body: JSON.stringify({
          items: items.map((i) => ({ product_id: i.product_id, quantity: i.quantity })),
          instruction,
        }),
      });
      setItems(res.items);
      setMessage(res.applied ? null : res.message);
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : 'Ошибка запроса');
    } finally {
      setLoading(false);
    }
  }

  async function checkout() {
    if (!token || items.length === 0) return;
    setLoading(true);
    try {
      const res = await apiFetch<CheckoutResponse>('/basket/checkout', token, {
        method: 'POST',
        body: JSON.stringify({
          items: items.map((i) => ({ product_id: i.product_id, quantity: i.quantity })),
          points_to_spend: spendPoints ? 'all' : null,
        }),
      });
      setItems([]);
      setHasCollected(false);
      setPreview(null);
      setSpendPoints(false);
      AsyncStorage.removeItem(STORAGE_KEY).catch(() => {});
      setMessage(`Заказ оформлен! Сэкономлено ${Math.round(res.total_saved)} ₽`);
      onOrderPlaced?.();
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : 'Ошибка оформления заказа');
    } finally {
      setLoading(false);
    }
  }

  return {
    items,
    loading,
    message,
    sendInstruction,
    checkout,
    preview,
    spendPoints,
    setSpendPoints,
    hasCollected,
    hydrated,
    collectWeeklyBasket,
  };
}
```

(Обрати внимание: старый `useEffect`, автоматически вызывавший `GET /basket/suggested` при монтировании, полностью удалён — заменён на чтение из `AsyncStorage` и явный `collectWeeklyBasket()`.)

- [ ] **Step 3: Wire the collect button into `savings-view.tsx`**

Замени деструктуризацию хука:

```typescript
  const {
    items: basketItems,
    loading: basketLoading,
    message: basketMessage,
    sendInstruction,
    checkout,
    preview,
    spendPoints,
    setSpendPoints,
  } = useBasket(token, onOrderPlaced);
```

на:

```typescript
  const {
    items: basketItems,
    loading: basketLoading,
    message: basketMessage,
    sendInstruction,
    checkout,
    preview,
    spendPoints,
    setSpendPoints,
    hasCollected,
    hydrated,
    collectWeeklyBasket,
  } = useBasket(token, onOrderPlaced);
```

Найди the item-list block (which after Tasks 2-3 of this plan should be otherwise unchanged from the prior plan's state):

```typescript
          {basketLoading && basketItems.length === 0 ? (
            <ActivityIndicator color={BrandColors.textSecondary} />
          ) : basketItems.length > 0 ? (
            pricedItems.map(({ item, unitBase, lineTotal }) => {
              const hasDiscount = lineTotal < Math.round(unitBase * item.quantity);
              return (
                <View key={item.product_id} style={styles.basketRow}>
                  <View style={styles.basketItemInfo}>
                    <Text style={styles.basketItemName}>{item.name}</Text>
                    <Text style={styles.basketItemQty}>{item.quantity} шт</Text>
                  </View>
                  <View style={styles.basketItemPrices}>
                    {hasDiscount && (
                      <Text style={styles.basketItemBasePrice}>{Math.round(unitBase * item.quantity)} ₽</Text>
                    )}
                    <Text style={styles.basketItemPaidPrice}>{lineTotal} ₽</Text>
                  </View>
                </View>
              );
            })
          ) : !basketMessage?.startsWith('Заказ оформлен') ? (
            <Text style={styles.basketEmptyText}>Пока нечего предложить — мало истории покупок</Text>
          ) : null}
```

замени на:

```typescript
          {!hydrated ? (
            <ActivityIndicator color={BrandColors.textSecondary} />
          ) : basketLoading && basketItems.length === 0 ? (
            <ActivityIndicator color={BrandColors.textSecondary} />
          ) : basketItems.length > 0 ? (
            pricedItems.map(({ item, unitBase, lineTotal }) => {
              const hasDiscount = lineTotal < Math.round(unitBase * item.quantity);
              return (
                <View key={item.product_id} style={styles.basketRow}>
                  <View style={styles.basketItemInfo}>
                    <Text style={styles.basketItemName}>{item.name}</Text>
                    <Text style={styles.basketItemQty}>{item.quantity} шт</Text>
                  </View>
                  <View style={styles.basketItemPrices}>
                    {hasDiscount && (
                      <Text style={styles.basketItemBasePrice}>{Math.round(unitBase * item.quantity)} ₽</Text>
                    )}
                    <Text style={styles.basketItemPaidPrice}>{lineTotal} ₽</Text>
                  </View>
                </View>
              );
            })
          ) : !basketMessage?.startsWith('Заказ оформлен') ? (
            <View style={styles.basketCollectBlock}>
              <Text style={styles.basketEmptyText}>
                {hasCollected
                  ? 'Пока нечего предложить — мало истории покупок'
                  : 'Соберите корзину на неделю на основе своих покупок'}
              </Text>
              <TouchableOpacity
                style={[styles.collectBtn, basketLoading && styles.collectBtnDisabled]}
                onPress={collectWeeklyBasket}
                activeOpacity={0.7}
                disabled={basketLoading}>
                {basketLoading
                  ? <ActivityIndicator color="#fff" size="small" />
                  : <Text style={styles.collectBtnText}>Собрать корзину на неделю</Text>
                }
              </TouchableOpacity>
            </View>
          ) : null}
```

- [ ] **Step 4: Add the new styles**

Найди в `StyleSheet.create`:

```typescript
  basketEmptyText: {
    fontSize: 13,
    color: BrandColors.textSecondary,
  },
```

и добавь сразу после него:

```typescript
  basketCollectBlock: {
    gap: 10,
    alignItems: 'flex-start',
  },
  collectBtn: {
    backgroundColor: BrandColors.dark,
    borderRadius: 12,
    paddingVertical: 10,
    paddingHorizontal: 16,
    alignItems: 'center',
    justifyContent: 'center',
  },
  collectBtnDisabled: {
    backgroundColor: BrandColors.cardBorder,
  },
  collectBtnText: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '700',
  },
```

- [ ] **Step 5: Type-check**

Run: `cd x5mobile && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Manual verification**

С поднятым стеком (backend пересобрать при необходимости — этот план не меняет backend-код, кроме Task 1, но раз уж пересобираешь — пересобери и его: `docker compose build web worker beat && docker compose up -d web worker beat`) и Expo web:

1. Если раньше в этой сессии уже собиралась корзина — очисти состояние приложения браузера (localStorage/AsyncStorage веб-полифилла) или используй режим инкогнито, чтобы проверить действительно первый заход.
2. Открой «Экономия» — корзина должна быть пустая, с кнопкой «Собрать корзину на неделю» (не с автоматически заполненным списком).
3. Нажми кнопку — корзина заполняется предложенными товарами.
4. Перейди на другой экран (например, «Главная») и вернись на «Экономия» — корзина должна остаться той же, без повторного авто-сбора.
5. Попроси Аппи добавить/убрать товар, перейди на другой экран и вернись — изменение должно сохраниться.
6. Оформи заказ — корзина очищается; перейди на другой экран и вернись — корзина должна снова быть пустой с кнопкой «Собрать корзину на неделю» (не восстанавливать оформленный заказ).

- [ ] **Step 7: Commit**

```bash
git add x5mobile/package.json x5mobile/package-lock.json x5mobile/src/hooks/useBasket.ts x5mobile/src/components/screens/savings-view.tsx
git commit -m "feat: persist weekly basket on-device, collect explicitly instead of auto-fetching"
```

(Замени `package-lock.json` на реальный lock-файл этого репозитория, если используется другой пакетный менеджер — проверь по `git status` после Step 1, какой файл реально изменился.)
