# Read this first

This repo builds a sideloaded IPTV player for a **2015 Samsung TV (Tizen 2.3)**. Most of the
design looks strange until you know the two walls below; they were learned the expensive way.
Full detail, including every bug that produced a wrong answer, is in **`docs/NOTES.md`** —
read it before changing anything.

## Non-negotiable facts

1. **A Tizen 2.3 web app only receives arrows, OK and BACK.** Number keys and the colour
   buttons never reach `keydown` unless the app calls `tizen.tvinputdevice.registerKey`,
   which needs the `tv.inputdevice` privilege that this TV *rejects at install*. Never design
   an interaction that depends on those keys, and never "fix" one by assuming the key arrives.
2. **HTTP 200 does not mean playable.** Verify a video elementary stream (TS → PAT → PMT →
   0x1b/0x24/0x02/0x10) or an fMP4 `vide` handler. Channels fail on this TV in this order:
   AES-128 HLS (Tizen cannot decrypt it), ad-stitched FAST hosts (`wurl.tv`,
   `getpublica.com`, `otteravision.com`, `jwplayer`, `jmp2.uk`, `*.amagi.tv`), ECDSA
   certificates, leaf-only certificate chains, US geo-locks. Bitrate and TLS availability do
   **not** predict failure.
3. **The TV's state cannot be read remotely.** SDB installs, uninstalls and launches; nothing
   else. Ratings the user makes on the TV come back as a photo, and are written into
   `playlists/ratings.json`. The repo is the memory; the TV is disposable.
4. **An install fails while the app is running.** `ConnectionResetError` / `RESULT: FAILED`
   means close the app on the TV and retry.

## Before you ship a build

```bash
python3 tools/build.py
node tools/test_keys.js      # drives the built script with real remote keys
node tools/dump_sections.js  # prints the section order per tab
node --check <extracted script>   # catches syntax errors before a sign/install cycle
```

`tools/test_keys.js` exists because a rendered-HTML check proves nothing: an undeclared
variable once broke every keypress while the list still rendered perfectly.
