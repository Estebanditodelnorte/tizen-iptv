# Issues checklist

Written after the code review pass and the failed preflight experiment. Nothing here is
fixed unless it is ticked. Ordered by how much damage it does.

Context for anyone picking this up: the app is on a **restored known-good build** (`b0b8791`).
Several improvements made during the review were lost when that build was restored on purpose.
They are listed here rather than re-applied, because each carries risk and the regression gate
(five working channels must still play) has to be run every time.

---

## P0 — playback and hangs

- [ ] **The hang is not understood.** Evidence: watching El Chavo, pressing BACK to reach the
      tag menu froze the app; also reported "freezes after about 5 tags". A status line now
      prints the operation around each native call (`docs/PLAN-HANG.md`). **Waiting on a
      photo of the frozen line before changing any playback code.**
- [ ] **The stop path is uninstrumented in the fix sense.** `stopPlayback → cancelPending →
      AV.stop()/AV.close()` can block on a live stream, and no watchdog can save us because a
      native block freezes the thread. Nothing currently guards it.
- [ ] **One player instance is reused forever.** Every channel opens and closes the same
      `application/avplayer` object. If repeated open/close cycles wedge it (the "5 tags"
      report fits), we have no recreate strategy.
- [ ] **`hideTimer` can hide the list after a failure.** A failed channel restores nothing;
      the 4 s auto-hide from `startChannel` can still fire afterwards and hide the list, which
      looks like a freeze. *Fixed once in `82f19f3`, lost in the `b0b8791` restore.*
- [ ] **A stale open can land after the user picks another channel.** The 200 ms settle delay
      has no generation token any more. *Fixed once in `82f19f3`, lost in the restore.*
- [ ] **No way to reset the player without restarting the app.** A BACK-menu item that calls
      `stop`/`close` and clears `pendingOpen` would recover a soft freeze.

## P1 — data loss

- [ ] **Ratings are stored under one key.** A single failed or truncated `localStorage` write
      loses everything, and the TV cannot be read to recover it. *Dual-key write was in
      `6a67f67`, lost in the restore.*
- [ ] **Deleting a channel silently deletes its rating.** Every cleanup pass so far has removed
      ratings the owner gave (Teletubbies, the six MUSIC channels, nineteen KIDS ones). That is
      what "I lost some of my ratings" meant. Decide: keep an orphaned-ratings file, or warn.
- [ ] **Ratings and category moves are keyed by channel *name*, not by URL or id.** 27 names
      appear in more than one tab (`3ABN Kids` in KIDS and PUBLIC, `El Chavo TV` in KIDS and
      MEXICO, `TSN The Ocho` in CANADA and SPORTS). Rating one instance silently rates the
      other, and renaming a channel orphans its rating. Keying on URL would fix both.
- [ ] **No export path.** The only way ratings leave the TV is a photograph. `ratings.json` in
      the repo is the durable copy, and it is written by hand from those photos.

## P2 — user experience

- [x] ~~Tagging a channel bad threw the cursor to the bottom of the list.~~ Fixed in `996866a`:
      the cursor stays on the row, so the next channel is already selected.
- [x] ~~Menus were invisible: the rating panel covered only the video half.~~ Fixed earlier
      (full-screen panel).
- [ ] **The app always opens on CANADA at the top of the list.** Last tab, last channel and
      scroll position are not remembered, which is tedious on a 100-channel tab.
- [ ] **42 channels have the literal group `Undefined`** (from iptv-org). It shows as a section
      heading. Should fold into `Other`.
- [ ] **`[Not 24/7]` and `[Geo-blocked]` are only in the channel name.** A dedicated marker
      would explain at a glance why a channel is dead at 3 pm and fine at 8 pm.
- [ ] **No search.** With 456 channels across seven tabs, typing or filtering would help, but
      no key for it is delivered (see the input limitation below) — would need arrow-only UI.
- [ ] **The LIKELY BAD heuristic has never been validated.** 39 channels are sorted there by
      host; we have no feedback on whether they are actually dead. Needs the owner to say.

## P3 — tooling and repo hygiene

- [ ] **Dead code is back in the source**: the GREEN test-every-channel runner (`startTest`,
      `testStep`) and the number-key shortcuts (`NUMCATS`, `assignCat`). Neither key ever
      reaches a web app on this firmware. Removed once in `82f19f3`, restored with the build.
- [ ] **No version string in the running app.** It was added in `82f19f3` and lost. Without it
      there is no way to tell which build is on the TV — it cost a debugging cycle already.
- [ ] **Two overlapping probe tools**: `tools/deep_probe.py` and `tools/video_probe.py` both
      walk master → variant → segment. One should go.
- [ ] **`speed_probe.py` reports a misleading `kbps`.** It reads 200 KB and divides by elapsed
      time, so a fast CDN reports 20 Mbps. It says nothing about stream bitrate. Either measure
      over time or rename the column to `throughput`.
- [ ] **`apply_speed.py` hardcodes the group `Sports (slow)`.** Fine for sports, wrong for any
      other list.
- [ ] **No CI.** `tools/test_keys.js`, `tools/dump_sections.js` and `node --check` are run by
      hand. A pre-push hook would stop a broken build reaching the TV.
- [ ] **Cleanup scripts live outside the repo** (`C:\Users\Public\*.py`: remove-bad, purge,
      prune-ratings…). They are not reproducible and will be lost. Move the reusable ones into
      `tools/`.
- [ ] **Malformed channel names in the playlists.** Some `#EXTINF` lines carry a comma inside a
      user-agent attribute, so the name after the last comma is garbage (`like Gecko) …`). The
      builder handles it; anything matching on names (removal scripts, ratings) must too.
- [ ] **`tools/.feeds.json` is a cache** (gitignored). Fine, but undocumented.

---

## Lessons that are now rules

These are in `docs/NOTES.md`; repeated here because each one cost a broken build.

- **A Tizen 2.3 web app only receives arrows, OK and BACK.** Numbers and colours need
  `tv.inputdevice`, which this TV rejects at install. Any interaction must work without them.
- **HTTP 200, a valid manifest and a passing probe do not mean playable.** The only signal that
  matters is a video elementary stream the TV's decoder accepts.
- **AES-128 is unplayable here.** It is not "DRM" in the usual sense — the TV simply cannot
  decrypt it. This is why every `jmp2.uk/plu-…` (Pluto) channel is dead weight.
- **A preflight must never reject a playable stream.** Tried in `acb6981`, broke working
  channels, reverted in `d2a87f3`. Do not re-add without a way to prove it.
- **Rendering is not input.** A page that draws perfectly can have a dead key handler; only
  `tools/test_keys.js` catches that.
- **Restarting the app is the accepted workaround** for a wedged decoder. Prefer it over
  trading away channels that work.

## Open questions for the owner

- [ ] Are the 39 LIKELY BAD channels actually dead, or do some play?
- [ ] Does the app freeze on the **5th tag** or the **5th play/stop cycle**? Different bugs.
- [ ] Would you rather keep a channel's rating when it is removed from the list, or lose it?
