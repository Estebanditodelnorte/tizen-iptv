# IPTV for old Samsung TVs

A small IPTV player for **Tizen TVs**, built because the official apps on a 2015 Samsung set
(UHD JU6800, Tizen 2.3) are slow and the store players either want a subscription or cannot be
given a playlist.

The whole channel list is **baked into the app**. There is no server, no account, and the TV
never has to fetch a playlist â€” which matters, because an old Tizen set is bad at exactly that.

## What it does

- Six tabs, switched with **â† / â†’**: CANADA, MEXICO, SPORTS, PUBLIC (PBS, BBC, public access),
  KIDS (PBS Kids by timezone), LEARN (education and documentary).
- **â†‘ / â†“** moves through the channel list, **OK** plays, **BACK** stops.
- The list sits on the left and the video on the right; the list auto-hides 4 s into playback
  and comes back on any key.
- Playback goes through Samsung's **AVPlay** â€” the hardware decoder â€” not the browser's
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

The signing step is not optional: a retail TV only installs widgets signed for it.

## Refresh the channels

The playlists in `playlists/` are snapshots of [iptv-org](https://github.com/iptv-org/iptv)
lists, filtered to what answered from the maintainer's connection (Canada).

```bash
# check a public list from your own network and keep only what works there
python3 tools/probe.py https://iptv-org.github.io/iptv/countries/ca.m3u playlists/canada.m3u

# rebuild the app with the new lists
python3 tools/build.py
```

Run the probe from the network the TV uses: its result is a geo-blocking test, not just a
liveness test. Streams come and go, so expect to re-run this every few months.

## Things that cost time to learn (read before editing)

Writing a player for Tizen 2.3 has three traps, all of which produce **sound with no picture**:

1. **`$WEBAPIS/webapis/webapis.js` must be loaded.** Without it `webapis.avplay` is
   `undefined`, the code falls back to HTML5 `<video>`, and HLS plays audio only.
2. **AVPlay needs an `<object type="application/avplayer">`** in the DOM. It is the surface the
   hardware plane binds to, it must be sized to track `setDisplayRect`, and it must be created
   once.
3. **The page must be transparent over the video**, all the way up to `<html>`. The picture is
   drawn *under* the browser; any opaque background anywhere in the chain hides it.

The other constraint is the package manager: a package id shorter than **10 characters** is
rejected instantly with `PKGMGR_ERROR`, and a *changed* manifest must be uninstalled before it
can be installed again.

## Credits

- Channel data: [iptv-org](https://github.com/iptv-org/iptv) (public domain).
- The AVPlay surface technique â€” including the `<object>` element and the transparency
  requirement â€” is documented in [shayanline/OpenIPTV](https://github.com/shayanline/OpenIPTV)
  (`src/services/player.ts`, MIT). That project targets Tizen 5.5+; this one is aimed at
  Tizen 2.3, where the same rules apply.
- No channel content is included or endorsed. IPTV is a player: what you point it at, and
  whether you are allowed to, is between you and whoever operates the stream.

## Licence

MIT for the code in this repository. The playlists are third-party data, under their own
project's terms.

