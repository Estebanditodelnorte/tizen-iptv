// Load the built app's script with a stub DOM and fire remote keys at it.
// Catches the class of bug that broke navigation: an undeclared variable throwing
// on the first keypress, which a rendered-DOM check cannot see.
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
let keyHandler = null;
const store = {};

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

const presses = [40, 40, 38, 39, 37, 406, 40, 40, 13, 10009, 406, 10009, 404];
let failures = 0;
for (const keyCode of presses) {
  try {
    keyHandler({ keyCode, preventDefault() {} });
  } catch (e) {
    failures++;
    console.log('FAIL on keyCode ' + keyCode + ': ' + e.message);
  }
}
console.log(failures === 0 ? 'all ' + presses.length + ' keypresses handled without throwing'
                           : failures + ' keypresses threw');
process.exit(failures === 0 ? 0 : 1);
