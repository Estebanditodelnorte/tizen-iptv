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

const rated = () => Object.values(stored('iptv-rate'))[0];

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
  if (Object.keys(stored('iptv-rate')).length !== 0) throw new Error('rating not cleared');
});
step('Cancel changes nothing', () => {
  const before = JSON.stringify(stored('iptv-rate'));
  press(10009); press(40); press(40); press(40); press(40); press(13);
  if (JSON.stringify(stored('iptv-rate')) !== before) throw new Error('cancel changed state');
});
step('OK plays without throwing', () => press(13));
step('BACK stops playback', () => press(10009));
step('RIGHT switches list', () => press(39));
step('LEFT switches back', () => press(37));

console.log(failures === 0 ? '\nall checks passed' : '\n' + failures + ' checks failed');
process.exit(failures === 0 ? 0 : 1);
