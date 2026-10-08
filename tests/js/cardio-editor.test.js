const test = require('node:test');
const assert = require('node:assert/strict');
const { loadDashboard, plain } = require('./harness');

function mockApi(window, session) {
  const requests = [];
  window.fetch = async (url, options = {}) => {
    const request = { url: String(url), method: options.method || 'GET', body: options.body ? JSON.parse(options.body) : undefined };
    requests.push(request);
    if (request.url.endsWith('/api/me/workout-sessions/1') && request.method === 'GET') {
      return { ok: true, json: async () => plain(session) };
    }
    if (request.url.endsWith('/api/me/workout-programs')) return { ok: true, json: async () => ({ programs: [] }) };
    if (request.url.endsWith('/api/me/cardio-presets')) return { ok: true, json: async () => ({ presets: [] }) };
    if (request.url.includes('/api/me/history')) return { ok: true, json: async () => ({}) };
    if (request.url.includes('/api/me/workout-sessions')) return { ok: true, json: async () => plain(session) };
    return { ok: true, json: async () => ({}) };
  };
  return requests;
}

function inputFor(window, label) {
  const field = [...window.document.querySelectorAll('#modalSheet .field')]
    .find((element) => element.querySelector('label')?.textContent === label);
  assert.ok(field, 'field ' + label + ' is visible');
  return field.querySelector('input,select');
}

async function clickSave(window) {
  const save = [...window.document.querySelectorAll('#modalSheet .modal-actions button')]
    .find((button) => button.textContent === 'บันทึก');
  assert.ok(save, 'save button is visible');
  save.click();
  await new Promise((resolve) => window.setTimeout(resolve, 0));
}

test('walking steps can be saved with blank minutes', async () => {
  const window = loadDashboard();
  const requests = mockApi(window, {});
  await window.openCardioPresetEditor();
  inputFor(window, 'จำนวนก้าว (ถ้ามี)').value = '10000';
  await clickSave(window);

  const request = requests.find((item) => item.method === 'POST' && item.url.endsWith('/api/me/cardio-presets'));
  assert.ok(request);
  assert.equal(request.body.activity, 'เดิน');
  assert.equal(request.body.duration_min, null);
  assert.equal(request.body.steps, 10000);
});

function cardioSession({ caloriesEstimated = true, calories = 100 } = {}) {
  return {
    id: 1, type: 'cardio', name: 'เดิน', estimated_duration_min: 20,
    estimated_calories: calories, calories_estimated: caloriesEstimated,
    notes: '', exercises: [],
    cardio: { activity: 'เดิน', duration_min: 20, incline_pct: null, speed_kmh: 5, distance_km: 2, steps: null, met: 4.8 },
  };
}

test('editing automatic cardio omits old calories and sends nulls for cleared metrics', async () => {
  const window = loadDashboard();
  const requests = mockApi(window, cardioSession());
  await window.openSessionEditor(1);
  inputFor(window, 'เวลา (นาที, ถ้าทราบ)').value = '25';
  inputFor(window, 'ความเร็ว (กม./ชม.)').value = '';
  inputFor(window, 'ระยะทาง (กม.)').value = '';
  await clickSave(window);

  const request = requests.find((item) => item.method === 'PUT' && item.url.endsWith('/api/me/workout-sessions/1'));
  assert.ok(request);
  assert.equal(request.body.estimated_calories, undefined);
  assert.equal(request.body.cardio.duration_min, 25);
  assert.equal(request.body.cardio.speed_kmh, null);
  assert.equal(request.body.cardio.distance_km, null);
});

test('clearing manual calories sends null for auto while explicit zero stays manual', async () => {
  const window = loadDashboard();
  const requests = mockApi(window, cardioSession({ caloriesEstimated: false }));

  await window.openSessionEditor(1);
  inputFor(window, 'พลังงานโดยประมาณ (ลบค่าเพื่อกลับไปคำนวณอัตโนมัติ)').value = '';
  await clickSave(window);
  let request = requests.filter((item) => item.method === 'PUT').at(-1);
  assert.equal(request.body.estimated_calories, null);

  await window.openSessionEditor(1);
  inputFor(window, 'พลังงานโดยประมาณ (ลบค่าเพื่อกลับไปคำนวณอัตโนมัติ)').value = '0';
  inputFor(window, 'พลังงานโดยประมาณ (ลบค่าเพื่อกลับไปคำนวณอัตโนมัติ)').dispatchEvent(new window.Event('input', { bubbles: true }));
  await clickSave(window);
  request = requests.filter((item) => item.method === 'PUT').at(-1);
  assert.equal(request.body.estimated_calories, 0);
});

test('cycling can save outdoor distance and speed without minutes', async () => {
  const window = loadDashboard();
  const requests = mockApi(window, {});
  await window.openCardioPresetEditor();
  const activity = inputFor(window, 'กิจกรรม');
  activity.value = 'จักรยาน';
  activity.dispatchEvent(new window.Event('change', { bubbles: true }));
  inputFor(window, 'ระยะทาง (กม.)').value = '12';
  inputFor(window, 'ความเร็ว (กม./ชม.)').value = '18';
  await clickSave(window);

  const request = requests.find((item) => item.method === 'POST' && item.url.endsWith('/api/me/cardio-presets'));
  assert.equal(request.body.variant, 'outdoor_general');
  assert.equal(request.body.duration_min, null);
  assert.equal(request.body.distance_km, 12);
  assert.equal(request.body.speed_kmh, 18);
});

test('swimming editor converts entered metres to kilometres for storage', async () => {
  const window = loadDashboard();
  const requests = mockApi(window, {});
  await window.openCardioPresetEditor();
  const activity = inputFor(window, 'กิจกรรม');
  activity.value = 'ว่ายน้ำ';
  activity.dispatchEvent(new window.Event('change', { bubbles: true }));
  inputFor(window, 'เวลา (นาที, จำเป็น)').value = '30';
  inputFor(window, 'ระยะทาง (เมตร)').value = '750';
  await clickSave(window);

  const request = requests.find((item) => item.method === 'POST' && item.url.endsWith('/api/me/cardio-presets'));
  assert.equal(request.body.variant, 'general');
  assert.equal(request.body.distance_km, 0.75);
});

test('other activity keeps category separate from a colliding custom display name', async () => {
  const window = loadDashboard();
  const session = cardioSession();
  session.cardio = { ...session.cardio, activity: 'เดิน', activity_type: 'อื่นๆ', variant: 'yoga' };
  const requests = mockApi(window, session);
  await window.openSessionEditor(1);
  assert.equal(inputFor(window, 'กิจกรรม').value, 'อื่นๆ');
  assert.equal(inputFor(window, 'ชื่อกิจกรรมอื่นๆ').value, 'เดิน');
  await clickSave(window);

  const request = requests.find((item) => item.method === 'PUT');
  assert.equal(request.body.cardio.activity, 'อื่นๆ');
  assert.equal(request.body.cardio.custom_name, 'เดิน');
  assert.equal(request.body.cardio.variant, 'yoga');
});

test('strength editor preserves displayed duration on ordinary edits', async () => {
  const window = loadDashboard();
  const session = { id: 1, type: 'strength', name: 'เวท', estimated_duration_min: 30, estimated_calories: 100, calories_estimated: true, notes: '', exercises: [{ name: 'Squat', sets: 3, repetitions: 10, weight: null, notes: '' }] };
  const requests = mockApi(window, session);
  await window.openSessionEditor(1);
  await clickSave(window);

  const request = requests.find((item) => item.method === 'PUT');
  assert.equal(request.body.estimated_duration_min, 30);
  assert.ok(request.body.exercises.length);
  assert.equal(request.body.estimated_calories, undefined);
});

test('changing bike mode to swimming preserves the entered swim distance across stroke changes', async () => {
  const window = loadDashboard();
  const requests = mockApi(window, {});
  await window.openCardioPresetEditor();
  const activity = inputFor(window, 'กิจกรรม');
  activity.value = 'จักรยาน';
  activity.dispatchEvent(new window.Event('change', { bubbles: true }));
  const variant = inputFor(window, 'รูปแบบ / ระดับ');
  variant.value = 'stationary_light';
  variant.dispatchEvent(new window.Event('change', { bubbles: true }));
  activity.value = 'ว่ายน้ำ';
  activity.dispatchEvent(new window.Event('change', { bubbles: true }));
  inputFor(window, 'เวลา (นาที, จำเป็น)').value = '20';
  inputFor(window, 'ระยะทาง (เมตร)').value = '800';
  const swimVariant = inputFor(window, 'รูปแบบ / ระดับ');
  swimVariant.value = 'butterfly';
  swimVariant.dispatchEvent(new window.Event('change', { bubbles: true }));
  await clickSave(window);

  const request = requests.find((item) => item.method === 'POST' && item.url.endsWith('/api/me/cardio-presets'));
  assert.equal(request.body.distance_km, 0.8);
  assert.equal(request.body.variant, 'butterfly');
});

test('custom activity does not silently choose a named activity variant', async () => {
  const window = loadDashboard();
  mockApi(window, {});
  await window.openCardioPresetEditor();
  const activity = inputFor(window, 'กิจกรรม');
  activity.value = 'อื่นๆ';
  activity.dispatchEvent(new window.Event('change', { bubbles: true }));
  assert.equal(inputFor(window, 'รูปแบบ / ระดับ').value, '');
});

test('run preset previews pace from entered minutes and kilometres', async () => {
  const window = loadDashboard();
  mockApi(window, {});
  await window.openCardioPresetEditor();
  const activity = inputFor(window, 'กิจกรรม');
  activity.value = 'วิ่ง';
  activity.dispatchEvent(new window.Event('change', { bubbles: true }));
  const duration = inputFor(window, 'เวลา (นาที, ถ้าทราบ)');
  const distance = inputFor(window, 'ระยะทาง (กม.)');
  duration.value = '30';
  duration.dispatchEvent(new window.Event('input', { bubbles: true }));
  distance.value = '5';
  distance.dispatchEvent(new window.Event('input', { bubbles: true }));
  const preview = [...window.document.querySelectorAll('#modalSheet .section-intro')].find((element) => element.textContent.includes('เพซประมาณ'));
  assert.ok(preview);
  assert.match(preview.textContent, /6\.0 นาที\/กม\./);
  assert.equal((preview.textContent.match(/เพซประมาณ/g) || []).length, 1);
});

test('run session editor previews pace from entered minutes and kilometres', async () => {
  const window = loadDashboard();
  const session = cardioSession();
  const requests = mockApi(window, session);
  await window.openSessionEditor(1);
  const activity = inputFor(window, 'กิจกรรม');
  activity.value = 'วิ่ง';
  activity.dispatchEvent(new window.Event('change', { bubbles: true }));
  const duration = inputFor(window, 'เวลา (นาที, ถ้าทราบ)');
  const distance = inputFor(window, 'ระยะทาง (กม.)');
  duration.value = '30';
  duration.dispatchEvent(new window.Event('input', { bubbles: true }));
  distance.value = '5';
  distance.dispatchEvent(new window.Event('input', { bubbles: true }));
  const preview = [...window.document.querySelectorAll('#modalSheet .section-intro')].find((element) => element.textContent.includes('เพซประมาณ'));
  assert.ok(preview);
  assert.match(preview.textContent, /6\.0 นาที\/กม\./);
});
