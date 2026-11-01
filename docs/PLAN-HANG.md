# Plan: find the hang without breaking the working app

The app is on the **known-good build** (`b0b8791` + Pluto TV Zombies). Any change below must be
reversible with one commit and must not touch the playback path until step 3.

## What we know

- The hang happens **when a channel fails**, not at random. Working channels never hang.
- After a hang, the app stays frozen until it is restarted. Rebooting the TV also clears it.
- A native decoder crash **cannot be caught in JavaScript** — if `AV.open()` blocks the thread,
  no timer, `try/catch` or watchdog can run. That is why an existing 12 s watchdog does not
  save us: it never gets a chance to fire.
- A preflight XHR was tried (`acb6981`) and rejected channels that play. Reverted in
  `ae975a8`/`d2a87f3`. Whatever we do next must not repeat that.

### New evidence: the hang happens on STOP, not on OPEN

Reported: watching **El Chavo**, pressed BACK to reach the tag menu, app froze and needed a
restart. That matters, because BACK while playing runs `stopPlayback()` →
`cancelPending()` → `AV.stop()` + `AV.close()` **before** any menu opens.

So the prime suspect is no longer only `AV.open()`. `AV.close()` on a live HLS stream can
block just as easily, and step 1 must instrument both. It also explains why "it hangs when a
channel is bad" and "it hangs when I press BACK" can be the same bug seen from two sides: both
run a native call that can block.

## Hypotheses, most likely first

1. **`AV.open()` or `prepareAsync()` blocks synchronously** on a stream the decoder refuses.
   Symptoms match exactly: UI dead, no watchdog, restart needed.
2. **The player is not in a clean state** before opening (previous stream stopped but not
   closed, or an error left it in `PLAYING`), so the next open wedges it.
3. **A failure callback arrives but our handler throws**, leaving `pendingOpen` true and the
   list hidden — looks like a hang but is recoverable with BACK.
4. **Memory pressure** on ~1.5 GB after many opens, making a native call slow rather than
   blocked.

Each hypothesis has a different fix, so step 1 is measuring which one it is.


### Third report: "when I try to go too fast it hangs"

This is the most diagnostic detail so far, and it reorders the hypotheses.

Every OK press schedules `playAv(c)` **200 ms later**, with no token and no re-entrancy guard in
the shipped build (the generation token was lost in the `b0b8791` restore). Press OK three times
quickly and you get three timers, three `AV.open()` calls and three `prepareAsync()` calls into
**one** player object. The decoder is not re-entrant: that is a textbook way to wedge it.

Same shape on the other side: BACK during `prepare` runs `AV.stop()`/`AV.close()` while a prepare
is still in flight.

So the ranking becomes:

1. **Re-entrancy from rapid input** (new): overlapping open/prepare/close on a single player.
2. `AV.open()` blocking on a stream the decoder refuses.
3. Player left in a dirty state between channels.
4. Memory pressure.

The fix for (1) is small, contained, and testable without a TV:

- ignore OK while `pendingOpen` is true, or cancel the pending open cleanly first;
- restore the generation token, so only the newest scheduled open can run;
- ignore a second BACK while a stop is already in progress;
- optionally drop key repeats inside a short window (e.g. 150 ms) for OK and BACK only.

Arrows need no guard: they only repaint.


### Tried and reverted: input guards (5927285)

Added three guards: 150 ms OK repeat window, generation token so a burst collapses to one
open, and `stopPlayback()` bumping the token so a scheduled open cannot land after BACK.

**It still hung**, and the recipe was specific: **play a channel → BACK → pick another channel
quickly**. So overlapping opens were not the whole story — the failing sequence is
`stop/close` immediately followed by `open`. Guards are reverted; the working build is `948a96c`.

What that tells us:

- Rapid input is only dangerous when it produces **stop → open with almost no gap**.
- The suspect is the native transition itself: `AV.close()` on a live stream followed straight
  away by `AV.open()`. Either `close()` blocks (thread frozen, nothing helps) or it returns
  before the pipeline has actually released, and `open()` then wedges it.

Two candidate experiments, in this order:

- **A. Cooldown after stop.** Refuse a new open for about 1 s after BACK and show
  "please wait" in the hint line. Cheap, reversible, and if the hang disappears it proves the
  pipeline needs time to release. Users pressing slowly would never notice.
- **B. Stop without closing.** On BACK, call `stop()` only and keep the player object for the
  next channel. Fewer native transitions, no close/open race. Riskier: a wedged player stays
  wedged, so this needs the cooldown fallback anyway.

Still needed before either: **the status line text at the moment of the freeze**. It names
`stop:before`, `close:before` or `open:before`, which decides between "close blocks" (A is
pointless, B might help) and "open blocks" (A is the right fix).

## Step 1 — diagnostics only, zero behaviour change

Add an on-screen diagnostic panel (toggle with a key that already arrives, e.g. **BACK held on
the list**, or simplest: always show a one-line status bar):

```
state=PLAYING open#7 t=1234ms last=onbufferingstart
```

Contents: `AV.getState()` before and after each call, a counter of opens **and of stops**,
milliseconds since `open()`, and the last callback name that fired. Instrument `stopPlayback`
and `cancelPending` too — the El Chavo report points there. Nothing about the playback path changes; the
only risk is a cosmetic regression.

Also record the last 20 events in `localStorage` (`iptv-log`), so after a hang you can
photograph the screen and I can see how far it got.

**Decision this step answers:** does the hang occur before or after `prepareAsync` returns, and
does any callback fire at all?

## Step 2 — a way out without restarting (safe, additive)

Add **"Reset player"** to the BACK menu: `AV.stop()`, `AV.close()`, clear `pendingOpen`,
re-render the list. If hypothesis 2 or 3 is right, this unfreezes the app without a TV reboot
and gives us a recovery path even before the root cause is fixed.

Zero risk to working channels: it touches nothing on the normal path.

## Step 3 — only if step 1 shows hypothesis 1

The only real defence against a synchronous native block is **not calling it on a stream that
will block**. Options, in increasing risk:

- **3a. Retry once with a fresh player.** On the first failure, `close()`, recreate the player
  object, wait 500 ms, retry once. If the decoder wedges only on re-use, this removes the hang
  for the "second bad channel" case. Reversible, low risk.
- **3b. Open the lowest-bitrate variant instead of the master.** The decoder then has the
  smallest possible problem to solve. Costs a manifest fetch and URI resolution; still pure
  HLS, no new failure modes.
- **3c. Narrow preflight, used only as a tie-breaker.** Give the URL 3 s to answer; if it does
  not, treat it as dead *and only then* skip AVPlay. The earlier attempt failed because it
  rejected on status codes and opaque replies — 3c must ignore everything except silence.
  Still the riskiest option, and only worth it if 3a/3b fail.

## Test protocol (so a fix cannot silently regress)

1. Before any change: note 5 channels that currently work, and 3 that hang. Keep the list.
2. Install the change.
3. Play the 5 working channels — all must still play. This is the regression gate; the
   preflight would have failed it.
4. Play the 3 hanging channels — the app must not freeze, or must unfreeze via step 2.
5. `node tools/test_keys.js` must still pass before installing anything.

Any change that fails gate 3 is reverted immediately, by reverting to the tagged commit.

## What I will not do again

- Ship a change that alters the open path and the failure path in the same build.
- Treat "did not answer an XHR" as "will not play in AVPlay".
- Assume a rendered UI means the key path works, or that a passing harness means the decoder
  path works. Those are separate tests, and only the TV can test the decoder.

## Next action

Say go, and I will do **step 1 only**: a status line plus an event log, no change to playback.
You install it, use it until it hangs, photograph the frozen screen, and that tells us which
hypothesis to chase — without ever having risked the channels that work.
