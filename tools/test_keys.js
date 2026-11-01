// Load the built app's script with a stub DOM and drive it with remote keys.
// Catches bugs a rendered-DOM check cannot see, e.g. an undeclared variable throwing on the
// first keypress, or tagging that silently writes nothing.
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('C:/Users/Public/iptv-repo/app/index.html', 'utf8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
const code = scripts[scripts.length - 1][1];

function El() {
  this.style = {};
  this.className = '';
  this.children = [];
  this.textContent = '';
  this.innerHTML = '';
  this.offsetTop = 0;
  this.offsetHeight = 20;
  this.scrollTop = 0;
  this.clientHeight = 100;
  this.attributes = {};
}
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function (k, v) { this.attributes[k] = v; };
El.prototype.getAttribute = function (k) { return this.attributes[k]; };
El.prototype.querySelector = function () { return null; };
El.prototype.removeAttribute = function () {};
// innerHTML must actually clear children, or repeated renders accumulate headers
Object.defineProperty(El.prototype, 'innerHTML', {
  get() { return this._html || ''; },
  set(v) { this._html = v; this.children.length = 0; },
});

const elements = {};
const store = {};
let keyHandler = null;

const sandbox = {
  document: {
    getElementById(id) { return elements[id] || (elements[id] = new El()); },
    createElement() { return new El(); },
    addEventListener(type, fn) { if (type === 'keydown') keyHandler = fn; },
    documentElement: new El(),
    body: new El(),
  },
  window: { innerWidth: 1920, innerHeight: 1080 },
  localStorage: {
    getItem(k) { return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; },
    setItem(k, v) { store[k] = String(v); },
  },
  setTimeout, clearTimeout, console, JSON, Math, Date,
};
sandbox.window.webapis = undefined;
vm.createContext(sandbox);
vm.runInContext(code, sandbox, { filename: 'app.js' });

if (!keyHandler) { console.log('FAIL: no keydown handler registered'); process.exit(1); }

const press = (k) => keyHandler({ keyCode: k, preventDefault() {} });
const stored = (k) => { try { return JSON.parse(store[k] || '{}'); } catch (e) { return {}; } };
let failures = 0;
function step(label, fn) {
  try { fn(); console.log('ok   ' + label); }
  catch (e) { failures++; console.log('FAIL ' + label + ': ' + e.message); }
}

step('navigate down twice', () => { press(40); press(40); });
step('digit 3 assigns Kids', () => {
  press(51);
  if (Object.values(stored('iptv-cat')).indexOf('Kids') === -1) throw new Error('no Kids mapping stored');
});

function selectedName() {
  const sel = elements['items'].children.find((c) => c.className === 'ch sel');
  return sel ? sel.textContent.replace(/^[^A-Za-z0-9]+/, '') : '';
}
const rated = () => stored('iptv-rate')[selectedName()];

step('BACK + OK rates Very good', () => {
  press(10009); press(13);
  if (rated() !== 3) throw new Error('expected rating 3, got ' + rated());
});
step('BACK + DOWN + OK rates Good', () => {
  press(10009); press(40); press(13);
  if (rated() !== 2) throw new Error('expected rating 2, got ' + rated());
});
step('BACK + DOWN x2 + OK rates Bad', () => {
  press(10009); press(40); press(40); press(13);
  if (rated() !== 1) throw new Error('expected rating 1, got ' + rated());
});
step('BACK + DOWN x3 + OK clears the rating', () => {
  press(10009); press(40); press(40); press(40); press(13);
  if (rated() !== 0) throw new Error('expected 0, got ' + rated());
});
step('Cancel changes nothing', () => {
  const name = selectedName();
  const before = stored('iptv-rate')[name];
  press(10009); press(40); press(40); press(40); press(40); press(13);
  if (stored('iptv-rate')[name] !== before) throw new Error('cancel changed state');
});
step('OK plays without throwing', () => press(13));
step('BACK stops playback', () => press(10009));
step('RIGHT switches list', () => press(39));
step('LEFT switches back', () => press(37));
step('rating puts a VERY GOOD section first', () => {
  press(10009); press(13);                       // rate the highlighted channel very good
  const heads = elements['items'].children
    .filter((c) => c.className === 'grp')
    .map((c) => c.textContent);
  if (heads[0] !== '\u2605\u2605 VERY GOOD') throw new Error('first section is ' + heads[0]);
});
step('sections follow SECTION_ORDER', () => {
  const heads = elements['items'].children
    .filter((c) => c.className === 'grp')
    .map((c) => c.textContent);
  const music = heads.indexOf('Music');
  const good = heads.indexOf('\u2605 GOOD');
  const bad = heads.indexOf('\u2717 BAD');
  if (music !== -1 && good !== -1 && music > good) throw new Error('Music should precede GOOD');
  if (bad !== -1 && bad !== heads.length - 1) throw new Error('BAD should be last');
});

console.log(failures === 0 ? '\nall checks passed' : '\n' + failures + ' checks failed');
process.exit(failures === 0 ? 0 : 1);
