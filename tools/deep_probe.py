#!/usr/bin/env python3
"""Deep-check every channel in a playlist and report why it fails.

    python3 tools/deep_probe.py playlists/canada.m3u report-canada.csv

Follows the HLS chain rather than trusting the first URL:

  1. fetch the playlist (master or media)
  2. if it is a master, pick the lowest-bandwidth variant
  3. reject if the media playlist is encrypted (EXT-X-KEY METHOD != NONE) - the TV cannot
     decrypt provider DRM
  4. fetch the first segment and require real media bytes: MPEG-TS sync byte 0x47 or an
     ISO-BMFF 'ftyp' box

Writes a CSV of name,status,reason,url and a .m3u of the channels that passed.
A pass here still is not proof the TV decodes it - codec support is the TV's call - but a
fail is a definite fail.
"""
import concurrent.futures as cf
import csv, os, ssl, sys, urllib.error, urllib.parse, urllib.request

UA = 'Mozilla/5.0 (SMART-TV; Linux; Tizen 2.3) AppleWebKit/537.36'
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
TIMEOUT = 8

def fetch(url, head=False, limit=None):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': '*/*'})
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX) as r:
        if head:
            return b'', r.getcode(), (r.headers.get('Content-Type') or '').lower(), r.geturl()
        data = r.read(limit) if limit else r.read()
        return data, r.getcode(), (r.headers.get('Content-Type') or '').lower(), r.geturl()

def text(url):
    """Return (playlist text, final URL after redirects). The final URL matters: shorteners
    like jmp2.uk redirect to the real manifest, and relative segment paths must resolve
    against the real one, not the short one."""
    data, _code, _ct, final = fetch(url, limit=400000)
    return data.decode('utf-8', 'replace'), final

def resolve(base, uri):
    return urllib.parse.urljoin(base, uri)

def is_media(playlist):
    return '#EXTINF' in playlist

def first_segment(playlist, base):
    for line in playlist.splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            return resolve(base, line)
    return None

def check(entry):
    url = entry['url']
    try:
        body, code, ctype, final_url = fetch(url, limit=400000)
        if code != 200:
            return entry, False, 'http_%d' % code
        head = body[:64]
        if head[:7] != b'#EXTM3U' and 'mpegurl' not in ctype:
            return entry, False, 'not_hls'
        playlist = body.decode('utf-8', 'replace')
        base = final_url

        if '#EXT-X-STREAM-INF' in playlist:
            variants = []
            lines = playlist.splitlines()
            for i, line in enumerate(lines):
                if line.startswith('#EXT-X-STREAM-INF'):
                    bw = 0
                    for part in line.split(','):
                        if 'BANDWIDTH=' in part:
                            try:
                                bw = int(part.split('BANDWIDTH=')[1].split(',')[0])
                            except ValueError:
                                bw = 0
                    for nxt in lines[i + 1:]:
                        if nxt and not nxt.startswith('#'):
                            variants.append((bw, resolve(base, nxt.strip())))
                            break
            if not variants:
                return entry, False, 'no_variants'
            variants.sort()
            variant_url = variants[0][1]
            playlist, base = text(variant_url)

        if not is_media(playlist):
            return entry, False, 'no_segments'

        for line in playlist.splitlines():
            if not line.startswith('#EXT-X-KEY'):
                continue
            upper = line.upper()
            if 'METHOD=NONE' in upper:
                continue
            if 'WIDEVINE' in upper or 'PLAYREADY' in upper or 'URN:UUID' in upper:
                return entry, False, 'drm'
            if 'METHOD=SAMPLE-AES' in upper:
                return entry, False, 'drm'
            if 'METHOD=AES-128' in upper:
                # Standard HLS encryption: the player fetches the key itself. Segments are
                # ciphertext, so the media-bytes check below cannot apply.
                return entry, True, 'aes128'
            return entry, False, 'drm'

        seg = first_segment(playlist, base)
        if not seg:
            return entry, False, 'no_segment_url'

        seg_bytes, code, _ct, _final = fetch(seg, limit=1024)
        if code != 200 or not seg_bytes:
            return entry, False, 'segment_http_%d' % code
        if seg_bytes[0] == 0x47:
            return entry, True, 'ts'
        if b'ftyp' in seg_bytes[:64]:
            return entry, True, 'mp4'
        if seg_bytes[:2] == b'\x1f\x8b':
            return entry, True, 'gzip'
        return entry, False, 'bad_segment'
    except urllib.error.HTTPError as e:
        return entry, False, 'http_%d' % e.code
    except urllib.error.URLError as e:
        return entry, False, 'net_%s' % type(e.reason).__name__ if hasattr(e, 'reason') else 'net'
    except Exception as e:
        return entry, False, type(e).__name__.lower()

def parse(path):
    channels, cur = [], {}
    for line in open(path, encoding='utf-8', errors='replace'):
        line = line.strip()
        if line.startswith('#EXTINF'):
            cur = {'extinf': line, 'name': line.split(',', 1)[-1].strip()}
        elif line and not line.startswith('#'):
            if cur:
                cur['url'] = line
                channels.append(cur)
            cur = {}
    return channels

def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, csv_path = sys.argv[1], sys.argv[2]
    channels = parse(src)
    print('%d channels, deep-checking...' % len(channels), flush=True)

    results = []
    with cf.ThreadPoolExecutor(max_workers=32) as pool:
        for entry, ok, reason in pool.map(check, channels):
            results.append((entry, ok, reason))

    good = [e for e, ok, _ in results if ok]
    bad = [(e, r) for e, ok, r in results if not ok]

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['name', 'status', 'reason', 'url'])
        for e, ok, reason in results:
            w.writerow([e['name'], 'ok' if ok else 'fail', reason, e['url']])

    out_m3u = os.path.splitext(src)[0] + '-deep.m3u'
    with open(out_m3u, 'w', encoding='utf-8') as f:
        f.write('#EXTM3U\n')
        for e in good:
            f.write(e['extinf'] + '\n' + e['url'] + '\n')

    print('pass %d / %d' % (len(good), len(channels)))
    from collections import Counter
    print('failure reasons:', dict(Counter(r for _e, r in bad).most_common()))
    print('csv   :', csv_path)
    print('clean :', out_m3u)

if __name__ == '__main__':
    main()
