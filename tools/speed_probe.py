#!/usr/bin/env python3
"""Measure real throughput per channel: time to first byte, segment size and download speed.

    python3 tools/speed_probe.py playlists/sports.m3u reports/speed-sports.csv

For each channel it follows master -> a variant -> the first segment, and reports:

  ttfb_ms   how long the server took to start answering the playlist
  seg_kb    size of the first segment
  kbps      throughput while downloading that segment
  bw        the BANDWIDTH the manifest advertises (bits/s)

Channels slower than --min-kbps (default 1200) or slower to answer than --max-ttfb
(default 3000 ms) are marked slow. This measures the machine running it, so run it on the
network the TV uses.
"""
import concurrent.futures as cf
import csv, os, ssl, sys, time, urllib.error, urllib.parse, urllib.request

UA = 'Mozilla/5.0 (SMART-TV; Linux; Tizen 2.3) AppleWebKit/537.36'
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
TIMEOUT = 10

def open_url(url, limit=None):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': '*/*'})
    start = time.time()
    r = urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX)
    ttfb = (time.time() - start) * 1000.0
    data = r.read(limit) if limit else r.read()
    return data, ttfb, r.geturl(), (r.headers.get('Content-Type') or '').lower()

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

def measure(entry):
    url = entry['url']
    try:
        body, ttfb, final, ctype = open_url(url, limit=300000)
        text = body.decode('utf-8', 'replace')
        base = final
        bw = 0
        if '#EXT-X-STREAM-INF' in text:
            best = None
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if line.startswith('#EXT-X-STREAM-INF'):
                    try:
                        b = int(line.split('BANDWIDTH=')[1].split(',')[0])
                    except Exception:
                        b = 0
                    for nxt in lines[i + 1:]:
                        if nxt and not nxt.startswith('#'):
                            if best is None or b > best[0]:
                                best = (b, urllib.parse.urljoin(base, nxt.strip()))
                            break
            if best:
                bw, variant = best
                body, ttfb2, final2, _ct = open_url(variant, limit=300000)
                text = body.decode('utf-8', 'replace')
                base = final2
                ttfb = max(ttfb, ttfb2)
        seg = None
        for line in text.splitlines():
            if line and not line.startswith('#'):
                seg = urllib.parse.urljoin(base, line.strip())
                break
        if not seg:
            return entry, None, 'no_segment', 0, 0, bw
        start = time.time()
        data, ttfb3, _f, _ct = open_url(seg, limit=200000)
        elapsed = max(time.time() - start, 0.001)
        kbps = (len(data) * 8 / 1000.0) / elapsed
        return entry, ttfb3, 'ok', len(data) // 1024, int(kbps), bw
    except urllib.error.HTTPError as e:
        return entry, None, 'http_%d' % e.code, 0, 0, 0
    except Exception as e:
        return entry, None, type(e).__name__.lower(), 0, 0, 0

def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, out = sys.argv[1], sys.argv[2]
    min_kbps = 1200
    max_ttfb = 3000
    if '--min-kbps' in sys.argv:
        min_kbps = int(sys.argv[sys.argv.index('--min-kbps') + 1])
    if '--max-ttfb' in sys.argv:
        max_ttfb = int(sys.argv[sys.argv.index('--max-ttfb') + 1])

    channels = parse(src)
    os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
    print('%d channels, measuring...' % len(channels), flush=True)

    rows = []
    with cf.ThreadPoolExecutor(max_workers=12) as pool:
        for entry, ttfb, status, seg_kb, kbps, bw in pool.map(measure, channels):
            slow = (status != 'ok') or (ttfb is not None and ttfb > max_ttfb) or (kbps < min_kbps)
            rows.append([entry['name'], status, round(ttfb or 0), seg_kb, kbps, bw,
                         'slow' if slow else 'ok', entry['url']])

    rows.sort(key=lambda r: r[4])
    with open(out, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['name', 'status', 'ttfb_ms', 'seg_kb', 'kbps', 'advertised_bps', 'verdict', 'url'])
        w.writerows(rows)

    slow = [r for r in rows if r[6] == 'slow']
    print('slow: %d of %d' % (len(slow), len(rows)))
    print('\nslowest ten:')
    for r in rows[:10]:
        print('  %-40s %6d kbps  ttfb %5d ms  %s' % (r[0][:40], r[4], r[2], r[1]))
    print('\nwrote', out)

if __name__ == '__main__':
    main()
