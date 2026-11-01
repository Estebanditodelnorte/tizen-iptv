#!/usr/bin/env python3
"""Apply a speed report to a playlist.

Channels that failed outright or measured under --drop kbps are removed. Channels between
--drop and --slow are kept but moved into a "<group> (slow)" section at the end, so they are
still available without cluttering the main list.

    python3 tools/apply_speed.py playlists/sports.m3u reports/speed-sports.csv
"""
import csv, os, sys

def parse(path):
    entries, cur = [], {}
    for line in open(path, encoding='utf-8', errors='replace'):
        line = line.rstrip('\n')
        if line.startswith('#EXTINF'):
            cur = {'extinf': line}
        elif line and not line.startswith('#'):
            if cur:
                cur['url'] = line
                entries.append(cur)
            cur = {}
    return entries

def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    m3u, report = sys.argv[1], sys.argv[2]
    drop = int(sys.argv[sys.argv.index('--drop') + 1]) if '--drop' in sys.argv else 600
    slow = int(sys.argv[sys.argv.index('--slow') + 1]) if '--slow' in sys.argv else 1000

    stats = {}
    for row in csv.DictReader(open(report, encoding='utf-8')):
        stats[row['url']] = row

    entries = parse(m3u)
    keep, demoted, removed = [], [], []
    for e in entries:
        row = stats.get(e['url'])
        if not row:
            keep.append(e)
            continue
        kbps = int(row['kbps'] or 0)
        if row['status'] != 'ok' or kbps < drop:
            removed.append((row['name'], row['status'], kbps))
            continue
        if kbps < slow:
            demoted.append((row['name'], kbps))
            import re
            if 'group-title="' in e['extinf']:
                e['extinf'] = re.sub(r'group-title="[^"]*"', 'group-title="Sports (slow)"', e['extinf'], count=1)
            keep.append(e)
            continue
        keep.append(e)

    with open(m3u, 'w', encoding='utf-8') as f:
        f.write('#EXTM3U\n')
        for e in keep:
            f.write(e['extinf'] + '\n' + e['url'] + '\n')

    print('removed %d, demoted %d, kept %d' % (len(removed), len(demoted), len(keep)))
    for name, status, kbps in removed:
        print('  removed  %-42s %-10s %d kbps' % (name[:42], status, kbps))
    for name, kbps in demoted:
        print('  demoted  %-42s %d kbps' % (name[:42], kbps))

if __name__ == '__main__':
    main()
