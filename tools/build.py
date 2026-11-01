#!/usr/bin/env python3
"""Build the IPTV widget from the playlists/ folder.

    python3 tools/build.py

Writes app/index.html and app/config.xml. Then sign and install the folder as a Tizen
web app (see README). No network access, no dependencies beyond Python 3.
"""
import json, os, re, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAYLISTS = os.path.join(ROOT, 'playlists')
APP = os.path.join(ROOT, 'app')

# tab id -> label shown on screen; playlist is playlists/<id>.m3u
TABS = [
    ('canada', 'CANADA'),
    ('mexico', 'MEXICO'),
    ('sports', 'SPORTS'),
    ('public', 'PUBLIC'),
    ('kids', 'KIDS'),
    ('learn', 'LEARN'),
    ('music', 'MUSIC'),
]

def channel_name(extinf):
    """The name is after the last quoted attribute. Splitting on the first comma breaks
    entries whose attributes contain one (http-user-agent strings do)."""
    if '"' in extinf:
        pos = extinf.rfind('"')
        if ',' in extinf[pos:]:
            return extinf[pos + 1:].split(',', 1)[-1].strip()
    return extinf.split(',', 1)[-1].strip()

def parse(path):
    channels, cur = [], {}
    for line in open(path, encoding='utf-8', errors='replace'):
        line = line.strip()
        if line.startswith('#EXTINF'):
            m = re.search(r'group-title="([^"]*)"', line)
            cur = {'group': m.group(1) if m else '', 'name': channel_name(line)}
        elif line and not line.startswith('#'):
            if cur.get('name'):
                cur['url'] = line
                channels.append(cur)
            cur = {}
    return channels

data = {}
for tab, _label in TABS:
    path = os.path.join(PLAYLISTS, tab + '.m3u')
    data[tab] = parse(path) if os.path.exists(path) else []
    print('%-8s %4d channels' % (tab, len(data[tab])))

os.makedirs(APP, exist_ok=True)
for stale in ('index.html', 'config.xml'):
    p = os.path.join(APP, stale)
    if os.path.exists(p):
        os.remove(p)

config = '''<?xml version="1.0" encoding="UTF-8"?>
<widget xmlns="http://www.w3.org/ns/widgets" xmlns:tizen="http://tizen.org/ns/widgets" id="https://example.com/iptv" version="1.0.0" viewmodes="maximized">
    <tizen:application id="IPTVPlayer.App" package="IPTVPlayer" required_version="2.3"/>
    <name>IPTV</name>
    <content src="index.html"/>
    <icon src="icon.png"/>
    <feature name="http://tizen.org/feature/screen.size.all"/>
    <tizen:profile name="tv"/>
    <tizen:privilege name="http://tizen.org/privilege/internet"/>
    <tizen:privilege name="http://developer.samsung.com/privilege/avplay"/>
    <tizen:setting screen-orientation="landscape" context-menu="disable" background-support="disable" encryption="disable" install-location="auto" hwkey-event="enable"/>
</widget>
'''
open(os.path.join(APP, 'config.xml'), 'w', encoding='utf-8').write(config)

template = r'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>IPTV</title>
<!-- Samsung product APIs. Without this webapis.avplay is undefined and only the HTML5
     <video> fallback is left, which plays HLS audio with no picture on Tizen TVs. -->
<script type="text/javascript" src="$WEBAPIS/webapis/webapis.js"></script>
<style>
  html,body{margin:0;padding:0;height:100%;width:100%;background:#0b0d12;color:#e8ecf4;
            font-family:Arial,Helvetica,sans-serif;overflow:hidden}
  /* AVPlay draws on a hardware plane UNDER the page; any opaque background hides the video. */
  html.playing,body.playing{background:transparent}
  #panel{position:absolute;top:0;left:0;bottom:0;width:44%;background:#0b0d12;z-index:5;
         display:-webkit-box;-webkit-box-orient:vertical}
  #tabs{display:-webkit-box;padding:14px 16px 8px;font-size:15px;letter-spacing:1px}
  #tips{font-size:12px;color:#5f7ba8;padding:0 16px 8px}
  .tab{padding:6px 14px;margin-right:8px;border-radius:16px;color:#7d92b5;background:#141a24}
  .tab.on{background:#2b6cf6;color:#fff}
  #items{-webkit-box-flex:1;overflow-y:auto;padding:0 20px 20px;position:relative}
  .grp{font-size:12px;color:#5f7ba8;margin:12px 0 3px;letter-spacing:1px}
  .ch{padding:7px 11px;border-radius:6px;font-size:16px;white-space:nowrap;overflow:hidden;
      text-overflow:ellipsis}
  .ch.sel{background:#2b6cf6;color:#fff}
  .ch.bad{color:#8a5a5a}
  .ch.bad.sel{background:#7a2b2b;color:#fff}
  #idle{position:absolute;top:0;left:44%;right:0;bottom:0;display:-webkit-box;
        -webkit-box-align:center;-webkit-box-pack:center;text-align:center;
        font-size:18px;color:#6d82a6;padding:0 30px;z-index:4}
  #now{position:absolute;top:12px;left:0;right:0;text-align:center;font-size:16px;color:#dfe7f5;
       text-shadow:0 1px 3px #000;z-index:6}
  #msg{position:absolute;top:44%;left:0;right:0;text-align:center;font-size:18px;color:#ffb4b4;
       padding:0 30px;z-index:6}
  #hint{position:absolute;bottom:12px;left:0;right:0;text-align:center;font-size:14px;color:#9fb3d9;
        text-shadow:0 1px 3px #000;z-index:6}
  #cat{position:absolute;top:0;left:44%;right:0;bottom:0;background:#0b0d12;z-index:9;
       display:none;padding:22px 30px;overflow-y:auto}
  #cat h2{font-size:18px;color:#9fb3d9;margin:0 0 4px}
  #cat .sub{font-size:14px;color:#5f7ba8;margin:0 0 14px}
  .cat{padding:8px 12px;border-radius:6px;font-size:17px}
  .cat.sel{background:#2b6cf6;color:#fff}
</style></head><body>
<!-- The plane AVPlay binds to. Created once; its size must track setDisplayRect. -->
<object id="avplay-surface" type="application/avplayer"
        style="position:absolute;top:0;left:0;width:1920px;height:1080px;background:transparent;pointer-events:none;"></object>
<div id="panel">
  <div id="tabs"></div>
  <div id="tips">RED / BLUE switch list &nbsp;|&nbsp; RIGHT change category &nbsp;|&nbsp; GREEN test</div>
  <div id="items"></div>
</div>
<div id="idle">Choose a channel on the left<br><br>&uarr; &darr; move &nbsp; LEFT/RIGHT switch list &nbsp; OK play</div>
<div id="now"></div><div id="msg"></div><div id="hint"></div>
<div id="cat"></div>
<script>
var SOURCES = __DATA__;
var TABS = __TABS__;
var LABELS = __LABELS__;
var tab = 0, CH = [], idx = 0, rows = [], playing = false, usingAv = false, listVisible = true, hideTimer = null;
var BAD = {}, testing = false, testIdx = 0, testTimer = null;
var connectTimer = null, pendingOpen = false;
/* category overrides chosen on the TV: channel name -> group */
var CAT = {}, CATS = [], catMode = false, catIdx = 0, catTarget = '', catTimer = null;
var items = document.getElementById('items');
var tabsEl = document.getElementById('tabs');
var panel = document.getElementById('panel');
var idle = document.getElementById('idle');
var msg = document.getElementById('msg');
var nowEl = document.getElementById('now');
var hintEl = document.getElementById('hint');
var surface = document.getElementById('avplay-surface');

var AV = null;
try { if (typeof webapis !== 'undefined' && webapis.avplay) AV = webapis.avplay; } catch (e) {}

function buildTabs() {
  tabsEl.innerHTML = '';
  for (var i = 0; i < TABS.length; i++) {
    var t = document.createElement('div');
    t.className = 'tab' + (i === tab ? ' on' : '');
    t.textContent = LABELS[TABS[i]];
    tabsEl.appendChild(t);
  }
}
function render() {
  CH = SOURCES[TABS[tab]] || [];
  idx = 0; rows = []; items.innerHTML = ''; painted = -1;
  BAD = loadBad();
  var lastGroup = null;
  for (var i = 0; i < CH.length; i++) {
    var gname = CAT[CH[i].name] || CH[i].group;
    if (gname !== lastGroup) {
      lastGroup = gname;
      var g = document.createElement('div');
      g.className = 'grp';
      g.textContent = lastGroup || 'OTHER';
      items.appendChild(g);
    }
    var d = document.createElement('div');
    d.className = 'ch';
    d.textContent = (BAD[CH[i].name] ? '\u2717 ' : '') + CH[i].name;
    items.appendChild(d);
    rows.push(d);
  }
  buildTabs(); paint();
}
var painted = -1;
/* Repaint only the two rows that changed and scroll by arithmetic. The previous version
   called scrollIntoView() on every keypress, which forces a synchronous layout of the whole
   list and hangs this engine near the bottom of a long tab. */
function paint() {
  if (painted >= 0 && rows[painted]) rows[painted].className = 'ch';
  if (!rows[idx]) return;
  rows[idx].className = 'ch sel';
  painted = idx;
  var top = rows[idx].offsetTop;
  var height = rows[idx].offsetHeight;
  var viewTop = items.scrollTop;
  var viewHeight = items.clientHeight;
  if (top < viewTop) items.scrollTop = top - 8;
  else if (top + height > viewTop + viewHeight) items.scrollTop = top + height - viewHeight + 8;
}
function applyRect() {
  var w = window.innerWidth, h = window.innerHeight;
  var x = listVisible ? Math.round(w * 0.44) : 0;
  var rw = w - x;
  if (surface) {
    surface.style.left = x + 'px'; surface.style.top = '0px';
    surface.style.width = rw + 'px'; surface.style.height = h + 'px';
  }
  if (usingAv && AV) { try { AV.setDisplayRect(x, 0, rw, h); } catch (e) {} }
}
function showList() {
  if (listVisible) return;
  listVisible = true;
  panel.style.display = '-webkit-box';
  idle.style.left = '44%';
  applyRect();
  hintEl.textContent = 'BACK stop';
}
function hideList() {
  if (!playing || !listVisible) return;
  listVisible = false;
  panel.style.display = 'none';
  idle.style.left = '0';
  applyRect();
  hintEl.textContent = 'any key: channel list   BACK: stop';
}
function stopPlayback() {
  if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; }
  cancelPending();
  playing = false; listVisible = true;
  document.documentElement.className = '';
  document.body.className = '';
  panel.style.display = '-webkit-box';
  idle.style.left = '44%';
  idle.style.display = '-webkit-box';
  nowEl.textContent = ''; msg.textContent = ''; hintEl.textContent = '';
}
/* Tear the player down safely. A stream that never reached "prepared" leaves AVPlay wedged:
   stop()/close() must be attempted anyway, and the next open() must wait a beat. */
function cancelPending() {
  if (connectTimer) { clearTimeout(connectTimer); connectTimer = null; }
  pendingOpen = false;
  if (AV) {
    try { AV.stop(); } catch (e) {}
    try { AV.close(); } catch (e) {}
  }
  usingAv = false;
}
function playAv(c) {
  cancelPending();
  usingAv = true;
  pendingOpen = true;
  msg.textContent = 'Connecting...';
  /* If the stream never answers, give up instead of waiting forever - this is what made a
     dead channel swallow every later selection. */
  connectTimer = setTimeout(function () {
    if (!pendingOpen) return;
    pendingOpen = false;
    try { AV.stop(); } catch (e) {}
    try { AV.close(); } catch (e) {}
    usingAv = false;
    msg.textContent = 'No response from this stream';
  }, 12000);
  function settled() {
    pendingOpen = false;
    if (connectTimer) { clearTimeout(connectTimer); connectTimer = null; }
  }
  try {
    AV.open(c.url);
    applyRect();
    AV.setListener({
      onbufferingstart: function () { msg.textContent = 'Buffering...'; },
      onbufferingprogress: function (p) { msg.textContent = 'Buffering ' + p + '%'; },
      onbufferingcomplete: function () { msg.textContent = ''; },
      onstreamcompleted: function () { msg.textContent = 'Stream ended'; },
      onerror: function (e) { msg.textContent = 'Stream failed (' + (e && e.name ? e.name : e) + ')'; }
    });
    AV.prepareAsync(function () {
      settled();
      msg.textContent = '';
      /* Some streams carry audio as a separate HLS rendition (EXT-X-MEDIA); older Tizen
         firmware then plays video silently. Ask for the first audio track explicitly. */
      try { AV.setSelectTrack('AUDIO', 0); } catch (e) {}
      try { AV.play(); } catch (e) { msg.textContent = 'Play error: ' + e; }
    }, function (e) {
      settled();
      msg.textContent = 'Cannot open stream (' + (e && e.name ? e.name : e) + ')';
      try { AV.close(); } catch (x) {}
      usingAv = false;
    });
  } catch (e) {
    settled();
    msg.textContent = 'AVPlay error: ' + e;
    usingAv = false;
  }
}
function startChannel() {
  var c = CH[idx];
  if (!c) return;
  cancelPending();
  playing = true;
  document.documentElement.className = 'playing';
  document.body.className = 'playing';
  idle.style.display = 'none';
  nowEl.textContent = c.name;
  hintEl.textContent = 'BACK stop';
  msg.textContent = 'Connecting...';
  /* let the previous teardown settle before opening the next one */
  setTimeout(function () { playAv(c); }, 200);
  if (hideTimer) clearTimeout(hideTimer);
  hideTimer = setTimeout(hideList, 4000);
}

function loadBad() {
  try { return JSON.parse(localStorage.getItem('iptv-bad-' + TABS[tab]) || '{}'); } catch (e) { return {}; }
}
function saveBad(o) {
  try { localStorage.setItem('iptv-bad-' + TABS[tab], JSON.stringify(o)); } catch (e) {}
}
function markBad(name, reason) {
  BAD[name] = reason || 'fail';
  saveBad(BAD);
}
/* Walk every channel in the current tab, open it, and record whether the decoder accepts it.
   This is the only test that reflects what the TV can actually play. */
function startTest() {
  if (testing) return;
  if (playing) stopPlayback();
  testing = true; testIdx = 0;
  BAD = loadBad();
  testStep();
}
function testStep() {
  if (testIdx >= CH.length) {
    testing = false;
    nowEl.textContent = ''; msg.textContent = ''; hintEl.textContent = '';
    render();
    return;
  }
  var c = CH[testIdx];
  nowEl.textContent = 'TESTING ' + (testIdx + 1) + ' / ' + CH.length;
  hintEl.textContent = c.name + '  \u2014  GREEN to stop';
  var done = false;
  function finish(ok, reason) {
    if (done) return;
    done = true;
    if (testTimer) { clearTimeout(testTimer); testTimer = null; }
    if (usingAv && AV) { try { AV.stop(); } catch (e) {} try { AV.close(); } catch (e) {} usingAv = false; }
    if (!ok) markBad(c.name, reason);
    testIdx++;
    setTimeout(testStep, 250);
  }
  testTimer = setTimeout(function () { finish(false, 'timeout'); }, 9000);
  try {
    usingAv = true;
    AV.open(c.url);
    AV.setListener({ onerror: function (e) { finish(false, (e && e.name) || 'error'); } });
    AV.prepareAsync(function () { finish(true); },
                    function (e) { finish(false, (e && e.name) || 'prepare_failed'); });
  } catch (e) {
    finish(false, 'open_failed');
  }
}

function loadCat() {
  try { return JSON.parse(localStorage.getItem('iptv-cat') || '{}'); } catch (e) { return {}; }
}
function saveCat() {
  try { localStorage.setItem('iptv-cat', JSON.stringify(CAT)); } catch (e) {}
}
function buildCats() {
  var seen = {}, i, t;
  for (t in SOURCES) {
    for (i = 0; i < SOURCES[t].length; i++) {
      if (SOURCES[t][i].group) seen[SOURCES[t][i].group] = 1;
    }
  }
  var extra = ['Kids', 'Music', 'Sports', 'News', 'Movies', 'Documentary',
               'Entertainment', 'Religious', 'Weather', 'Other'];
  for (i = 0; i < extra.length; i++) seen[extra[i]] = 1;
  CATS = [];
  for (var k in seen) CATS.push(k);
  CATS.sort();
}
/* RIGHT on a channel opens this: pick a category and the channel moves there for good. */
function openCat() {
  if (!CH[idx]) return;
  catTarget = CH[idx].name;
  catMode = true;
  catIdx = 0;
  var current = CAT[catTarget] || CH[idx].group;
  for (var i = 0; i < CATS.length; i++) if (CATS[i] === current) catIdx = i;
  if (catTimer) clearTimeout(catTimer);
  catTimer = setTimeout(closeCat, 20000);   /* never leave the picker in the way */
  renderCat();
}
function renderCat() {
  var box = document.getElementById('cat');
  var html = '<h2>' + (catTarget || '') + '</h2><div class="sub">Where should this channel go? &nbsp; OK choose &nbsp; BACK cancel</div>';
  for (var i = 0; i < CATS.length; i++) {
    html += '<div class="cat' + (i === catIdx ? ' sel' : '') + '">' + CATS[i] + '</div>';
  }
  box.innerHTML = html;
  box.style.display = 'block';
  var sel = box.querySelector('.cat.sel');
  if (sel && sel.scrollIntoView) {
    var top = sel.offsetTop, st = box.scrollTop, ch = box.clientHeight;
    if (top < st) box.scrollTop = top - 8;
    else if (top + sel.offsetHeight > st + ch) box.scrollTop = top + sel.offsetHeight - ch + 8;
  }
}
function closeCat() {
  catMode = false;
  if (catTimer) { clearTimeout(catTimer); catTimer = null; }
  document.getElementById('cat').style.display = 'none';
}
function applyCat() {
  CAT[catTarget] = CATS[catIdx];
  saveCat();
  closeCat();
  render();
  hintEl.textContent = catTarget + ' -> ' + CATS[catIdx];
}

document.addEventListener('keydown', function (e) {
  var k = e.keyCode, handled = true;
  if (catMode) {
    if (k === 38) { catIdx = Math.max(0, catIdx - 1); renderCat(); }
    else if (k === 40) { catIdx = Math.min(CATS.length - 1, catIdx + 1); renderCat(); }
    else if (k === 13 || k === 415) { applyCat(); }
    else if (k === 10009 || k === 27 || k === 8) { closeCat(); }
    else { handled = false; }
    e.preventDefault();
    return;
  }
  if (testing) {
    if (k === 404) {
      testing = false;
      if (testTimer) { clearTimeout(testTimer); testTimer = null; }
      try { AV.stop(); } catch (x) {}
      try { AV.close(); } catch (x) {}
      usingAv = false;
      nowEl.textContent = ''; hintEl.textContent = '';
      render();
    }
    e.preventDefault();
    return;
  }
  if (!listVisible) { showList(); e.preventDefault(); return; }
  if (k === 37 || k === 403) { tab = (tab + TABS.length - 1) % TABS.length; render(); }
  else if (k === 39) { tab = (tab + 1) % TABS.length; render(); }
  else if (k === 406) { openCat(); }
  else if (k === 38) { idx = Math.max(0, idx - 1); paint(); }
  else if (k === 40) { idx = Math.min(CH.length - 1, idx + 1); paint(); }
  else if (k === 13 || k === 415) { startChannel(); }
  else if (k === 404) { startTest(); }
  else if (k === 10009 || k === 27 || k === 8) { stopPlayback(); }
  else { handled = false; }
  if (handled) e.preventDefault();
});

CAT = loadCat();
buildCats();
render();
</script></body></html>
'''

ids = [t for t, _ in TABS]
labels = {t: l for t, l in TABS}
html = (template
        .replace('__DATA__', json.dumps(data, ensure_ascii=False))
        .replace('__TABS__', json.dumps(ids))
        .replace('__LABELS__', json.dumps(labels)))
open(os.path.join(APP, 'index.html'), 'w', encoding='utf-8').write(html)

total = sum(len(v) for v in data.values())
print('wrote app/index.html (%d channels, %d KB)' % (total, os.path.getsize(os.path.join(APP, 'index.html')) // 1024))
