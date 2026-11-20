"""Telegram'dan gelen videoyu Türkçe, özgün bir videoya dönüştürüp Buffer'dan yayınlar.

Akış: Telegram botu → video indir → Gemini videoyu izler, Türkçe yeniden anlatım + kurgu planı yazar →
Gemini TTS seslendirme → ffmpeg kurgu (kesme, hız, zoom, renk, gerekirse aynalama, 9:16, başlık, altyazı,
orijinal ses kısık) → media dalı (herkese açık link) → Buffer (shareNow) → sonuç Telegram'a.

python -m studio.main remake-bot          # botu çalıştırır (REMAKE_LOOP_MINUTES kadar açık kalır)
python -m studio.main remake --video x.mp4 --out out [--note "..."] [--no-publish]
"""
import base64
import datetime as dt
import json
import mimetypes
import os
import random
import re
import subprocess
import time

import requests

from .llm import GeminiError, _key, _post, pick_models, tts

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, 'assets', 'fonts')
OWNER_FILE = os.path.join(ROOT, 'content', 'telegram.json')
MAX_SECONDS = 170  # YouTube Shorts 3 dk sınırının altında kal


# ---------------------------------------------------------------- yardımcılar
def sh(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(f'Komut başarısız: {" ".join(cmd[:6])}...\n{r.stderr[-1500:]}')
    return r.stdout


def probe(path):
    js = json.loads(sh(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', path]))
    v = next((s for s in js['streams'] if s['codec_type'] == 'video'), None)
    if not v:
        raise RuntimeError('Dosyada video yok')
    rot = 0
    for sd in v.get('side_data_list', []) or []:
        if 'rotation' in sd:
            rot = abs(int(float(sd['rotation'])))
    w, h = int(v['width']), int(v['height'])
    if rot in (90, 270):
        w, h = h, w
    return {'w': w, 'h': h, 'dur': float(js['format'].get('duration') or v.get('duration') or 0),
            'audio': any(s['codec_type'] == 'audio' for s in js['streams'])}


def wav_seconds(path):
    return float(json.loads(sh(['ffprobe', '-v', 'error', '-show_format', '-of', 'json', path]))['format']['duration'])


def slug(s):
    import unicodedata
    s = unicodedata.normalize('NFKD', s.replace('ı', 'i')).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-zA-Z0-9]+', '-', s).strip('-').lower()[:40] or 'video'


# ---------------------------------------------------------------- Gemini: videoyu izle, plan yaz
def upload_to_gemini(path):
    mime = mimetypes.guess_type(path)[0] or 'video/mp4'
    size = os.path.getsize(path)
    r = requests.post('https://generativelanguage.googleapis.com/upload/v1beta/files', params={'key': _key()},
                      headers={'X-Goog-Upload-Protocol': 'resumable', 'X-Goog-Upload-Command': 'start',
                               'X-Goog-Upload-Header-Content-Length': str(size),
                               'X-Goog-Upload-Header-Content-Type': mime, 'Content-Type': 'application/json'},
                      json={'file': {'display_name': os.path.basename(path)}}, timeout=60)
    r.raise_for_status()
    up = r.headers.get('x-goog-upload-url') or r.headers.get('X-Goog-Upload-URL')
    with open(path, 'rb') as f:
        r = requests.post(up, headers={'X-Goog-Upload-Offset': '0', 'X-Goog-Upload-Command': 'upload, finalize',
                                       'Content-Length': str(size)}, data=f, timeout=600)
    r.raise_for_status()
    info = r.json()['file']
    for _ in range(60):  # video işlenene kadar bekle
        if info.get('state') == 'ACTIVE':
            return info, mime
        if info.get('state') == 'FAILED':
            raise RuntimeError('Gemini videoyu işleyemedi')
        time.sleep(5)
        info = requests.get(f"https://generativelanguage.googleapis.com/v1beta/{info['name']}",
                            params={'key': _key()}, timeout=60).json()
    raise RuntimeError('Gemini video işleme zaman aşımı')


def delete_gemini_file(info):
    try:
        requests.delete(f"https://generativelanguage.googleapis.com/v1beta/{info['name']}", params={'key': _key()}, timeout=30)
    except Exception:  # noqa
        pass


PLAN_PROMPT = """Sen Türkçe kısa video (Instagram Reels / YouTube Shorts) editörü ve seslendirme metni yazarısın.
Ekteki videoyu baştan sona izle ve dinle. Bu videodan Türkçe, ÖZGÜN bir kısa video yapacağız: görüntü yeniden kurgulanacak,
orijinal ses çok kısılacak ve üstüne senin yazacağın Türkçe anlatım okunacak.

Video süresi: {dur:.1f} saniye.
{note}
GÖREV:
1) Videonun en ilgi çekici, akıcı bölümünü seç ("kes_bas", "kes_son" saniye). Başta/sonda boş, sıkıcı, logo/outro kısmı
   varsa at. Seçilen bölüm en az {minlen:.0f} sn, en fazla {maxlen:.0f} sn olsun. Video zaten kısa ve iyiyse neredeyse tamamını al.
2) Seçtiğin bölüm için Türkçe anlatım yaz ("seslendirme"):
   - Birebir çeviri YAPMA. Olanı kendi cümlelerinle, yorum katarak, merak uyandıran bir dille yeniden anlat.
     Videoda konuşma varsa ana fikrini aktar ama kelimesi kelimesine çevirme.
   - İlk cümle güçlü bir kanca olsun (en fazla 10 kelime; "selam", "bu videoda" gibi ısınma YOK).
   - Uzunluk: yaklaşık {words} kelime (okunduğunda seçtiğin bölümün süresini aşmasın).
   - Sade, akıcı, konuşma dili. Sayıları okunuşuyla yaz ("üç", "yüzde elli"). Emoji, URL, kısaltma YOK.
   - Videoda görünmeyen/duyulmayan bilgi, uydurma rakam, uydurma isim YAZMA. Emin değilsen genel konuş.
   - Hakaret, küfür, kişiler hakkında asılsız iddia YOK.
3) "baslik": videonun üstünde duracak kısa Türkçe başlık (en fazla 38 karakter, merak uyandıran, emoji yok).
4) "yazi_var": Videoda okunabilir yazı, logo, skor tablosu, rakam vb. var mı? (true/false) — varsa görüntü aynalanmayacak.
5) "youtube_title": en fazla 90 karakter, merak uyandıran Türkçe başlık (1 emoji olabilir).
6) "aciklama": Instagram/YouTube açıklaması: ilk satır en fazla 120 karakter ve konunun anahtar kelimesini içersin,
   sonra 1-2 kısa cümle. "Takip et", "beğen" gibi çağrılar YAZMA.
7) "hashtags": konuyla ilgili 3-5 Türkçe etiket.

ÇIKTI: Sadece şu JSON:
{{"ozet": "videoda ne oluyor (1-2 cümle)", "kes_bas": 0.0, "kes_son": {dur:.1f}, "yazi_var": false,
 "baslik": "...", "seslendirme": "...", "youtube_title": "...", "aciklama": "...", "hashtags": ["#..."]}}"""


def make_plan(video, info_v, cfg, note=''):
    dur = info_v['dur']
    maxlen = min(dur, MAX_SECONDS)
    minlen = min(maxlen, max(6.0, dur * 0.5))
    rate = float(cfg.get('yeniden_uretim', {}).get('kelime_saniye', 2.1))
    words = max(12, int(min(dur, maxlen) * rate * 0.9))
    note = f'KULLANICININ NOTU (buna uy): {note}\n' if note else ''
    prompt = PLAN_PROMPT.format(dur=dur, minlen=minlen, maxlen=maxlen, words=words, note=note)

    finfo, mime = None, 'video/mp4'
    try:
        finfo, mime = upload_to_gemini(video)
        vpart = {'file_data': {'mime_type': mime, 'file_uri': finfo['uri']}}
    except Exception as e:  # noqa
        print('Dosya yükleme başarısız, video doğrudan gönderilecek:', e)
        if os.path.getsize(video) > 18 * 1024 * 1024:
            raise
        vpart = {'inline_data': {'mime_type': mime, 'data': base64.b64encode(open(video, 'rb').read()).decode()}}

    models = pick_models([cfg['models']['text']] + cfg['models'].get('text_fallbacks', []), 'text')[:5]
    print('Plan modelleri:', models)
    gen_variants = [
        {'responseMimeType': 'application/json', 'temperature': 0.8, 'thinkingConfig': {'thinkingLevel': 'low'}},
        {'responseMimeType': 'application/json', 'temperature': 0.8},
    ]
    errors = []
    try:
        for model in models:
            for gc in gen_variants:
                body = {'contents': [{'role': 'user', 'parts': [vpart, {'text': prompt}]}], 'generationConfig': gc}
                try:
                    js = _post(model, body, tries=5)
                except GeminiError as e:
                    errors.append(str(e)[:300])
                    if e.status == 400:
                        continue
                    break
                try:
                    parts = js['candidates'][0]['content']['parts']
                    txt = ''.join(p.get('text', '') for p in parts if not p.get('thought')).strip()
                    txt = txt.removeprefix('```json').removeprefix('```').removesuffix('```').strip()
                    return validate_plan(json.loads(txt), info_v)
                except Exception as e:  # noqa
                    errors.append(f'geçersiz plan: {e}')
                    print('Plan geçersiz, tekrar deneniyor:', e)
    finally:
        if finfo:
            delete_gemini_file(finfo)
    print('\n'.join(errors[-6:]))
    raise RuntimeError('Gemini video planı üretemedi')


def validate_plan(p, info_v):
    dur = info_v['dur']
    a = max(0.0, min(float(p.get('kes_bas') or 0), max(0.0, dur - 3)))
    b = float(p.get('kes_son') or dur)
    b = min(dur, b if b > a + 3 else dur)
    if b - a > MAX_SECONDS:
        b = a + MAX_SECONDS
    say = re.sub(r'\s+', ' ', str(p.get('seslendirme', ''))).strip()
    if len(say.split()) < 5:
        raise ValueError('seslendirme boş/çok kısa')
    p.update({'kes_bas': round(a, 2), 'kes_son': round(b, 2), 'seslendirme': say,
              'baslik': str(p.get('baslik', '')).strip()[:60], 'yazi_var': bool(p.get('yazi_var', True))})
    p['hashtags'] = [h if str(h).startswith('#') else '#' + str(h) for h in (p.get('hashtags') or [])][:5]
    return p


# ---------------------------------------------------------------- altyazı (ASS)
def _chunks(text, max_chars=22):
    words, out, cur = text.split(), [], ''
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            out.append(cur)
            cur = w
        else:
            cur = (cur + ' ' + w).strip()
        if re.search(r'[.!?…]$', w) and len(cur) > 12:
            out.append(cur)
            cur = ''
    if cur:
        out.append(cur)
    return out


def _ts(t):
    t = max(0.0, t)
    return f'{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}'


def _ass_escape(s):
    return s.replace('\\', '\\\\').replace('{', '(').replace('}', ')').replace('\n', ' ')


def write_ass(path, title, narration, start, speech_len, total):
    """Başlık tüm video boyunca üstte; altyazılar seslendirmeye karakter oranıyla yayılır."""
    chunks = _chunks(narration)
    weights = [len(c) + 4 for c in chunks]
    tot_w = sum(weights) or 1
    t = start
    lines = []
    for c, w in zip(chunks, weights):
        d = speech_len * w / tot_w
        lines.append(f'Dialogue: 0,{_ts(t)},{_ts(t + d - 0.03)},Alt,,0,0,0,,{_ass_escape(c.replace('i', 'İ').upper())}')
        t += d
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Baslik,Inter ExtraBold,66,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,3,18,0,8,70,70,190,1
Style: Alt,Inter ExtraBold,70,&H0000E5FF,&H0000E5FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,3,2,80,80,520,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    body = []
    if title:
        body.append(f'Dialogue: 1,{_ts(0)},{_ts(total)},Baslik,,0,0,0,,{_ass_escape(title)}')
    open(path, 'w', encoding='utf-8').write(head + '\n'.join(body + lines) + '\n')


# ---------------------------------------------------------------- kurgu (ffmpeg)
def render(video, info_v, plan, narr_wav, out_mp4, cfg, workdir):
    rc = cfg.get('yeniden_uretim', {})
    speed = float(rc.get('hiz', 1.06))
    zoom = float(rc.get('zoom', 1.07))
    duck = float(rc.get('orijinal_ses', 0.12))
    a, b = plan['kes_bas'], plan['kes_son']
    vlen = (b - a) / speed
    flip = (not plan.get('yazi_var', True)) and rc.get('aynala', True)

    # seslendirme süresini videoya uydur (gerekirse en fazla %22 hızlandır)
    alen = wav_seconds(narr_wav)
    lead = 0.35
    tempo = 1.0
    if alen + lead > vlen:
        tempo = min(1.22, (alen + lead) / vlen)
    spoken = alen / tempo
    total = max(vlen, spoken + lead + 0.4)  # yine uzunsa son kare dondurulur
    pad = max(0.0, total - vlen)

    ass = os.path.join(workdir, 'alt.ass')
    write_ass(ass, plan.get('baslik', ''), plan['seslendirme'], lead, spoken, total)

    hue = random.uniform(-6, 6)
    sat = random.uniform(1.08, 1.18)
    con = random.uniform(1.03, 1.08)
    base = (f"[0:v]trim=start={a}:end={b},setpts=(PTS-STARTPTS)/{speed},"
            f"{'hflip,' if flip else ''}"
            f"crop=iw/{zoom}:ih/{zoom},eq=contrast={con:.3f}:saturation={sat:.3f}:brightness=0.01,hue=h={hue:.1f},"
            f"fps=30,format=yuv420p,split[f][g];"
            f"[g]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:3,eq=brightness=-0.12[bg];"
            f"[f]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,"
            f"{f'tpad=stop_mode=clone:stop_duration={pad:.2f},' if pad > 0.01 else ''}"
            f"subtitles=filename='{ass}':fontsdir='{FONTS}',setsar=1[v]")
    narr = f"[1:a]aresample=48000,atempo={tempo:.4f},adelay={int(lead * 1000)}:all=1,volume=1.0[n]"
    if info_v['audio']:
        orig = (f"[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS,atempo={speed},aresample=48000,"
                f"volume={duck}[o]")
        mix = f"{orig};{narr};[o][n]amix=inputs=2:duration=longest:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]"
    else:
        mix = f"{narr};[n]loudnorm=I=-14:TP=-1.5:LRA=11[a]"
    cmd = ['ffmpeg', '-v', 'error', '-y', '-i', video, '-i', narr_wav,
           '-filter_complex', base + ';' + mix, '-map', '[v]', '-map', '[a]',
           '-t', f'{total:.2f}', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21', '-pix_fmt', 'yuv420p',
           '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-movflags', '+faststart', out_mp4]
    sh(cmd)
    return round(total, 2), {'tempo': round(tempo, 3), 'aynalama': flip, 'kesit': [a, b]}


# ---------------------------------------------------------------- tek video
def remake(video, out, cfg, note=''):
    os.makedirs(out, exist_ok=True)
    info_v = probe(video)
    print('Video:', info_v)
    if info_v['dur'] < 3:
        raise RuntimeError('Video çok kısa (3 saniyeden az)')
    plan = make_plan(video, info_v, cfg, note)
    print('Plan:', json.dumps(plan, ensure_ascii=False))
    vid = dt.datetime.now(dt.timezone(dt.timedelta(hours=3))).strftime('%Y-%m-%d-%H%M') + '-tr-' + slug(plan.get('baslik') or 'video')
    wav = os.path.join(out, f'{vid}.wav')
    tts(plan['seslendirme'], cfg, wav)
    mp4 = os.path.join(out, f'{vid}.mp4')
    duration, edit = render(video, info_v, plan, wav, mp4, cfg, out)
    tags = ' '.join(plan['hashtags'])
    cap = plan.get('aciklama', '').strip()
    yt_tags = tags if '#shorts' in tags.lower() else (tags + ' #shorts').strip()
    meta = {'id': vid, 'title': plan.get('baslik') or vid,
            'youtube_title': (plan.get('youtube_title') or plan.get('baslik') or 'Video')[:95],
            'instagram_text': '\n\n'.join(x for x in [cap, tags] if x)[:2150],
            'youtube_text': '\n\n'.join(x for x in [cap, yt_tags] if x)[:4900],
            'duration': duration, 'plan': plan, 'edit': edit, 'source': 'telegram'}
    json.dump(meta, open(os.path.join(out, f'{vid}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('Hazır:', mp4, duration, 'sn', edit)
    return mp4, meta


# ---------------------------------------------------------------- media dalı + Buffer
def push_media(mp4, meta_path):
    repo = os.environ.get('GITHUB_REPOSITORY', 'mendaxyazilim/icerik-otomasyonu')
    remote = f"https://x-access-token:{os.environ['GH_TOKEN']}@github.com/{repo}.git"
    d = os.path.join('/tmp', 'media-' + str(int(time.time())))
    for attempt in range(3):
        subprocess.run(['rm', '-rf', d])
        if subprocess.run(['git', 'clone', '-q', '--depth', '1', '--branch', 'media', remote, d]).returncode != 0:
            os.makedirs(d)
            sh(['git', 'init', '-q', '-b', 'media'], cwd=d)
            sh(['git', 'remote', 'add', 'origin', remote], cwd=d)
        sh(['cp', mp4, meta_path, d])
        files = sorted(f for f in os.listdir(d) if f.endswith('.mp4'))
        for f in files[:-30]:  # en yeni 30 video kalsın (günlük-video ile aynı kural)
            for x in (f, f[:-4] + '.json'):
                if os.path.exists(os.path.join(d, x)):
                    os.remove(os.path.join(d, x))
        sh(['git', 'checkout', '-q', '--orphan', 'yeni'], cwd=d)
        sh(['git', 'add', '-A'], cwd=d)
        sh(['git', '-c', 'user.name=icerik-bot', '-c', 'user.email=icerik-bot@users.noreply.github.com',
            'commit', '-q', '-m', 'media: ' + os.path.basename(mp4)], cwd=d)
        if subprocess.run(['git', 'push', '-q', '-f', 'origin', 'yeni:media'], cwd=d).returncode == 0:
            return f"https://raw.githubusercontent.com/{repo}/media/{os.path.basename(mp4)}"
        time.sleep(5)
    raise RuntimeError('Video media dalına yüklenemedi')


def publish_remake(meta, cfg, url):
    from .publish import publish
    rc = cfg.get('yeniden_uretim', {})
    c = dict(cfg)
    c['publish'] = dict(cfg['publish'])
    c['publish']['services'] = rc.get('services') or cfg['publish']['services']
    c['publish']['mode'] = 'shareNow'
    if rc.get('youtube_category'):
        c['publish']['youtube_category'] = rc['youtube_category']
    # bağlantı herkese açık olsun diye kısa bekle, sonra iste
    for _ in range(12):
        try:
            if requests.head(url, timeout=20, allow_redirects=True).status_code == 200:
                break
        except Exception:  # noqa
            pass
        time.sleep(5)
    return publish(meta, c, url)


# ---------------------------------------------------------------- Telegram botu
class TG:
    def __init__(self, token):
        self.base = f'https://api.telegram.org/bot{token}'
        self.fbase = f'https://api.telegram.org/file/bot{token}'

    def call(self, method, http_timeout=70, **params):
        r = requests.post(f'{self.base}/{method}', json=params, timeout=http_timeout)
        js = r.json()
        if not js.get('ok'):
            raise RuntimeError(f'Telegram {method}: {js.get("description")}')
        return js['result']

    def send(self, chat, text):
        try:
            return self.call('sendMessage', chat_id=chat, text=text[:4000], disable_web_page_preview=True)
        except Exception as e:  # noqa
            print('Telegram mesajı gönderilemedi:', e)

    def send_video(self, chat, path, caption=''):
        try:
            if os.path.getsize(path) > 49 * 1024 * 1024:
                return
            with open(path, 'rb') as f:
                requests.post(f'{self.base}/sendVideo', data={'chat_id': chat, 'caption': caption[:1000],
                                                             'supports_streaming': 'true'},
                              files={'video': f}, timeout=300)
        except Exception as e:  # noqa
            print('Telegram videosu gönderilemedi:', e)

    def download(self, file_id, dest):
        f = self.call('getFile', file_id=file_id)
        r = requests.get(f"{self.fbase}/{f['file_path']}", timeout=300)
        r.raise_for_status()
        open(dest, 'wb').write(r.content)
        return dest


def _owner():
    env = (os.environ.get('TELEGRAM_CHAT_ID') or '').strip()
    if env:
        return env
    if os.path.exists(OWNER_FILE):
        return str(json.load(open(OWNER_FILE)).get('chat_id', '')) or None
    return None


def _save_owner(chat_id, name):
    os.makedirs(os.path.dirname(OWNER_FILE), exist_ok=True)
    json.dump({'chat_id': chat_id, 'name': name}, open(OWNER_FILE, 'w'), ensure_ascii=False)
    # depoya kaydet ki sonraki çalışmalar da bilsin
    subprocess.run(['git', 'add', OWNER_FILE], cwd=ROOT)
    subprocess.run(['git', '-c', 'user.name=icerik-bot', '-c', 'user.email=icerik-bot@users.noreply.github.com',
                    'commit', '-q', '-m', 'Telegram bot sahibi kaydedildi [skip ci]'], cwd=ROOT)
    subprocess.run(['git', 'pull', '-q', '--rebase', 'origin', 'main'], cwd=ROOT)
    subprocess.run(['git', 'push', '-q'], cwd=ROOT)


def _video_of(msg):
    if msg.get('video'):
        return msg['video']
    doc = msg.get('document') or {}
    if (doc.get('mime_type') or '').startswith('video/'):
        return doc
    if msg.get('animation'):
        return msg['animation']
    return None


HELP = ('Merhaba! Bana bir video gönder; Türkçe anlatımlı, yeniden kurgulanmış bir versiyonunu hazırlayıp '
        'Buffer üzerinden hesaplarında paylaşırım.\n\n'
        '• Videonun açıklamasına not yazabilirsin (örn. "daha esprili anlat", "saat detayına odaklan").\n'
        '• Dosya en fazla 20 MB olmalı (Telegram bot sınırı).\n'
        '• Bir video 3-8 dakikada hazır olur, bitince sana gönderirim.')


def handle(tg, msg, cfg, owner):
    chat = str(msg['chat']['id'])
    if owner and chat != owner:
        tg.send(chat, 'Bu bot özel bir bot.')
        return owner
    if not owner:
        owner = chat
        _save_owner(chat, (msg.get('from') or {}).get('first_name', ''))
        tg.send(chat, 'Bot artık sana bağlandı ✅ Başka kimse kullanamaz.\n\n' + HELP)
        if not _video_of(msg):
            return owner
    v = _video_of(msg)
    if not v:
        tg.send(chat, HELP)
        return owner
    if (v.get('file_size') or 0) > 20 * 1024 * 1024:
        tg.send(chat, '⚠️ Video 20 MB\'tan büyük; Telegram botlar bunu indiremiyor. Biraz kısaltıp ya da '
                      'sıkıştırıp (normal "video" olarak, dosya değil) tekrar gönderir misin?')
        return owner
    note = (msg.get('caption') or '').strip()
    tg.send(chat, '🎬 Video alındı, hazırlıyorum (birkaç dakika sürer)...')
    work = os.path.join('/tmp', f"tg-{msg['message_id']}")
    os.makedirs(work, exist_ok=True)
    src = os.path.join(work, 'kaynak.mp4')
    try:
        tg.download(v['file_id'], src)
        mp4, meta = remake(src, work, cfg, note)
        meta_path = os.path.join(work, f"{meta['id']}.json")
        url = push_media(mp4, meta_path)
        if os.environ.get('REMAKE_PUBLISH', 'true').lower() == 'false':
            tg.send_video(chat, mp4, f"✅ Hazır (yayın kapalı): {meta['title']}")
            return owner
        res = publish_remake(meta, cfg, url)
        lines = '\n'.join(f'{"✅" if r.startswith("OK") else "❌"} {svc}: {r}' for svc, r in res)
        tg.send_video(chat, mp4, f"{meta['title']}\n\n{lines}")
        tg.send(chat, f"Buffer'a gönderildi:\n{lines}\n\nBaşlık: {meta['youtube_title']}")
    except Exception as e:  # noqa
        print('HATA:', repr(e))
        tg.send(chat, f'❌ Bu video hazırlanamadı: {str(e)[:600]}')
    finally:
        subprocess.run(['rm', '-rf', work])
    return owner


def run_bot(cfg, minutes):
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not token:
        raise SystemExit('TELEGRAM_BOT_TOKEN yok (GitHub Secrets).')
    tg = TG(token)
    me = tg.call('getMe')
    print('Bot:', '@' + me.get('username', ''))
    try:
        tg.call('deleteWebhook')
    except Exception:  # noqa
        pass
    owner = _owner()
    if os.environ.get('BUFFER_API_KEY'):
        try:
            from .publish import channels
            for c in channels():
                print(f"Buffer kanalı: {c['service']} | {c.get('displayName') or c['name']} | duraklatılmış={c['isQueuePaused']}")
        except Exception as e:  # noqa
            print('Buffer kanalları okunamadı:', e)
    end = time.time() + minutes * 60
    offset = None
    while time.time() < end:
        try:
            ups = tg.call('getUpdates', http_timeout=80, timeout=50, allowed_updates=['message'],
                          **({'offset': offset} if offset else {}))
        except Exception as e:  # noqa
            print('getUpdates hatası:', e)
            time.sleep(10)
            continue
        for u in ups:
            offset = u['update_id'] + 1
            # önce onayla: çökme olursa aynı video sonsuza kadar tekrar işlenmesin
            try:
                tg.call('getUpdates', offset=offset, timeout=0, limit=1)
            except Exception:  # noqa
                pass
            msg = u.get('message')
            if msg:
                owner = handle(tg, msg, cfg, owner)
    print('Süre doldu, bot kapanıyor (zamanlayıcı yenisini başlatacak).')
