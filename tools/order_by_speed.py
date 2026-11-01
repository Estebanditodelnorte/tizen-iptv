#!/usr/bin/env python3
"""Reorder a playlist by measured speed, with the speed tier as the section heading.

    python3 tools/order_by_speed.py playlists/sports.m3u reports/speed-sports.csv

Channels are sorted fastest first and regrouped into FAST / MEDIUM / SLOW, so the list reads
from the ones that start instantly to the ones that stutter. Thresholds default to 2500 and
1000 kbps; override with --fast and --slow.
"""
import csv, os, re, sys

def entries(path):
    out, cur = [], {}
    for line in open(path, encoding='utf-8', errors='replace'):
        line = line.rstrip('\n')
        if line.startswith('#EXTINF'):
            cur = {'extinf': line}
        elif line and not line.startswith('#'):
            if cur:
                cur['url'] = line
                out.append(cur)
            cur = {}
    return out

def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    m3u, report = sys.argv[1], sys.argv[2]
    fast = int(sys.argv[sys.argv.index('--fast') + 1]) if '--fast' in sys.argv else 2500
    slow = int(sys.argv[sys.argv.index('--slow') + 1]) if '--slow' in sys.argv else 1000

    stats = {}
    for row in csv.DictReader(open(report, encoding='utf-8')):
        try:
            kbps = int(row.get('kbps') or 0)
        except ValueError:
            kbps = 0
        stats[row['url']] = (kbps, row.get('status', ''))

    items = entries(m3u)
    ordered = []
    for e in items:
        kbps, status = stats.get(e['url'], (0, 'unmeasured'))
        if status != 'ok':
            continue
        tier = 'FAST' if kbps >= fast else ('MEDIUM' if kbps >= slow else 'SLOW')
        if 'group-title="' in e['extinf']:
            e['extinf'] = re.sub(r'group-title="[^"]*"', 'group-title="%s"' % tier, e['extinf'], count=1)
        else:
            e['extinf'] = e['extinf'].replace('#EXTINF:-1', '#EXTINF:-1 group-title="%s"' % tier, 1)
        ordered.append((kbps, tier, e))

    tier_rank = {'FAST': 0, 'MEDIUM': 1, 'SLOW': 2}
    ordered.sort(key=lambda x: (tier_rank[x[1]], -x[0]))

    with open(m3u, 'w', encoding='utf-8') as f:
        f.write('#EXTM3U\n')
        for _kbps, _tier, e in ordered:
            f.write(e['extinf'] + '\n' + e['url'] + '\n')

    from collections import Counter
    counts = Counter(t for _k, t, _e in ordered)
    print('%s: FAST %d, MEDIUM %d, SLOW %d (dropped %d unmeasured/failed)'
          % (os.path.basename(m3u), counts['FAST'], counts['MEDIUM'], counts['SLOW'], len(items) - len(ordered)))

if __name__ == '__main__':
    main()
