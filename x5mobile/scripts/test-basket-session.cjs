// Run with node scripts/test-basket-session.cjs. Exercise the actual hook with
// deferred network/storage responses, including React StrictMode effect replay.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const code = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/hooks/useBasket.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText;
const flush = () => new Promise(setImmediate);

async function scenario(failLogin = false) {
  const states = [], refs = [], effects = [];
  let stateIndex = 0, refIndex = 0, effectIndex = 0;
  const requests = [];
  const item = { product_id: 'milk', name: 'Молоко', quantity: 4, price: 90 };
  const stored = new Map([['@x5hack/weeklyBasket/user', JSON.stringify([{ ...item, quantity: 1 }])]]);
  const storage = {
    async getItem(key) { return stored.get(key) ?? null; },
    async setItem(key, value) { stored.set(key, value); },
    async removeItem(key) { stored.delete(key); },
  };
  let finishGeneration;
  const generation = new Promise((resolve, reject) => { finishGeneration = fail => fail ? reject(Error('offline')) : resolve({ items: [item] }); });
  const react = {
    useState(initial) {
      const i = stateIndex++;
      if (!(i in states)) states[i] = initial;
      return [states[i], value => { states[i] = typeof value === 'function' ? value(states[i]) : value; }];
    },
    useRef(initial) { const i = refIndex++; return refs[i] ??= { current: initial }; },
    useEffect(fn, deps) {
      const i = effectIndex++;
      const old = effects[i];
      if (!old || deps.some((dep, j) => dep !== old.deps[j])) {
        old?.cleanup?.();
        effects[i] = { fn, deps, cleanup: fn() };
      }
    },
  };
  const exports = {};
  vm.runInNewContext(code, { exports, require(name) {
    if (name === 'react') return react;
    if (name.includes('async-storage')) return { __esModule: true, default: storage };
    return { async apiFetch(url) {
      requests.push(url);
      if (url === '/me') return { user_id: 'user' };
      if (url === '/basket/suggested') return generation;
      if (url === '/basket/checkout') return { total_saved: 0 };
      if (url === '/basket/preview') return { items: [] };
      throw Error(url);
    } };
  } });
  const render = () => { stateIndex = refIndex = effectIndex = 0; return exports.useBasket('token'); };
  render();
  effects[0].cleanup(); effects[0].cleanup = effects[0].fn(); // StrictMode replay
  await flush();
  let basket = render();
  assert.equal(requests.filter(url => url === '/basket/suggested').length, 1);
  assert.equal(basket.loading, true);
  assert.equal(await basket.checkout(), false); // no checkout while login generation runs
  finishGeneration(failLogin);
  await flush(); basket = render();
  assert.equal(basket.loading, false);
  assert.equal(basket.items[0].quantity, failLogin ? 1 : 4);
  if (failLogin) {
    assert.match(basket.message, /не удалось/);
    return;
  }
  // Renders / screen navigation do not own or recreate the basket hook.
  render(); render();
  assert.equal(await basket.checkout(), true);
  await flush(); basket = render(); await flush(); render();
  assert.equal(basket.items.length, 0);
  assert.equal(stored.has('@x5hack/weeklyBasket/user'), false);
  assert.equal(requests.filter(url => url === '/basket/suggested').length, 1);
  await basket.collectWeeklyBasket();
  assert.equal(requests.filter(url => url === '/basket/suggested').length, 2);
  assert.equal(render().items.length, 1);
}
(async () => {
  await scenario();
  await scenario(true);
  console.log('PASS: one login request, StrictMode replay, loading lock, checkout stays empty, explicit rebuild, failure preserves saved basket');
})().catch(error => { console.error(error); process.exitCode = 1; });
