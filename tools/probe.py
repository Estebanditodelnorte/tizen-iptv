#!/usr/bin/env python3
"""Check which streams in a playlist are actually reachable from your connection.

    python3 tools/probe.py https://iptv-org.github.io/iptv/countries/ca.m3u playlists/canada.m3u

A stream that answers HTTP 200 with a media content type is kept; everything else is dropped.
This removes dead links before they reach the TV, which cannot tell "dead" from "not my codec".
Geo-blocking is judged from where you run this, so run it on the network the TV uses.
"""
import concurrent.futures as cf
import ssl, sys, urllib.error, urllib.request

UA = 'Mozilla/5.0 (SMART-TV; Linux; Tizen 2.3) AppleWebKit/537.36'
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

def get(url, timeout=45):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={'User-Agent': UA}), timeout=timeout).read().decode('utf-8', 'replace')

def parse(text):
    channels, cur = [], {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('#EXTINF'):
            cur = {'extinf': line}
        elif line and not line.startswith('#'):
            if cur:
                cur['url'] = line
                channels.append(cur)
            cur = {}
    return channels

def probe(entry):
    try:
        req = urllib.request.Request(entry['url'], headers={'User-Agent': UA, 'Accept': '*/*'})
        with urllib.request.urlopen(req, timeout=8, context=CTX) as r:
            ctype = (r.headers.get('Content-Type') or '').lower()
            code = r.getcode()
            r.read(1024)
        ok = code == 200 and ('mpegurl' in ctype or 'video' in ctype or 'octet-stream' in ctype or ctype == '')
        return entry, ok
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return entry, False

def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    url, out = sys.argv[1], sys.argv[2]
    channels = parse(get(url))
    print('%d channels, probing...' % len(channels))
    good = []
    with cf.ThreadPoolExecutor(max_workers=24) as pool:
        for entry, ok in pool.map(probe, channels):
            if ok:
                good.append(entry)
    with open(out, 'w', encoding='utf-8') as f:
        f.write('#EXTM3U\n')
        for e in good:
            f.write(e['extinf'] + '\n' + e['url'] + '\n')
    print('%d of %d reachable -> %s' % (len(good), len(channels), out))

if __name__ == '__main__':
    main()
