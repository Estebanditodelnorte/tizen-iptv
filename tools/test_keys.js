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
const fake = { opens: 0, stops: 0, closes: 0, fail: true };
sandbox.webapis = {
  avplay: {
    open() { fake.opens++; },
    setListener() {},
    prepareAsync(onOk, onErr) {
      setTimeout(function () {
        if (fake.fail) { if (onErr) onErr({ name: 'stub_fail' }); }
        else if (onOk) onOk();
      }, 20);
    },
    play() {},
    stop() { fake.stops++; },
    close() { fake.closes++; },
    setSelectTrack() {},
    setDisplayRect() {},
    getState() { return 'IDLE'; },
  },
};
sandbox.window.webapis = sandbox.webapis;
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

function selectedName() {
  const sel = elements['items'].children.find((c) => c.className === 'ch sel');
  return sel ? sel.textContent.replace(/^[^A-Za-z0-9]+/, '') : '';
}
const rated = () => stored('iptv-rate')[selectedName()];

step('BACK + OK rates Very good', () => {
  const name = selectedName();
  press(10009); press(13);
  if (stored('iptv-rate')[name] !== 3) throw new Error('expected 3, got ' + stored('iptv-rate')[name]);
});
step('cursor stays put after a rating', () => {
  const before = selectedName();
  press(10009); press(40); press(40); press(13);   // rate bad: would have jumped to BOTTOM
  const after = selectedName();
  if (before === after) throw new Error('cursor followed the channel instead of staying');
});
step('BACK + DOWN + OK rates Good', () => {
  const name = selectedName();
  press(10009); press(40); press(13);
  if (stored('iptv-rate')[name] !== 2) throw new Error('expected 2, got ' + stored('iptv-rate')[name]);
});
step('BACK + DOWN x3 + OK clears the rating', () => {
  const name = selectedName();
  press(10009); press(40); press(40); press(40); press(13);
  if (stored('iptv-rate')[name] !== 0) throw new Error('expected 0, got ' + stored('iptv-rate')[name]);
});
step('Cancel changes nothing', () => {
  const name = selectedName();
  const before = stored('iptv-rate')[name];
  press(10009); press(40); press(40); press(40); press(40); press(13);
  if (stored('iptv-rate')[name] !== before) throw new Error('cancel changed state');
});
step('menu can move a channel into a category', () => {
  const name = selectedName();
  press(10009);                       // open menu
  for (let i = 0; i < 5; i++) press(40);   // past ratings, header row, onto first category
  press(13);
  const moved = stored('iptv-cat')[name];
  if (!moved) throw new Error('no category recorded for ' + name);
  if (stored('iptv-rate')[name]) throw new Error('rating should be cleared by a move');
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

// async: the post-stop cooldown, the token, then the failure path
(async () => {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));

  await wait(1500);                       // let any cooldown from the sync steps expire

  // 1. a normal open
  fake.opens = 0;
  press(13);
  await wait(600);
  if (fake.opens === 1) console.log('ok   one press opens one channel');
  else { console.log('FAIL expected 1 open, saw ' + fake.opens); failures++; }

  // 2. switch straight from one channel to another while the first is still open
  //    (this is the o2 / s0 case that hung on the TV: no BACK was ever pressed)
  fake.fail = false;                     // first channel is genuinely playing
  await wait(1500);                      // let any pending cooldown expire
  const closesBefore = fake.closes;
  press(13);
  await wait(700);                       // opens and prepares successfully
  fake.opens = 0;
  press(13);                             // switch channel without pressing BACK
  await wait(300);
  const duringSwitch = fake.opens;
  await wait(1400);
  const afterSwitch = fake.opens;
  fake.fail = true;
  if (duringSwitch === 0) console.log('ok   channel-to-channel switch is deferred');
  else { console.log('FAIL switch opened immediately (' + duringSwitch + ')'); failures++; }
  if (afterSwitch === 1) console.log('ok   switched channel opened once');
  else { console.log('FAIL switch opened ' + afterSwitch + ' times'); failures++; }
  if (fake.closes === closesBefore) console.log('ok   switching does not close the player');
  else { console.log('FAIL switch closed the player ' + (fake.closes - closesBefore) + ' times'); failures++; }

  // 3. stop, then press OK immediately: the open must be deferred, not dropped
  press(10009);
  await wait(30);
  fake.opens = 0;
  press(13);
  await wait(300);
  if (fake.opens === 0) console.log('ok   open deferred inside the cooldown');
  else { console.log('FAIL open fired inside the cooldown (' + fake.opens + ')'); failures++; }

  await wait(1500);
  if (fake.opens === 1) console.log('ok   deferred open ran exactly once');
  else { console.log('FAIL expected 1 deferred open, saw ' + fake.opens); failures++; }

  // 4. the failure path still reports and marks
  const msg = elements['msg'].textContent || '';
  if (msg.indexOf('Cannot open stream') !== -1 || msg.indexOf('No response') !== -1) {
    console.log('ok   failure reported to the user');
  } else {
    console.log('FAIL failure not reported (msg=' + JSON.stringify(msg) + ')');
    failures++;
  }

  if (elements['panel'].style.display === '-webkit-box') console.log('ok   list still visible after failure');
  else { console.log('FAIL list disappeared after failure'); failures++; }

  process.exit(failures === 0 ? 0 : 1);
})();
