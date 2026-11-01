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

## Current state of the app

- Package `IPTVPlayer`, app id `IPTVPlayer.App`, name **IPTV**, sideloaded and working.
- **v1.9.0 plays video** â€” the fixes were the `webapis.js` include, the
  `object[type=application/avplayer]` surface sized to `setDisplayRect`, and transparent
  `html`/`body` while playing.
- Channel list parsed from `https://iptv-org.github.io/iptv/countries/ca.m3u`
  (265 channels, `C:\Users\Public\iptv\ca.m3u`).
- **All 265 URLs probed from the laptop**; 216 answered HTTP 200 with an HLS content type.
  The app is built from the validated subset (`ca-working.m3u`, `probe-report.json` holds the
  per-channel result). Every working stream is HLS (`.m3u8`) â€” no MPEG-TS or DASH in the list.
- Builders: `C:\Users\Public\build-iptv-app9.py` (current), earlier ones kept for reference.
- Layout: channel list on the left, video in the right pane; list auto-hides 4 s into playback,
  any key brings it back, BACK stops.
- Chasing any remaining per-channel failures: it is now stream-side (geo-blocked segment,
  DRM, or a codec the 2015 decoder lacks), not the app.

## Untested / useful next steps

- AVPlay with the `webapis.js` include (the fix in progress).
- If HLS still fails: check `getState()`/`getCodecInfo()` and surface the error name.
- Tizen 2.3 answers the Web Inspector on port 7011 (one WebSocket per launch) â€” a real
  debugging channel for console errors, unlike SDB.
- Fallback if AVPlay stays unstable: install **SS IPTV** from the Samsung store and register
  the device on `ss-iptv.com` â€” it is built for these panels and uses AVPlay correctly.

