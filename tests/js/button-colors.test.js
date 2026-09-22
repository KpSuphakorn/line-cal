const test = require('node:test');
const assert = require('node:assert/strict');

const { loadDashboard } = require('./harness');

test('creating a program and creating a cardio preset are the same flow, so their buttons must match', () => {
  const window = loadDashboard();
  window.renderPrograms();

  const root = window.document.getElementById('programsRoot');
  const createProgram = [...root.querySelectorAll('button')].find((b) => b.textContent === 'สร้างโปรแกรม');
  const createPreset = [...root.querySelectorAll('button')].find((b) => b.textContent === 'สร้างรายการคาร์ดิโอ');

  assert.ok(createProgram, 'สร้างโปรแกรม button renders');
  assert.ok(createPreset, 'สร้างรายการคาร์ดิโอ button renders');
  assert.equal(createProgram.className, createPreset.className);
});
