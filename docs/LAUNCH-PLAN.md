# Launch plan — critical path

Written after the laptop rebooted and lost its Wi-Fi profile. Ordered so that nothing waits on
something that is not done yet.

## Where things actually stand

| Item | State |
|---|---|
| Laptop Wi-Fi | **DHCP, automatic**, now `192.168.2.13` |
| TV | reachable at `192.168.2.12` (ping OK) |
| SDB `26101` | **refused** — TV Developer Mode whitelists `192.168.2.47` |
| App on TV | `df40d9b` — has the auto-bad bug and stop-without-close |
| Repo `HEAD` | `68f058e` — all fixes, none installed |
| Ratings | on the TV only; not photographed; one (LCN) currently wrong |

## Why the build was good when it was good

Not luck, and worth writing down so it can be repeated:

1. The installed app came from a **commit known to work** (`b0b8791`), not from a fresh
   experiment.
2. Every change after that was **tested in `tools/test_keys.js` before installing** — which
   caught two broken builds that would otherwise have reached the TV.
3. Installs succeeded because the **laptop's IP matched the TV's whitelist**. The moment it
   drifted to `.13`, every install failed — and that looked like an app problem for days.

The lesson: a good build is *a known-good commit + a passing harness + a working SDB link*.
All three, every time.

## Critical path

The chain that gates launch. Everything else can slip without delaying the date.

**CP1 — restore SDB (blocker, ~10 min).**
Either set the laptop static to `192.168.2.47`, or set the TV's Developer Mode Host PC IP to
`192.168.2.13` and restart the TV. Nothing else can be verified until this passes:
`sdb devices` must list the TV.

**CP2 — photograph the ratings (can run in parallel with CP1).**
Per tab, scroll the rated sections. No dependency on the network, and it is the only data that
exists nowhere else. Transcribe into `playlists/ratings.json`.

**CP3 — install `68f058e` and run the gate (~15 min).**
Five channels known to work must still play, or revert immediately to `df40d9b`.

**CP4 — LCN check.**
It will likely still show as BAD on the TV (stored value from the old auto-demotion). Rate it
★★ once; it must stay in VERY GOOD across two restarts. That is the acceptance test for the
whole "app cannot overrule the owner" change.

**CP5 — movies and news (optional, after launch).**
38 movie and 50 news candidates are video-verified and waiting in `reports/`. Nine tabs needs a
layout check first.

## Not on the critical path

- FRAGILE host tuning
- Web Inspector (port 7011) reading of `localStorage`
- Virtualising the list
- Re-adding the version stamp

## Test checklist after CP3

- [ ] Five previously working channels still play
- [ ] Two different channels switched quickly — no hang
- [ ] BACK during playback → tag menu appears
- [ ] Rating a channel bad leaves the cursor on the same row
- [ ] A definitely dead channel shows a message and does **not** change any rating
- [ ] LCN (CP4) stays VERY GOOD after two restarts
- [ ] Rating survives an app restart
