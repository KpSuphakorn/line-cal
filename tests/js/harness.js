/**
 * Loads the real dashboard.html into jsdom so the Web App's own functions can
 * be exercised, rather than a copy of them that could drift from the page.
 *
 * `init()` runs on load and immediately awaits liff.init(), so the stubs below
 * hand it a promise that never settles: the page stops before it touches the
 * network and every helper it defined is still reachable on `window`.
 */
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const DASHBOARD = path.join(__dirname, '..', '..', 'app', 'templates', 'dashboard.html');

function loadDashboard() {
  const html = fs
    .readFileSync(DASHBOARD, 'utf8')
    // The LIFF SDK is a remote script; the stub in beforeParse stands in for it.
    .replace(/<script[^>]*\ssrc=[^>]*><\/script>/g, '');

  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    url: 'https://example.test/webapp',
    beforeParse(window) {
      window.liff = {
        init: () => new Promise(() => {}),
        isLoggedIn: () => false,
        login: () => {},
        getIDToken: () => '',
      };
      window.fetch = () => new Promise(() => {});
    },
  });

  return dom.window;
}

/** Build a detached exercise list rendered by the page's own renderer. */
function exerciseList(window, rows, { reorder = true } = {}) {
  const container = window.document.createElement('div');
  window.document.body.append(container);
  window.renderExerciseList(rows, container, reorder);
  return container;
}

/** Current on-screen value of one field in one row, as the user sees it. */
function fieldValue(container, index, key) {
  const row = container.querySelectorAll('.exercise')[index];
  return row.querySelector(`[data-field="${key}"]`).value;
}

/** Type into a row the way a user would, without saving. */
function typeInto(container, index, values) {
  const row = container.querySelectorAll('.exercise')[index];
  for (const [key, value] of Object.entries(values)) {
    row.querySelector(`[data-field="${key}"]`).value = String(value);
  }
}

/**
 * Click a row's action button by the label a user or screen reader sees, which
 * for the icon-only reorder buttons is their aria-label rather than any text.
 */
function clickRowAction(container, index, label) {
  const row = container.querySelectorAll('.exercise')[index];
  const target = [...row.querySelectorAll('.exercise-actions button')].find(
    (candidate) => candidate.textContent === label || candidate.getAttribute('aria-label') === label,
  );
  if (!target) throw new Error(`no "${label}" button on row ${index}`);
  target.click();
}

/**
 * Copy a value out of the jsdom realm.  Arrays and objects built inside the
 * page have that realm's prototypes, which deepStrictEqual rejects even when
 * the contents match.
 */
function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

function names(container) {
  return [...container.querySelectorAll('.exercise')].map(
    (row) => row.querySelector('[data-field="name"]').value,
  );
}

module.exports = { loadDashboard, exerciseList, fieldValue, typeInto, clickRowAction, names, plain };
