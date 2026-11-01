#!/usr/bin/env python3
"""Drop channels whose language is not English, French or Spanish.

    python3 tools/filter_lang.py playlists/canada.m3u [--keep eng,fra,spa] [--in-place]

Language comes from iptv-org's feeds.json, keyed by the playlist's tvg-id, which is
"<channel id>@<feed id>" (for example 3ABNCanada.ca@SD). Channels with no tvg-id, or whose id
is not in the feed database, are KEPT and counted as "unknown" - dropping them would throw away
working channels for lack of metadata.

Downloads feeds.json once per run (~8 MB) and caches it next to this script.
"""
import csv, json, os, sys, urllib.request

API = 'https://iptv-org.github.io/api/feeds.json'
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.feeds.json')
UA = 'Mozilla/5.0'

def feeds():
    if os.path.exists(CACHE) and os.path.getsize(CACHE) > 1000000:
        return json.load(open(CACHE, encoding='utf-8'))
    data = urllib.request.urlopen(urllib.request.Request(API, headers={'User-Agent': UA}), timeout=180).read()
    open(CACHE, 'wb').write(data)
    return json.loads(data)

def index(feed_list):
    by_pair, by_channel = {}, {}
    for f in feed_list:
        langs = f.get('languages') or []
        by_pair[(f.get('channel'), f.get('id'))] = langs
        if f.get('is_main') or f.get('channel') not in by_channel:
            by_channel[f.get('channel')] = langs
    return by_pair, by_channel

def tvg_id(extinf):
    marker = 'tvg-id="'
    i = extinf.find(marker)
    if i < 0:
        return ''
    return extinf[i + len(marker):].split('"', 1)[0]

def languages_of(extinf, by_pair, by_channel):
    tid = tvg_id(extinf)
    if not tid:
        return None
    if '@' in tid:
        ch, feed = tid.split('@', 1)
        if (ch, feed) in by_pair:
            return by_pair[(ch, feed)]
        if ch in by_channel:
            return by_channel[ch]
        return None
    return by_channel.get(tid)

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path = sys.argv[1]
    keep = {'eng', 'fra', 'spa'}
    if '--keep' in sys.argv:
        keep = set(sys.argv[sys.argv.index('--keep') + 1].split(','))
    in_place = '--in-place' in sys.argv

    by_pair, by_channel = index(feeds())
    lines = open(path, encoding='utf-8').read().splitlines()

    kept, dropped, unknown = [], [], []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXTINF'):
            url = lines[i + 1] if i + 1 < len(lines) else ''
            langs = languages_of(line, by_pair, by_channel)
            name = line.split(',', 1)[-1].strip()
            if langs is None:
                kept.append((line, url)); unknown.append(name)
            elif not langs or (set(langs) & keep):
                kept.append((line, url))
            else:
                dropped.append((name, langs))
            i += 2
            continue
        i += 1

    out = '#EXTM3U\n' + ''.join(e + '\n' + u + '\n' for e, u in kept)
    target = path if in_place else os.path.splitext(path)[0] + '-lang.m3u'
    open(target, 'w', encoding='utf-8').write(out)

    print('%s: kept %d, dropped %d, unknown-language %d' % (os.path.basename(path), len(kept), len(dropped), len(unknown)))
    for name, langs in dropped[:12]:
        print('   dropped %-40s %s' % (name[:40], ','.join(langs)))
    if len(dropped) > 12:
        print('   ... and %d more' % (len(dropped) - 12))
    print('   ->', target)

if __name__ == '__main__':
    main()
