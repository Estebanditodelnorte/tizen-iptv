#!/usr/bin/env python3
"""Verify a channel really carries video, by parsing the media rather than trusting HTTP 200.

    python3 tools/video_probe.py playlists/sports.m3u reports/video-sports.csv

For each entry: master -> variant -> first segment, then

  * AES-128 / SAMPLE-AES encrypted playlists are reported as `encrypted` (Tizen 2.3 cannot
    decrypt HLS AES-128, which is why Pluto-backed channels fail on it)
  * MPEG-TS segments are parsed: PAT -> PMT -> elementary stream types. H.264 (0x1b),
    HEVC (0x24), MPEG-2 (0x02) and MPEG-4 (0x10) count as video; audio-only playlists do not.
  * fragmented MP4 segments are checked for a `vide` handler.

Writes a CSV and a .m3u containing only the channels with a verified video stream.
"""
import concurrent.futures as cf
import csv, os, ssl, sys, urllib.error, urllib.parse, urllib.request

UA = 'Mozilla/5.0 (SMART-TV; Linux; Tizen 2.3) AppleWebKit/537.36'
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
TIMEOUT = 9
VIDEO_TYPES = {0x01, 0x02, 0x10, 0x1B, 0x24, 0x42, 0xEA}

def get(url, limit=None):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': '*/*'})
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=CTX) as r:
        data = r.read(limit) if limit else r.read()
        return data, r.geturl(), (r.headers.get('Content-Type') or '').lower()

def parse_ts_video(data):
    """Return True/False if the PMT lists a video elementary stream, None if no PMT was found."""
    if not data or data[0] != 0x47:
        return None

    def payload(pkt):
        """Offset of payload data, or None when the packet carries none."""
        if pkt[0] != 0x47 or len(pkt) < 188:
            return None
        afc = (pkt[3] >> 4) & 0x3
        p = 4
        if afc & 0x2:
            p += 1 + pkt[4]
        if not (afc & 0x1) or p >= 188:
            return None
        return p

    pmt_pids = set()
    for off in range(0, len(data) - 188, 188):
        pkt = data[off:off + 188]
        if pkt[0] != 0x47:
            continue
        pid = ((pkt[1] & 0x1F) << 8) | pkt[2]
        if pid != 0 or not (pkt[1] & 0x40):
            continue
        p = payload(pkt)
        if p is None:
            continue
        p += 1 + pkt[p]
        if p + 8 >= 188 or pkt[p] != 0x00:
            continue
        section_len = ((pkt[p + 1] & 0x0F) << 8) | pkt[p + 2]
        end = min(p + 3 + section_len - 4, 188)
        q = p + 8
        while q + 4 <= end:
            prog = (pkt[q] << 8) | pkt[q + 1]
            ppid = ((pkt[q + 2] & 0x1F) << 8) | pkt[q + 3]
            if prog != 0:
                pmt_pids.add(ppid)
            q += 4
        if pmt_pids:
            break

    if not pmt_pids:
        return None

    for off in range(0, len(data) - 188, 188):
        pkt = data[off:off + 188]
        if pkt[0] != 0x47:
            continue
        pid = ((pkt[1] & 0x1F) << 8) | pkt[2]
        if pid not in pmt_pids or not (pkt[1] & 0x40):
            continue
        p = payload(pkt)
        if p is None:
            continue
        p += 1 + pkt[p]
        if p + 12 >= 188 or pkt[p] != 0x02:
            continue
        section_len = ((pkt[p + 1] & 0x0F) << 8) | pkt[p + 2]
        prog_info_len = ((pkt[p + 10] & 0x0F) << 8) | pkt[p + 11]
        end = min(p + 3 + section_len - 4, 188)
        q = p + 12 + prog_info_len
        while q + 5 <= end:
            stype = pkt[q]
            if stype in VIDEO_TYPES:
                return True
            es_len = ((pkt[q + 3] & 0x0F) << 8) | pkt[q + 4]
            q += 5 + es_len
        return False
    return None

def check(entry):
    try:
        body, final, ctype = get(entry['url'], limit=400000)
        text = body.decode('utf-8', 'replace')
        if '#EXTM3U' not in text[:64] and 'mpegurl' not in ctype:
            return entry, False, 'not_hls'
        base = final
        if '#EXT-X-STREAM-INF' in text:
            best = None
            lines = text.splitlines()
            for i, line in enumerate(lines):
                if line.startswith('#EXT-X-STREAM-INF'):
                    try:
                        bw = int(line.split('BANDWIDTH=')[1].split(',')[0])
                    except Exception:
                        bw = 0
                    # skip audio-only renditions: some masters list one at the lowest bandwidth
                    codecs = ''
                    if 'CODECS=' in line:
                        codecs = line.split('CODECS=')[1].split('"')[1].lower()
                    if codecs and not any(v in codecs for v in ('avc1', 'hvc1', 'hev1', 'av01', 'mp4v', 'vp09')):
                        continue
                    for nxt in lines[i + 1:]:
                        if nxt and not nxt.startswith('#'):
                            if best is None or bw < best[0]:
                                best = (bw, urllib.parse.urljoin(base, nxt.strip()))
                            break
            if not best:
                return entry, False, 'no_variants'
            body2, final2, _ct2 = get(best[1], limit=400000)
            text = body2.decode('utf-8', 'replace')
            base = final2
        return check_media(entry, text, base)
    except urllib.error.HTTPError as e:
        return entry, False, 'http_%d' % e.code
    except Exception as e:
        return entry, False, type(e).__name__.lower()

def check_media(entry, text, base):
    for line in text.splitlines():
        if line.startswith('#EXT-X-KEY') and 'METHOD=NONE' not in line:
            upper = line.upper()
            if 'WIDEVINE' in upper or 'PLAYREADY' in upper or 'SAMPLE-AES' in upper:
                return entry, False, 'drm'
            if 'AES-128' in upper:
                return entry, False, 'encrypted'
    seg = None
    for line in text.splitlines():
        if line and not line.startswith('#'):
            seg = urllib.parse.urljoin(base, line.strip())
            break
    if not seg:
        return entry, False, 'no_segment'
    data, final2, _ct = get(seg, limit=400000)
    if not data:
        return entry, False, 'empty_segment'
    if data[0] == 0x47:
        verdict = parse_ts_video(data)
        if verdict is True:
            return entry, True, 'ts_video'
        if verdict is False:
            return entry, False, 'ts_audio_only'
        return entry, False, 'ts_no_pmt'
    if b'ftyp' in data[:64]:
        head = data[:400000]
        if b'vide' in head or b'avc1' in head or b'hvc1' in head:
            return entry, True, 'mp4_video'
        return entry, False, 'mp4_no_video'
    return entry, False, 'unknown_container'

def parse(path):
    out, cur = [], {}
    for line in open(path, encoding='utf-8', errors='replace'):
        line = line.rstrip('\n')
        if line.startswith('#EXTINF'):
            cur = {'extinf': line, 'name': line.split(',', 1)[-1].strip()}
        elif line and not line.startswith('#'):
            if cur:
                cur['url'] = line
                out.append(cur)
            cur = {}
    return out

def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    src, out_csv = sys.argv[1], sys.argv[2]
    channels = parse(src)
    os.makedirs(os.path.dirname(out_csv) or '.', exist_ok=True)
    print('%d channels, verifying video...' % len(channels), flush=True)

    results = []
    with cf.ThreadPoolExecutor(max_workers=16) as pool:
        for entry, ok, reason in pool.map(check, channels):
            results.append((entry, ok, reason))

    with open(out_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['name', 'status', 'reason', 'url'])
        for e, ok, reason in results:
            w.writerow([e['name'], 'ok' if ok else 'fail', reason, e['url']])

    good = [e for e, ok, _ in results if ok]
    out_m3u = os.path.splitext(src)[0] + '-video.m3u'
    with open(out_m3u, 'w', encoding='utf-8') as f:
        f.write('#EXTM3U\n')
        for e in good:
            f.write(e['extinf'] + '\n' + e['url'] + '\n')

    from collections import Counter
    print('kept %d / %d' % (len(good), len(channels)))
    print('reasons:', dict(Counter(r for _e, _ok, r in results if _ok is False).most_common()))
    print('csv:', out_csv)
    print('m3u:', out_m3u)

if __name__ == '__main__':
    main()
