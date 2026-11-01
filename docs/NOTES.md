# IPTV on Samsung UN55JU6800 â€” project memory

Everything learned building a sideloadable IPTV player for a 2015 Samsung TV. Written after
several failed iterations so the next attempt starts from facts, not guesses.

## The TV

| | |
|---|---|
| Model | Samsung UHD (2015) / Tizen 2.3 |
| Platform | Tizen 2.3.0, msf `2.0.25`, sdbd `2.2.17` |
| Panel | 1920Ã—1080, 11 years old, ~1.5 GB RAM |
| IP | `192.168.x.x` (Wi-Fi, BSSID `<ap-bssid>`) |
| DUID | `<your-tv-duid>` (from `:8001/api/v2/`) |
| API | `http://192.168.x.x:8001/api/v2/` |

## Hard constraints discovered

1. **Developer Mode whitelists one IP.** Host PC IP must equal the laptop's current address.
   The laptop is pinned to `192.168.x.x` because the TV still holds that value. If the
   laptop's IP changes, SDB connects at TCP level then closes with zero bytes.
2. **SDB on Tizen 2.3 accepts only three commands**: `0 vd_appinstall`, `0 vd_appuninstall`,
   `0 was_execute`. Everything else is refused (`ls`, `cat`, `vd_applist`, `was_applist`).
   No shell, no app-data access, no way to edit an app's settings remotely.
3. **Package name must be â‰¥ 10 characters.** `IPTVPlay` (8) fails instantly with
   `PKGMGR_ERROR` and no progress bar. `FreeMyTVio` (10) and `IPTVPlayer` (10) work.
4. **Changed manifest cannot be installed as an update.** Uninstall first, then install.
   `install.py --uninstall` or `0 vd_appuninstall <package>`.
5. **Running app blocks its own update** â€” `ConnectionResetError` or a silent
   `install failed`. Close the app (Home) before installing.
6. **`/opt/usr/apps/tmp` accumulates pushed `.wgt` files.** Every failed install still leaves
   one. Reuse a single remote filename, or truncate by re-pushing zero bytes to the same path.
7. **TV privileges (`tv.inputdevice`, `application.launch`, `tv.window`,
   `network.public`) are rejected** on this set â€” `PKGMGR_ERROR`. Adding
   `<tizen:setting ... hwkey-event="enable"/>` and `<access origin="*">` IS accepted.
   The TV permits a package without those privileges, and after the TV was signed into a
   Samsung account apps could even be launched, so the privileges turned out unnecessary.
8. **Partner-level Samsung certificates are useless here**: issued by
   `VD DEVELOPER Partner CA Class`, a chain 2015 firmware does not trust â€” even a minimal
   package was refused.

## The one that matters for video

**AVPlay requires `<script src="$WEBAPIS/webapis/webapis.js"></script>` in index.html.**
Without it `webapis.avplay` is `undefined`, code falls through to the HTML5 `<video>`
element, and HLS streams then play **audio with no picture**. Verified against
[the AVPlay API docs](https://developer.samsung.com/smarttv/develop/api-references/samsung-product-api-references/avplay-api.html).

**AVPlay also needs a DOM surface to bind to:**
`<object id="avplay-surface" type="application/avplayer" style="position:absolute;top:0;left:0;
width:1920px;height:1080px;background:transparent;pointer-events:none;">`
as the **first child of `<body>`**, created once (the API is a singleton â€” a second object
element sends video to the wrong one) and **resized to track every `setDisplayRect`**. Without
it: sound, no picture. Source: [shayanline/OpenIPTV `src/services/player.ts`](https://github.com/shayanline/OpenIPTV/blob/master/src/services/player.ts), whose comment explains that the
picture lands on a hardware plane *underneath* the browser and the page is "punched through
with a transparent hole" â€” so **every** element from `<html>` down over the video area must be
transparent. An opaque background anywhere in the chain hides the picture while the audio
plays on.

Other AVPlay rules on Tizen 2.3:

- `open(url)` â†’ `setDisplayRect(x, y, w, h)` â†’ `setListener` â†’ `prepareAsync` â†’ `play()`.
- The player draws on a **separate plane below the web view**. The page must be
  **transparent** where the video should appear â€” an opaque `body` background hides it.
  Give panels around the video their own opaque background instead.
- `setDisplayRect` can be called again during playback to move/resize (used for the split view).
- The decoder crashes the whole app on streams it cannot handle; JavaScript cannot catch that.

## Network facts

- TV â†” laptop: **laptop â†’ TV works** (ping 4 ms, port 8001, SDB). **TV â†’ laptop does not**:
  the TV browser reports "Server not found" against `http://192.168.x.x:PORT/...`, and the
  local HTTP server logs no request. Cause included the laptop's hardening rule
  **`Local Device Shield - Block LAN Inbound`**, which overrides allow rules; even with it
  disabled the TV browser still could not fetch. Do not rely on serving files from the laptop.
- Internet from the TV works (YouTube plays, `:8001` API reachable), but GitHub Pages
  over HTTPS failed inside OttPlayer ("no data received"). Baking the playlist into the app
  avoids all of this.

## Signing pipeline (works, used repeatedly)

```
# sign (WSL): cert password read via PTY, profile password left blank
python3 /mnt/c/Users/Public/sign.py /mnt/c/Users/Public/<appdir> /tmp/out<X>

# install
python3 /mnt/c/Users/Public/install_pkg.py "<wgt>" <PackageName> probe.wgt

# uninstall
python3 /mnt/c/Users/Public/uninstall-iptv.py     # package IPTVPlayer
```

- Cert: self-signed Tizen author cert in `~/tizen-studio-data/certificate/author.p12`
  (password blank in profile, answered through a PTY). Samsung partner cert is NOT needed.
- `tizen package`, not `build.py --sign`, is what produced the packages.

## Current state of the app (v2.1.0, the rebuilt player)

- Package `IPTVPlayer`, app id `IPTVPlayer.App`, sideloaded and working.
- Seven baked-in tabs: CANADA, MEXICO, SPORTS, PUBLIC, KIDS, LEARN, MUSIC (~455 channels).
  Playlists live in `playlists/*.m3u`, the app is generated from them by `tools/build.py`.
- Every channel passed a video check before shipping (see `tools/video_probe.py`).
- Navigation: arrows move and switch lists, OK plays, BACK tags. No numbers, no colours.
- Tagging is a three-level rating plus category moves, stored on the TV.
- `playlists/ratings.json` ships ratings that survive a rebuild and reach other copies.

- **Removed as unreachable**: the GREEN "test every channel" runner and the number-key
  category shortcuts. Both depended on keys this TV never delivers to a web app, so they were
  dead code that looked like a feature. Tagging is BACK only.
- The running version is printed at the end of the hint line (`v2.1.0`), because a sideloaded
  app otherwise gives no way to tell which build is on the TV.

## Remote input: what a Tizen 2.3 web app actually receives

This cost the most time. **Only arrows, OK and BACK are delivered** to a web app on this
firmware. Number keys and the colour buttons (red/green/yellow/blue) never reach `keydown`;
they are consumed by the platform. Registering them needs `tizen.tvinputdevice.registerKey`
and the **`tv.inputdevice` privilege**, which this TV **rejects at install** with
`PKGMGR_ERROR` (the same wall as the short-package-name error).

Worse, `e.keyCode` for an unregistered key never arrives at all, so there is nothing to
feature-detect. Design every interaction on arrows + OK + BACK, and treat colour/number
shortcuts as optional extras that may silently do nothing.

| Key | keyCode |
|---|---|
| Left / Right / Up / Down | 37 / 39 / 38 / 40 |
| OK / Enter | 13 (also 415) |
| Back | 10009 |
| Red / Green / Yellow / Blue | 403 / 404 / 405 / 406 (usually never delivered) |

## Why channels are "bad" — the taxonomy

Reachability is nearly worthless as a predictor. HTTP 200 and a valid manifest mean nothing
if the TV cannot decode or cannot authenticate. Ranked by how often it bit us:

1. **HLS AES-128 encryption.** Tizen 2.3 cannot decrypt it, so every Pluto-backed channel
   (`jmp2.uk/plu-...`) plays as nothing. This removed 108 channels in one pass (KIDS 156→84).
2. **Ad-stitched FAST channels (SSAI).** Hosts: `wurl.tv`, `getpublica.com`,
   `otteravision.com`, `jwp.services`, `jmp2.uk`, plus many `*.amagi.tv`. The manifest is
   public but segment URLs are personalised per session, so probes look fine and the TV
   stalls. This is the single biggest source of "it answered but shows nothing".
3. **ECDSA server certificates.** 2015 firmware generally cannot validate them
   (TELE 6 via `bozztv.com`). RSA everywhere else.
4. **Leaf-only certificate chains.** Server sends one cert and no intermediate; browsers
   fetch the issuer via AIA, old firmware does not. Suspected for Imagen TV
   (`otteravision.com`), which is otherwise a clean H.264 stream.
5. **Geo-locked US feeds.** `livestream.pbskids.org`, some `cloudfront.net` fronts. Manifest
   serves, segments do not.
6. **Timeouts / dead hosts.** Genuinely gone; the shakedown probe catches these.

What does **not** correlate: advertised bitrate (a 5.0 Mbps channel works while a 4.5 Mbps
one fails) and TLS availability (almost all of them negotiate TLS 1.2 happily).

Working rule of thumb: **plain broadcaster HLS plays; ad-tech FAST channels and US
geo-locked feeds do not.**

## Probing: the mistakes that produced false results

Each of these once caused a wrong decision, so they are worth re-reading before writing
another probe.

- **`HTTP 200` is not "playable".** The only trustworthy signal is a decoded video
  elementary stream: TS → PAT → PMT → stream type 0x1b/0x24/0x02/0x10.
- **Follow redirects before resolving relative segment URIs.** Using the original URL as the
  base produced phantom `http_414` failures for `jmp2.uk` and Pluto links.
- **AES-128 is not DRM.** The player decrypts AES-128; only SAMPLE-AES / Widevine /
  PlayReady are real DRM. Treating AES-128 as DRM hid real information.
- **Skip audio-only renditions when choosing a variant.** Some masters list an audio-only
  variant at the lowest bandwidth; picking it makes a healthy channel look audio-only.
- **TS parsing needs payload-start and adaptation-field handling.** A naive parser that
  bails on the first PID-0 packet reports "no PMT" for perfectly good streams (CityNews).
- **Measure throughput honestly.** Reading a fixed 200 KB off a fast CDN reports 20 Mbps,
  which says nothing about the stream. Use the manifest's `BANDWIDTH` for bitrate and treat
  a timed read as a rough idea only.
- **Probe from the TV's network.** Numbers are only as good as the machine running them.

## Testing the app itself

- `node tools/test_keys.js` loads the built script against a stub DOM and fires real remote
  key sequences at it. It exists because a rendered-HTML check proves nothing about the key
  path: an undeclared variable made every keypress throw `ReferenceError` while the list
  still rendered perfectly in headless Chrome.
- The stub must clear `children` on `innerHTML` assignment, or repeated renders accumulate
  headers and ordering assertions become meaningless.
- `node --check` on the extracted script catches syntax errors before an install cycle.
- `node tools/dump_sections.js` prints the section order per tab — the fastest way to see an
  ordering regression.
- Install fails with `ConnectionResetError` / `RESULT: FAILED` when the app is running on
  the TV. Close it and retry; there is no remote "kill".

## Ordering and tagging model

- `SECTION_ORDER` in `tools/build.py` is the whole layout, in one line:
  `['V3', 'Music', 'Kids', 'News', 'Sports', 'V2', 'Religious', '*', 'FRAGILE', 'V1']`.
  `V3/V2/V1` are the ratings; `*` expands to the remaining categories in first-appearance
  order.
- iptv-org writes **compound categories** (`Animation;Kids;Religious`). Each entry collapses
  to the first token matching a known section, and inside a tab that tab's own category wins
  (so `Kids;Sports` in SPORTS files under Sports).
- `FRAGILE` is the **LIKELY BAD** section: channels whose host matches
  `tools/fragile_hosts.txt` are sorted there (just above BAD) instead of being deleted. They
  are still playable — several are — so the user can rate one up and it leaves the section.
  Measured 39 of 456 channels when the list was written: MEXICO 6, SPORTS 21, PUBLIC 2,
  KIDS 9, CANADA 1. Nothing is removed on a host guess alone.

- Ratings live in the TV's `localStorage`. **There is no way to read them remotely**: SDB
  only installs/uninstalls/launches, app data is sandboxed, and the TV cannot reach a server
  on the laptop. The working sync is: the user photographs the list, the ratings are written
  into `playlists/ratings.json`, and they ship with the next build. Clearing a rating is
  stored as `0` so a baked-in default cannot come back.
- `ratings.json` is the durable artefact. TV state is disposable; the repo is the memory.

## Untested / useful next steps

- Tizen 2.3 answers the Web Inspector on port 7011 (one WebSocket per launch) — a real
  debugging channel, and the one plausible way to read `localStorage` remotely.
- A "FRAGILE" section for channels on SSAI/geo hosts, so they sort out of the way without
  being deleted.
- Virtualise the list if long tabs still feel slow on 1.5 GB of RAM.
- Fallback if AVPlay stays unstable: **SS IPTV** from the Samsung store, registered at
  `ss-iptv.com` — built for these panels and uses AVPlay correctly.
