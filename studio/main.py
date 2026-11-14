"""CLI.

python -m studio.main produce  --out out          # konu seç -> senaryo -> ses -> video (+ meta.json)
python -m studio.main render   --storyboard sb.json --audio vo.wav --out out   # API'siz render (test)
python -m studio.main publish  --meta out/<id>.json --url <public mp4 url>
python -m studio.main channels                    # Buffer'daki kanalları listele
"""
import argparse
import datetime as dt
import json
import os
import re
import unicodedata
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CFG_PATH = os.path.join(ROOT, 'config.yaml')
STATE = os.path.join(ROOT, 'content', 'state.json')
TOPICS = os.path.join(ROOT, 'content', 'topics.txt')


def load_cfg():
    with open(CFG_PATH, encoding='utf-8') as f:
        return yaml.safe_load(f)


def slug(s):
    s = unicodedata.normalize('NFKD', s.replace('ı', 'i')).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-zA-Z0-9]+', '-', s).strip('-').lower()[:50] or 'video'


def pick_topic(cfg):
    st = {'next': 0, 'history': []}
    if os.path.exists(STATE):
        st = json.load(open(STATE, encoding='utf-8'))
    topics = [l.strip() for l in open(TOPICS, encoding='utf-8') if l.strip() and not l.startswith('#')]
    if st['next'] < len(topics):
        topic = topics[st['next']]
    else:
        from .llm import new_topic
        topic = new_topic(st['history'], cfg)
    return topic, st


def save_state(st, topic):
    st['next'] += 1
    st['history'].append(topic)
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(st, open(STATE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)


def fill_links(text, cfg):
    for k, v in (cfg.get('affiliates') or {}).items():
        text = text.replace('{' + k + '}', v['url'])
    return re.sub(r'\{[A-Z_]+\}', '', text)


def next_slot(cfg):
    """En yakın yayın saati (en az 10 dk sonrası), UTC ISO."""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(cfg['publish'].get('timezone', 'Europe/Istanbul'))
    now = dt.datetime.now(tz)
    for day in (0, 1):
        for hhmm in cfg['publish']['slots']:
            h, m = map(int, hhmm.split(':'))
            cand = (now + dt.timedelta(days=day)).replace(hour=h, minute=m, second=0, microsecond=0)
            if cand > now + dt.timedelta(minutes=10):
                return cand.astimezone(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')
    return None


def build_meta(sb, cfg, vid):
    caption = fill_links(sb.get('caption', ''), cfg)
    tags = ' '.join(h if h.startswith('#') else '#' + h for h in sb.get('hashtags', [])[:10])
    kw = sb.get('cta_keyword', cfg['cta']['default_keyword'])
    dm = fill_links(sb.get('dm') or cfg['dm']['default'], cfg).strip()
    if not any(v['url'] in dm for v in (cfg.get('affiliates') or {}).values()):
        dm += '\n\n' + '\n'.join(f"{v['name']}: {v['url']}" for v in cfg['affiliates'].values())
    if cfg['dm'].get('disclosure'):
        dm += '\n\n' + cfg['dm']['disclosure']
    ig_cta = cfg['cta']['ig_line'].format(kw=kw)
    links = '\n'.join(f"{v['name']}: {v['url']}" for v in cfg['affiliates'].values())
    disclosure = cfg['disclosure']
    ig = '\n\n'.join(x for x in [caption, ig_cta, disclosure, tags] if x)
    yt_tags = tags if '#shorts' in tags.lower() else (tags + ' #shorts').strip()
    has_links = any(v['url'] in caption for v in cfg['affiliates'].values())
    yt = '\n\n'.join(x for x in [caption, '' if has_links else '🔗 ' + links, disclosure, yt_tags] if x)
    return {'id': vid, 'title': sb.get('title', vid), 'youtube_title': sb.get('youtube_title', sb.get('title', vid)),
            'instagram_text': ig[:2150], 'youtube_text': yt[:4900], 'keyword': kw, 'dm': dm[:950],
            'segments': sb['segments']}


def do_render(sb, audio, out, cfg, vid):
    from .render import build_timeline, render
    from .core import Avatar
    tl = build_timeline(sb, audio)
    av = Avatar(width=cfg.get('avatar', {}).get('width', 420))
    mp4 = os.path.join(out, f'{vid}.mp4')
    render(tl, audio, mp4, av)
    meta = build_meta(sb, cfg, vid)
    meta['duration'] = round(tl['duration'], 2)
    json.dump(meta, open(os.path.join(out, f'{vid}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return mp4, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['produce', 'render', 'publish', 'channels', 'dmbot'])
    ap.add_argument('--out', default='out')
    ap.add_argument('--storyboard')
    ap.add_argument('--audio')
    ap.add_argument('--meta')
    ap.add_argument('--url')
    ap.add_argument('--topic')
    ap.add_argument('--due', default='', help="'next' = config'teki bir sonraki yayın saati, ya da ISO zaman")
    a = ap.parse_args()
    cfg = load_cfg()
    os.makedirs(a.out, exist_ok=True)

    if a.cmd == 'dmbot':
        from .dmbot import run, run_loop
        minutes = int(os.environ.get('DM_LOOP_MINUTES', '0') or 0)
        if minutes > 0:
            run_loop(cfg, minutes, int(os.environ.get('DM_INTERVAL_SECONDS', '180')))
        else:
            run(cfg)
        return

    if a.cmd == 'channels':
        from .publish import channels
        for c in channels():
            print(f"{c['service']:12s} {c.get('displayName') or c['name']:30s} id={c['id']} paused={c['isQueuePaused']}")
        return

    if a.cmd == 'render':
        sb = json.load(open(a.storyboard, encoding='utf-8'))
        vid = dt.date.today().isoformat() + '-' + slug(sb.get('title', 'test'))
        mp4, meta = do_render(sb, a.audio, a.out, cfg, vid)
        print(mp4)
        return

    if a.cmd == 'produce':
        from .llm import make_storyboard, tts
        topic, st = (a.topic, None) if a.topic else pick_topic(cfg)
        print('Konu:', topic)
        sb = make_storyboard(topic, cfg)
        vid = dt.date.today().isoformat() + '-' + slug(sb.get('title', topic))
        json.dump(sb, open(os.path.join(a.out, f'{vid}.storyboard.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        text = '\n'.join(s['say'] for s in sb['segments'])
        wav = os.path.join(a.out, f'{vid}.wav')
        tts(text, cfg, wav)
        mp4, meta = do_render(sb, wav, a.out, cfg, vid)
        meta['topic'] = topic
        json.dump(meta, open(os.path.join(a.out, f'{vid}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        if st is not None:
            save_state(st, topic)
        with open(os.environ.get('GITHUB_OUTPUT', os.devnull), 'a') as gh:
            gh.write(f'id={vid}\n')
        print('Hazır:', mp4, f"({meta['duration']} sn)")
        return

    if a.cmd == 'publish':
        from .publish import publish
        meta = json.load(open(a.meta, encoding='utf-8'))
        due = next_slot(cfg) if a.due == 'next' else (a.due or None)
        print('Yayın zamanı:', due or 'hemen')
        res = publish(meta, cfg, a.url, due)
        for svc, r in res:
            print(svc, r)
        if any(r.startswith('HATA') for _, r in res):
            raise SystemExit(1)


if __name__ == '__main__':
    main()
