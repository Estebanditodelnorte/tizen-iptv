// Print the section headers the app renders in each tab, using the same stub DOM.
const fs = require('fs');
const vm = require('vm');

const html = fs.readFileSync('C:/Users/Public/iptv-repo/app/index.html', 'utf8');
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
const code = scripts[scripts.length - 1][1];

function El() { this.style = {}; this.className = ''; this.children = []; this.textContent = ''; this._html = '';
  this.offsetTop = 0; this.offsetHeight = 20; this.scrollTop = 0; this.clientHeight = 100; this.attributes = {}; }
El.prototype.appendChild = function (c) { this.children.push(c); return c; };
El.prototype.setAttribute = function (k, v) { this.attributes[k] = v; };
El.prototype.querySelector = function () { return null; };
El.prototype.removeAttribute = function () {};
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
    addEventListener(t, fn) { if (t === 'keydown') keyHandler = fn; },
    documentElement: new El(), body: new El(),
  },
  window: { innerWidth: 1920, innerHeight: 1080 },
  localStorage: { getItem(k) { return store[k] || null; }, setItem(k, v) { store[k] = String(v); } },
  setTimeout, clearTimeout, console, JSON, Math, Date,
};
sandbox.window.webapis = undefined;
vm.createContext(sandbox);
vm.runInContext(code, sandbox, { filename: 'app.js' });

const press = (k) => keyHandler({ keyCode: k, preventDefault() {} });
const headers = () => elements['items'].children.filter((c) => c.className === 'grp').map((c) => c.textContent);

const tabs = ['CANADA', 'MEXICO', 'SPORTS', 'PUBLIC', 'KIDS', 'LEARN', 'MUSIC'];
for (const name of tabs) {
  const heads = headers();
  const counts = heads.map((h) => {
    const start = elements['items'].children.indexOf(
      elements['items'].children.find((c) => c.className === 'grp' && c.textContent === h));
    return h;
  });
  console.log(name.padEnd(7) + ': ' + heads.join(' | '));
  press(39); // next tab
}
