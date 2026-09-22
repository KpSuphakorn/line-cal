const test = require('node:test');
const assert = require('node:assert/strict');

const {
  loadDashboard,
  exerciseList,
  fieldValue,
  typeInto,
  clickRowAction,
  names,
  plain,
} = require('./harness');

const window = loadDashboard();

function draftRows() {
  return [
    { name: 'Bench press', sets: 3, repetitions: 8, weight: 60, notes: '' },
    { name: '', sets: 3, repetitions: 10, weight: null, notes: '' },
  ];
}

test('adding an exercise keeps what the user typed into the row above it', () => {
  const rows = draftRows();
  const list = exerciseList(window, rows);
  typeInto(list, 1, { name: 'Incline dumbbell press', sets: 4, notes: 'เอียง 30 องศา' });

  window.editExercises(rows, list, true, () =>
    rows.push({ name: '', sets: 3, repetitions: 10, weight: null, notes: '' }),
  );

  assert.equal(list.querySelectorAll('.exercise').length, 3);
  assert.equal(fieldValue(list, 1, 'name'), 'Incline dumbbell press');
  assert.equal(fieldValue(list, 1, 'sets'), '4');
  assert.equal(fieldValue(list, 1, 'notes'), 'เอียง 30 องศา');
  assert.equal(fieldValue(list, 0, 'name'), 'Bench press');
});

test('deleting one exercise keeps the unsaved drafts in every other row', () => {
  const rows = draftRows();
  const list = exerciseList(window, rows);
  typeInto(list, 1, { name: 'Incline dumbbell press' });

  clickRowAction(list, 0, 'ลบท่า');

  assert.deepEqual(names(list), ['Incline dumbbell press']);
});

test('reordering carries the typed values with the row, not just its position', () => {
  const rows = draftRows();
  const list = exerciseList(window, rows);
  typeInto(list, 0, { name: 'Flat bench', weight: 62.5 });
  typeInto(list, 1, { name: 'Incline bench' });

  clickRowAction(list, 1, 'ย้ายขึ้น');

  assert.deepEqual(names(list), ['Incline bench', 'Flat bench']);
  assert.equal(fieldValue(list, 1, 'weight'), '62.5');
});

test('the reorder buttons are arrow icons that still announce themselves', () => {
  const list = exerciseList(window, draftRows());
  const first = list.querySelectorAll('.exercise')[0];
  const down = first.querySelector('[aria-label="ย้ายลง"]');

  assert.ok(down, 'first row can move down');
  assert.equal(down.textContent, '', 'icon only, no text label');
  assert.ok(down.querySelector('svg.icon'), 'renders the chevron icon');
  assert.equal(first.querySelector('[aria-label="ย้ายขึ้น"]'), null, 'first row cannot move up');
  assert.ok(
    list.querySelectorAll('.exercise')[1].querySelector('[aria-label="ย้ายขึ้น"]'),
    'second row can move up',
  );
});

test('the session editor has no reorder buttons but still protects drafts', () => {
  const rows = draftRows();
  const list = exerciseList(window, rows, { reorder: false });
  typeInto(list, 1, { name: 'Cable fly' });
  assert.equal(list.querySelectorAll('.exercise-actions button').length, 2, 'remove only');

  window.editExercises(rows, list, false, () =>
    rows.push({ name: '', sets: 3, repetitions: 10, weight: null, notes: '' }),
  );

  assert.deepEqual(names(list), ['Bench press', 'Cable fly', '']);
});

test('the save payload drops unnamed rows and trims the rest', () => {
  const rows = draftRows();
  const list = exerciseList(window, rows);
  typeInto(list, 1, { name: '  Cable fly  ', sets: 4, repetitions: 12, weight: '', notes: '  ช้าๆ  ' });

  const payload = plain(window.exercisePayload(list));

  assert.deepEqual(payload, [
    { name: 'Bench press', sets: 3, repetitions: 8, weight: 60, notes: '' },
    { name: 'Cable fly', sets: 4, repetitions: 12, weight: null, notes: 'ช้าๆ' },
  ]);
});

test('a blank row the user never filled in is not saved', () => {
  const rows = draftRows();
  const list = exerciseList(window, rows);

  assert.deepEqual(plain(window.exercisePayload(list)).map((item) => item.name), ['Bench press']);
});
