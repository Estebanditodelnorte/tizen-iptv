# IPTV for old Samsung TVs

A small IPTV player for **Tizen TVs**, built because the official apps on a 2015 Samsung set
(UHD JU6800, Tizen 2.3) are slow and the store players either want a subscription or cannot be
given a playlist.

The whole channel list is **baked into the app**. There is no server, no account, and the TV
never has to fetch a playlist — which matters, because an old Tizen set is bad at exactly that.

## What it does

- Six tabs, switched with **â† / â†’**: CANADA, MEXICO, SPORTS, PUBLIC (PBS, BBC, public access),
  KIDS (PBS Kids by timezone), LEARN (education and documentary), MUSIC (Spanish rock, pop, retro).
- **â†‘ / â†“** moves through the channel list, **OK** plays, **BACK** stops.
- **GREEN** tests every channel in the current tab and marks the ones the TV cannot play.
- The list sits on the left and the video on the right; the list auto-hides 4 s into playback
  and comes back on any key.
- Playback goes through Samsung's **AVPlay** — the hardware decoder — not the browser's
  `<video>` element.

## Install on the TV

You need Developer Mode on the TV and a computer on the same network.

1. **TV:** Apps â†’ press `1 2 3 4 5` â†’ Developer Mode on â†’ Host PC IP = the computer's address â†’
   restart the TV.
2. **Build the widget:**

   ```bash
   python3 tools/build.py            # writes app/index.html and app/config.xml
   ```

3. **Sign it** with Tizen Studio (`tizen package -t wgt -s <profile> -- app`) and install it over
   SDB (`vd_appinstall`), or use [Apps2Samsung](https://github.com/Apps2Samsung/Apps2Samsung),
   which signs and installs in one step.

Signing is not optional: a retail TV only installs widgets signed for that TV.

## Testing channels, and cleaning the dead ones

Public IPTV lists rot constantly. There are two tests, and they answer different questions.

**1. On the TV — press GREEN.** The app walks every channel in the current tab, opens it, and
waits for the decoder to accept it (9 s each). Failures are marked **âœ—**, dimmed, and remembered
in `localStorage`, so they stay marked after a restart. Pressing GREEN during a run stops it.
This is the only test that reflects what your TV can actually decode.

Expect it to take a while: roughly 10 s per channel, so ~20 minutes for a 107-channel tab and
over an hour for KIDS (311). Run it per tab, not all at once.

**2. On a computer — `tools/deep_probe.py`.** Follows the HLS chain instead of trusting the
first URL: master playlist â†’ lowest-bandwidth variant â†’ first segment, rejecting provider DRM
(`EXT-X-KEY`), missing segments, and segments that are not real media (MPEG-TS `0x47` sync byte
or an `ftyp` box). It writes a CSV with a reason per channel plus a cleaned playlist.

```bash
python3 tools/deep_probe.py playlists/canada.m3u report-canada.csv
#   -> report-canada.csv, playlists/canada-deep.m3u
python3 tools/build.py
```

A pass on the computer is not proof (codecs are the TV's call), but a **fail is definite** — so
run it first, then spend TV time only on what survives.

## Refresh the playlists

`playlists/` holds snapshots of [iptv-org](https://github.com/iptv-org/iptv) lists, filtered to
what answered from the maintainer's connection (Canada).

```bash
# check a public list from your own network and keep only what works there
python3 tools/probe.py https://iptv-org.github.io/iptv/countries/ca.m3u playlists/canada.m3u

# rebuild the app with the new lists
python3 tools/build.py
```

Run the probe from the network the TV uses: the result is a geo-blocking test, not just a
liveness test.

## Things that cost time to learn (read before editing)

Writing a player for Tizen 2.3 has three traps, and all of them produce **sound with no
picture**:

1. **`$WEBAPIS/webapis/webapis.js` must be loaded.** Without it `webapis.avplay` is
   `undefined`, the code falls back to HTML5 `<video>`, and HLS plays audio only.
2. **AVPlay needs an `<object type="application/avplayer">`** in the DOM. It is the surface the
   hardware plane binds to, it must be sized to track `setDisplayRect`, and it must be created
   once.
3. **The page must be transparent over the video**, all the way up to `<html>`. The picture is
   drawn *under* the browser; any opaque background anywhere in the chain hides it.

Two more, from the package manager:

- A package id shorter than **10 characters** is rejected instantly with `PKGMGR_ERROR`.
- A **changed manifest** must be uninstalled before it can be installed again, and an app that
  is currently running blocks its own update.

One known-limitation: channels that carry audio as a **separate HLS rendition**
(`EXT-X-MEDIA ... URI="audio.m3u8"`) may play silently on Tizen 2.3. The app calls
`setSelectTrack('AUDIO', 0)` after `prepareAsync`, which helps on some firmware but not all.

## Language filter

Lists from a "country" still contain channels in other languages — the Canadian list alone had
Punjabi, Bengali, Hindi, Tamil, Urdu and Persian entries. `tools/filter_lang.py` drops anything
whose language is not English, French or Spanish, using the `languages` field in iptv-org's
`feeds.json` matched against each entry's `tvg-id` (`Channel.ca@SD` = channel + feed):

```bash
python3 tools/filter_lang.py playlists/canada.m3u --in-place
```

Coverage was 100% on these lists (no channel lacked metadata), so nothing was dropped for being
unknown. On the current lists it removed 22 of Canada's 107, 135 of 306 sports, 141 of 311 kids
and 65 of 159 learn — 1,048 channels down to 684. Mexico and PUBLIC were already 100% in scope.

Two caveats: a channel can be mislabelled upstream (Canada One is listed as English but
broadcasts Punjabi, so it was removed by hand), and dropping by language also drops silent or
music channels whose only audio is not speech.
## Slow channels

Reachability is not speed. `tools/speed_probe.py` measures each channel for real: it follows
master -> variant -> first segment and reports time-to-first-byte, segment size and throughput
(kbps), plus the bandwidth the manifest advertises.

```bash
python3 tools/speed_probe.py playlists/sports.m3u reports/speed-sports.csv
python3 tools/apply_speed.py playlists/sports.m3u reports/speed-sports.csv
```

`apply_speed.py` removes anything under 600 kbps (or that failed outright), and moves 600-1000
kbps into a "Sports (slow)" group at the end of the list instead of deleting it - slow is a
judgement call, broken is not. Run it on the network the TV uses; the numbers are that
machine's view of the internet.

## Ordering by speed

`speed_probe.py` writes a CSV per playlist; `order_by_speed.py` re-sorts that playlist fastest
first and rewrites each entry's `group-title` to its tier, so the app shows FAST, then MEDIUM,
then SLOW:

```bash
python3 tools/speed_probe.py playlists/sports.m3u reports/speed-sports.csv
python3 tools/order_by_speed.py playlists/sports.m3u reports/speed-sports.csv
```

Thresholds default to 2500 kbps (FAST) and 1000 kbps (MEDIUM); pass `--fast` / `--slow` to
change them. Entries with no successful measurement are dropped, on the view that a channel
nobody could measure is not one to put in front of a viewer.

## Verifying that a channel has video

`tools/video_probe.py` does not trust HTTP 200. It follows master -> variant -> first segment
and inspects the media itself:

- **MPEG-TS** segments are parsed: PAT -> PMT -> elementary stream types. H.264 (0x1b),
  HEVC (0x24), MPEG-2 (0x02) and MPEG-4 (0x10) count as video; an audio-only playlist does not.
- **fragmented MP4** segments are checked for a `vide` handler.
- **AES-128 / SAMPLE-AES** playlists are rejected as `encrypted`.

That last point is the useful discovery: Tizen 2.3 cannot decrypt HLS AES-128, so every
Pluto-backed channel (the `jmp2.uk/plu-...` URLs) plays as nothing on this TV. That is why
The Weather Network never worked, and removing that whole class took KIDS from 156 to 84.

```bash
python3 tools/video_probe.py playlists/kids.m3u reports/video-kids.csv
```

Variant selection skips audio-only renditions - some masters list one at the lowest bandwidth,
and picking it made a healthy channel look audio-only.

## Credits

- Channel data: [iptv-org](https://github.com/iptv-org/iptv) (public domain).
- The AVPlay surface technique — the `<object>` element and the transparency requirement — is
  documented in [shayanline/OpenIPTV](https://github.com/shayanline/OpenIPTV)
  (`src/services/player.ts`, MIT). That project targets Tizen 5.5+; this one is aimed at
  Tizen 2.3, where the same rules apply.
- No channel content is included or endorsed. IPTV is a player: what you point it at, and
  whether you are allowed to, is between you and whoever operates the stream.

## Licence

MIT for the code in this repository. The playlists are third-party data, under their own
project's terms.

