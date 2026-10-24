const test = require('node:test');
const assert = require('node:assert/strict');
const { loadDashboard, plain } = require('./harness');

const profile = {
  name: 'ผู้ใช้ทดสอบ', profile_completed: true, age: 30, gender: 'female',
  height_cm: 165, weight_kg: 58, activity_level: '1.45', goal: 'recomposition',
  daily_target_kcal: 1900, target_protein_g: 110, target_carbs_g: 220,
  target_fat_g: 60, targets_customized: false, bmr: 1350, tdee: 1957,
};
const today = {
  food_consumed: 620, food_target: 1900, remaining_kcal: 1280, exercise_estimate: 0,
  protein: 31, carbs: 80, fat: 18, target_protein: 110, target_carbs: 220,
  target_fat: 60, food_logs: [],
};

function reply(data, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => plain(data), clone() { return reply(data, status); } };
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

async function until(predicate, message = 'timed out waiting for UI state') {
  for (let i = 0; i < 100; i++) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
  assert.fail(message);
}

function endpointFetch(overrides = {}) {
  const calls = [];
  const fetchImpl = async (url, options = {}) => {
    const parsed = new URL(String(url));
    const call = { path: parsed.pathname + parsed.search, method: options.method || 'GET', body: options.body };
    calls.push(call);
    const override = overrides[call.path] || overrides[call.method + ' ' + parsed.pathname];
    if (override) return override(call, calls.length);
    if (parsed.pathname.endsWith('/profile')) return reply(profile);
    if (parsed.pathname.endsWith('/today')) return reply(today);
    if (parsed.pathname.endsWith('/workout-sessions')) return reply({ sessions: [] });
    if (parsed.pathname.endsWith('/workout-programs')) return reply({ programs: [{ id: 1, name: 'เวท', exercises: [] }] });
    if (parsed.pathname.endsWith('/cardio-presets')) return reply({ presets: [] });
    if (parsed.pathname.endsWith('/history')) return reply({ summary: {}, daily_breakdown: [], available_years: [2026] });
    return reply({});
  };
  return { fetchImpl, calls };
}

test('loading UI keeps muted text readable and mobile navigation labels at least 11px', () => {
  const window = loadDashboard();
  const css = window.document.querySelector('style').textContent;
  const muted = css.match(/--muted:(#[\da-f]{6})/i)?.[1];
  assert.ok(muted, 'the theme defines its muted text color');
  const luminance = (hex) => hex.match(/[\da-f]{2}/gi).map((channel) => parseInt(channel, 16) / 255)
    .map((value) => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4)
    .reduce((sum, value, index) => sum + value * [0.2126, 0.7152, 0.0722][index], 0);
  for (const background of ['#ffffff', '#f5f8fc', '#f7faff']) {
    assert.ok((luminance(background) + 0.05) / (luminance(muted) + 0.05) >= 4.5, `muted text contrast on ${background}`);
  }
  assert.match(css, /@media\(max-width:380px\).*?\.bottom-nav button\{font-size:11px\}/s);
  window.close();
});

async function authenticated(fetchImpl, options = {}) {
  const window = loadDashboard({ authenticated: true, fetchImpl, ...options });
  await until(() => window.document.getElementById('headerUser').textContent === 'ผู้ใช้: ผู้ใช้ทดสอบ' || window.document.querySelector('#todayRoot [role="alert"]'));
  return window;
}

test('startup keeps shaped skeletons visible while LIFF initialization is pending', async () => {
  const gate = deferred();
  const window = loadDashboard({ authenticated: true, liffInit: () => gate.promise });
  const todayRoot = window.document.getElementById('todayRoot');
  assert.equal(todayRoot.getAttribute('aria-busy'), 'true');
  assert.ok(todayRoot.querySelector('.skeleton-ring'), 'Today skeleton follows the calorie-ring layout');
  assert.equal(window.document.querySelectorAll('#profileRoot .skeleton-field-input').length, 7);
  gate.resolve();
  window.close();
});

test('a Today read crossing the Bangkok date boundary is discarded and reloaded', async () => {
  const firstToday = deferred();
  let now = Date.UTC(2026, 9, 24, 16, 59, 59);
  let todayReads = 0;
  const { fetchImpl, calls } = endpointFetch({
    'GET /api/me/today': () => ++todayReads === 1 ? firstToday.promise : reply({ ...today, food_consumed: 777 }),
  });
  const window = loadDashboard({ authenticated: true, fetchImpl, dateNow: () => now });
  await until(() => window.document.getElementById('headerUser').textContent.includes('ผู้ใช้ทดสอบ'));
  await until(() => todayReads === 1);
  now = Date.UTC(2026, 9, 24, 17, 0, 1);
  firstToday.resolve(reply({ ...today, food_consumed: 111 }));
  await until(() => todayReads === 2);
  await until(() => window.document.getElementById('todayRoot').textContent.includes('777'));
  assert.doesNotMatch(window.document.getElementById('todayRoot').textContent, /111/);
  assert.equal(calls.filter((call) => call.path === '/api/me/today').length, 2);
  window.close();
});

test('startup auth failure leaves recovery visible on the tab selected while LIFF was pending', async () => {
  const gate = deferred();
  const window = loadDashboard({ authenticated: true, liffInit: () => gate.promise });
  window.setTab('programs');
  gate.reject(new Error('synthetic LIFF failure'));
  await until(() => window.document.querySelector('#programsRoot h2')?.textContent === 'เชื่อมต่อ LINE ไม่สำเร็จ');
  assert.equal(window.document.querySelector('.content.active')?.id, 'tab-programs');
  assert.ok(window.document.querySelector('#programsRoot button'));
  assert.equal(window.document.getElementById('programsRoot').getAttribute('aria-busy'), null);
  window.close();
});

test('rapid tab revisits share the in-flight request and reuse fresh program data', async () => {
  const waitPrograms = deferred();
  const { fetchImpl, calls } = endpointFetch({
    'GET /api/me/workout-programs': () => waitPrograms.promise,
  });
  const window = await authenticated(fetchImpl);
  window.setTab('programs');
  window.setTab('programs');
  window.setTab('programs');
  await until(() => calls.filter((call) => call.path === '/api/me/workout-programs').length === 1);
  assert.equal(window.document.getElementById('programsRoot').getAttribute('aria-busy'), 'true');
  waitPrograms.resolve(reply({ programs: [{ id: 1, name: 'เวท', exercises: [] }] }));
  await until(() => window.document.getElementById('programsRoot').dataset.loaded === 'true');
  window.setTab('programs');
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(calls.filter((call) => call.path === '/api/me/workout-programs').length, 1);
  assert.equal(calls.filter((call) => call.path === '/api/me/cardio-presets').length, 1);
  window.close();
});

test('a slow mutation immediately marks its button busy and ignores a duplicate click', async () => {
  const pending = deferred();
  const { fetchImpl, calls } = endpointFetch({ 'POST /api/me/workout-sessions': () => pending.promise });
  const window = await authenticated(fetchImpl);
  await window.loadPrograms();
  const save = [...window.document.querySelectorAll('#programsRoot button')].find((item) => item.textContent === 'บันทึกวันนี้');
  save.click();
  assert.equal(save.disabled, true);
  assert.equal(save.getAttribute('aria-busy'), 'true');
  assert.match(save.getAttribute('aria-label'), /กำลังบันทึก/);
  save.click();
  assert.equal(calls.filter((call) => call.method === 'POST' && call.path === '/api/me/workout-sessions').length, 1);
  pending.resolve(reply({}));
  await until(() => !save.disabled);
  assert.equal(save.hasAttribute('aria-busy'), false);
  window.close();
});

test('failed save leaves the sheet and typed program draft available for retry', async () => {
  let writes = 0;
  const { fetchImpl, calls } = endpointFetch({
    'POST /api/me/workout-programs': () => ++writes === 1 ? Promise.reject(new TypeError('Failed to fetch')) : reply({}),
  });
  const window = await authenticated(fetchImpl);
  window.openProgramEditor();
  const name = window.document.querySelector('#modalSheet input');
  name.value = 'โปรแกรมที่พิมพ์ไว้';
  const save = [...window.document.querySelectorAll('#modalSheet .modal-actions button')].find((item) => item.textContent === 'บันทึก');
  save.click();
  await until(() => !save.disabled);
  assert.equal(window.document.querySelector('#modalSheet input').value, 'โปรแกรมที่พิมพ์ไว้');
  assert.equal(window.document.getElementById('modal').getAttribute('aria-hidden'), 'false');
  assert.match(window.document.querySelector('.toast')?.textContent || '', /เชื่อมต่อไม่สำเร็จ/);
  assert.equal(calls.filter((call) => call.method === 'POST').length, 1, 'failed write is not retried automatically');
  save.click();
  await until(() => window.document.getElementById('modal').getAttribute('aria-hidden') === 'true');
  assert.equal(calls.filter((call) => call.method === 'POST').length, 2);
  window.close();
});

test('backdrop cannot discard a modal draft while its write is pending', async () => {
  const pending = deferred();
  const { fetchImpl } = endpointFetch({ 'POST /api/me/workout-programs': () => pending.promise });
  const window = await authenticated(fetchImpl);
  window.openProgramEditor();
  const name = window.document.querySelector('#modalSheet input');
  name.value = 'เก็บร่างนี้ไว้';
  const save = [...window.document.querySelectorAll('#modalSheet .modal-actions button')].find((item) => item.textContent === 'บันทึก');
  save.click();
  window.document.getElementById('modal').dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
  assert.equal(window.document.getElementById('modal').getAttribute('aria-hidden'), 'false');
  assert.equal(window.document.querySelector('#modalSheet input').value, 'เก็บร่างนี้ไว้');
  pending.reject(new TypeError('Failed to fetch'));
  await until(() => !save.disabled);
  assert.equal(window.document.querySelector('#modalSheet input').value, 'เก็บร่างนี้ไว้');
  assert.equal(window.document.getElementById('modal').getAttribute('aria-hidden'), 'false');
  window.close();
});

test('a pre-write programs response cannot replace the fresh post-write result', async () => {
  const programReads = [];
  const { fetchImpl, calls } = endpointFetch({
    'GET /api/me/workout-programs': () => {
      const request = deferred();
      programReads.push(request);
      return request.promise;
    },
  });
  const window = await authenticated(fetchImpl);
  const staleLoad = window.loadPrograms();
  await until(() => programReads.length === 1);
  window.openProgramEditor();
  const name = window.document.querySelector('#modalSheet input');
  name.value = 'รายการใหม่';
  [...window.document.querySelectorAll('#modalSheet .modal-actions button')].find((item) => item.textContent === 'บันทึก').click();
  await until(() => programReads.length === 2);
  programReads[1].resolve(reply({ programs: [{ id: 2, name: 'รายการใหม่', exercises: [] }] }));
  await until(() => window.document.getElementById('programsRoot').textContent.includes('รายการใหม่'));
  programReads[0].resolve(reply({ programs: [] }));
  await staleLoad;
  await until(() => window.document.getElementById('programsRoot').dataset.loaded === 'true');
  window.setTab('programs');
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.match(window.document.getElementById('programsRoot').textContent, /รายการใหม่/);
  assert.equal(calls.filter((call) => call.method === 'GET' && call.path === '/api/me/workout-programs').length, 2);
  window.close();
});

test('profile save stays disabled until the response body is parsed', async () => {
  const body = deferred();
  const { fetchImpl, calls } = endpointFetch({
    'PUT /api/me/profile': () => ({ ok: true, status: 200, json: () => body.promise }),
  });
  const window = await authenticated(fetchImpl);
  window.setTab('profile');
  const save = [...window.document.querySelectorAll('#profileRoot button')].find((item) => item.textContent === 'บันทึกโปรไฟล์');
  save.click();
  await until(() => calls.some((call) => call.method === 'PUT' && call.path === '/api/me/profile'));
  assert.equal(save.disabled, true);
  assert.equal(save.getAttribute('aria-busy'), 'true');
  save.click();
  assert.equal(calls.filter((call) => call.method === 'PUT' && call.path === '/api/me/profile').length, 1);
  window.setTab('programs');
  await until(() => window.document.querySelector('#programsRoot button'));
  [...window.document.querySelectorAll('#programsRoot button')].find((item) => item.textContent === 'บันทึกวันนี้')?.click();
  assert.equal(calls.filter((call) => call.method === 'POST').length, 0, 'another tab action cannot overlap the pending profile save');
  body.resolve(plain({ profile }));
  await until(() => !save.disabled);
  window.close();
});

test('profile save does not pull the user back to Today after they navigate away', async () => {
  const body = deferred();
  const { fetchImpl } = endpointFetch({
    'PUT /api/me/profile': () => ({ ok: true, status: 200, json: () => body.promise }),
  });
  const window = await authenticated(fetchImpl);
  window.setTab('profile');
  const save = [...window.document.querySelectorAll('#profileRoot button')].find((item) => item.textContent === 'บันทึกโปรไฟล์');
  save.click();
  await until(() => save.getAttribute('aria-busy') === 'true');
  window.setTab('programs');
  await until(() => window.document.getElementById('programsRoot').dataset.loaded === 'true');
  body.resolve(plain({ profile }));
  await until(() => window.document.querySelector('.toast')?.textContent === 'บันทึกโปรไฟล์แล้ว');
  assert.equal(window.document.querySelector('.content.active')?.id, 'tab-programs');
  window.close();
});

test('capture lookup network failure is shown instead of escaping as an unhandled rejection', async () => {
  const { fetchImpl } = endpointFetch({
    'GET /api/me/food-captures/demo': () => Promise.reject(new TypeError('Failed to fetch')),
  });
  const window = loadDashboard({ authenticated: true, fetchImpl, url: 'https://example.test/webapp?capture_token=demo' });
  await until(() => window.document.querySelector('.toast'));
  assert.match(window.document.querySelector('.toast').textContent, /เปิดรายการอาหารไม่สำเร็จ/);
  assert.equal(window.document.getElementById('modal').getAttribute('aria-hidden'), 'true');
  window.close();
});

test('a late capture response cannot reopen a private draft after account deletion', async () => {
  const pendingCapture = deferred();
  let profileReads = 0;
  let captureReads = 0;
  const { fetchImpl } = endpointFetch({
    'GET /api/me/profile': () => reply(++profileReads === 1 ? profile : { ...profile, name: '', profile_completed: false }),
    'GET /api/me/food-captures/demo': () => { captureReads += 1; return pendingCapture.promise; },
    'DELETE /api/me/account': () => reply({}),
  });
  const window = await authenticated(fetchImpl);
  window.confirm = () => true;
  const loading = window.loadCapture('demo');
  await until(() => captureReads === 1);
  await window.deleteAccount();
  assert.equal(window.document.getElementById('modal').getAttribute('aria-hidden'), 'true');
  pendingCapture.resolve(reply({ status: 'draft', items: [{ food_name: 'ข้อมูลเก่า', calories: 100 }] }));
  await loading;
  assert.equal(window.document.getElementById('modal').getAttribute('aria-hidden'), 'true');
  assert.doesNotMatch(window.document.getElementById('modalSheet').textContent, /ข้อมูลเก่า/);
  window.close();
});

test('account deletion clears rendered private tabs before the replacement profile reads finish', async () => {
  const pendingReplacementToday = deferred();
  const oldToday = { ...today, food_logs: [{ id: 99, name: 'อาหารบัญชีเก่า', calories: 500, protein: 10, carbs: 20, fat: 5 }] };
  let profileReads = 0;
  let todayReads = 0;
  const { fetchImpl } = endpointFetch({
    'GET /api/me/profile': () => reply(++profileReads === 1 ? profile : { ...profile, name: '', profile_completed: false }),
    'GET /api/me/today': () => ++todayReads === 1 ? reply(oldToday) : pendingReplacementToday.promise,
    'DELETE /api/me/account': () => reply({}),
    'PUT /api/me/profile': () => reply({ profile }),
  });
  const window = await authenticated(fetchImpl);
  await until(() => window.document.getElementById('todayRoot').textContent.includes('อาหารบัญชีเก่า'));
  await window.loadPrograms();
  await window.loadHistory();
  window.setTab('profile');
  window.confirm = () => true;
  await window.deleteAccount();
  for (const id of ['todayRoot', 'historyRoot', 'programsRoot']) {
    const root = window.document.getElementById(id);
    assert.equal(root.dataset.loaded, 'false');
    assert.equal(root.childElementCount, 0);
    assert.doesNotMatch(root.textContent, /อาหารบัญชีเก่า|เวท/);
  }
  assert.equal(window.document.getElementById('headerUser').textContent, '');
  const saveProfile = [...window.document.querySelectorAll('#profileRoot button')].find((item) => item.textContent === 'บันทึกโปรไฟล์');
  saveProfile.click();
  await until(() => todayReads === 2);
  const todayRoot = window.document.getElementById('todayRoot');
  assert.equal(todayRoot.getAttribute('aria-busy'), 'true');
  assert.doesNotMatch(todayRoot.textContent, /อาหารบัญชีเก่า/);
  assert.equal(window.document.getElementById('historyRoot').textContent, '');
  assert.equal(window.document.getElementById('programsRoot').textContent, '');
  pendingReplacementToday.resolve(reply({ ...today, food_logs: [{ name: 'อาหารบัญชีใหม่', calories: 120 }] }));
  await until(() => todayRoot.textContent.includes('อาหารบัญชีใหม่'));
  assert.doesNotMatch(todayRoot.textContent, /อาหารบัญชีเก่า/);
  window.close();
});

test('profile edits survive navigation away and back without a second profile read', async () => {
  const { fetchImpl, calls } = endpointFetch();
  const window = await authenticated(fetchImpl);
  window.setTab('profile');
  await until(() => window.document.querySelector('#profileRoot input'));
  const name = window.document.querySelector('#profileRoot input');
  name.value = 'ร่างที่ยังไม่บันทึก';
  window.setTab('today');
  window.setTab('profile');
  assert.equal(window.document.querySelector('#profileRoot input').value, 'ร่างที่ยังไม่บันทึก');
  assert.equal(calls.filter((call) => call.path === '/api/me/profile').length, 1);
  window.close();
});

test('a session editor opens immediately, and a late response cannot reopen it after cancel', async () => {
  const detail = deferred();
  const { fetchImpl } = endpointFetch({ 'GET /api/me/workout-sessions/1': () => detail.promise });
  const window = loadDashboard();
  window.fetch = fetchImpl;
  const loading = window.openSessionEditor(1);
  assert.equal(window.document.getElementById('modal').getAttribute('aria-hidden'), 'false');
  assert.ok(window.document.querySelector('#modalSheet [role="status"]'));
  window.closeModal();
  detail.resolve(reply({ id: 1, type: 'strength', name: 'เวท', exercises: [] }));
  await loading;
  assert.equal(window.document.getElementById('modal').getAttribute('aria-hidden'), 'true');
  assert.equal(window.document.querySelector('#modalSheet input'), null);
  window.close();
});

test('first-load network failure clears skeleton busy state and offers retry', async () => {
  let todayReads = 0;
  const { fetchImpl } = endpointFetch({
    'GET /api/me/today': () => ++todayReads === 1 ? Promise.reject(new TypeError('Failed to fetch')) : reply(today),
  });
  const window = await authenticated(fetchImpl);
  const root = window.document.getElementById('todayRoot');
  await until(() => root.querySelector('.load-error'));
  assert.equal(root.getAttribute('aria-busy'), null);
  assert.equal(root.querySelector('.skeleton-stack'), null);
  assert.match(root.querySelector('.load-error').textContent, /เชื่อมต่อไม่สำเร็จ/);
  const retry = [...root.querySelectorAll('button')].find((item) => item.textContent === 'ลองอีกครั้ง');
  retry.click();
  await until(() => root.dataset.loaded === 'true');
  assert.equal(root.querySelector('.load-error'), null);
  assert.equal(root.getAttribute('aria-busy'), null);
  window.close();
});

test('a 401 during startup clears all skeletons and shows the LINE sign-in recovery', async () => {
  const { fetchImpl } = endpointFetch({ 'GET /api/me/profile': () => reply({ detail: 'unauthorized' }, 401) });
  const window = loadDashboard({ authenticated: true, fetchImpl });
  await until(() => window.document.querySelector('#todayRoot h2')?.textContent === 'เชื่อมต่อ LINE ไม่สำเร็จ');
  for (const id of ['todayRoot', 'historyRoot', 'programsRoot', 'profileRoot']) {
    assert.equal(window.document.getElementById(id).getAttribute('aria-busy'), null);
    assert.equal(window.document.getElementById(id).querySelector('.skeleton-stack'), null);
  }
  window.close();
});

test('an older history response cannot replace the period selected later', async () => {
  const pending = [];
  const historyResult = (total) => ({
    summary: { total_calories_in: total, total_calories_burned: 0, average_daily_calories: total },
    daily_breakdown: [{ date: '2026-10-19', calories_in: total, food_logs: [], workout_logs: [] }],
    available_years: [2026],
  });
  let historyCalls = 0;
  const { fetchImpl } = endpointFetch({
    'GET /api/me/history': () => {
      historyCalls += 1;
      if (historyCalls === 1) return reply(historyResult(10));
      const request = deferred();
      pending.push(request);
      return request.promise;
    },
  });
  const window = await authenticated(fetchImpl);
  window.setTab('history');
  await until(() => window.document.querySelector('#historyRoot .history-nav button'));
  const previous = window.document.querySelector('#historyRoot .history-nav button[aria-label="สัปดาห์ก่อน"]');
  previous.click();
  await until(() => pending.length === 1);
  previous.click();
  await until(() => pending.length === 2);
  pending[1].resolve(reply(historyResult(333)));
  await until(() => window.document.querySelector('#historyRoot').textContent.includes('333 kcal'));
  pending[0].resolve(reply(historyResult(111)));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.match(window.document.querySelector('#historyRoot').textContent, /333 kcal/);
  assert.doesNotMatch(window.document.querySelector('#historyRoot').textContent, /111 kcal/);
  window.close();
});
