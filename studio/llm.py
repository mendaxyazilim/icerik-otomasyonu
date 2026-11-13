"""Gemini API: storyboard (script) generation and text-to-speech."""
import base64
import json
import os
import re
import time
import requests

from .scenes import TEMPLATE_DOC, TEMPLATES

API = 'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'


def _key():
    k = os.environ.get('GEMINI_API_KEY')
    if not k:
        raise SystemExit('GEMINI_API_KEY ortam değişkeni yok (GitHub Secrets).')
    return k


def _post(model, body, tries=6):
    url = API.format(model=model)
    last = None
    for i in range(tries):
        r = requests.post(url, params={'key': _key()}, json=body, timeout=180)
        if r.status_code == 200:
            return r.json()
        last = f'{r.status_code}: {r.text[:500]}'
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(90, 8 * (2 ** i)))
            continue
        break
    raise RuntimeError(f'Gemini hatası ({model}) {last}')


STORY_PROMPT = """Sen Türkçe kısa video (Instagram Reels / YouTube Shorts) senaristisin. Kanal: yapay zekâ araçları ve otomasyon
taktikleri anlatan, yüzünü göstermeyen, 2D avatarlı bir anlatıcı. Ton: enerjik, merak uyandıran, sade Türkçe.

KONU: {topic}

KURALLAR (çok önemli):
- Sadece genel olarak bilinen, doğrulanabilir özelliklerden bahset. Fiyat, indirim, kampanya, "X gün ücretsiz",
  süreli teklif, kesin kullanıcı sayısı veya uydurma istatistik YAZMA. Emin olmadığın özelliği anlatma.
- Başka bir kişinin başarısını anlatıyorsan "bazı hesaplar/kişiler" diye genel konuş; anlatıcı kendine ait olmayan
  başarı iddia etmesin ("ben 47 bin takipçi yaptım" gibi şeyler YOK).
- Gerçek kullanıcı adı, @hesap, kişi adı geçmesin.
- İlk cümle güçlü bir kanca olsun (ilk 2 saniyede merak).
- Toplam seslendirme 120-160 kelime (yaklaşık 50-70 saniye). 8-13 segment.
- Her segment tek cümle (veya çok kısa iki cümle). "say" alanı sesli okunacak metindir: sayıları okunuşuyla yaz
  (örn. "yüzde altmış", "üç gün"), kısaltma/emoji/URL kullanma.
- "captions": o segmentin ekranda görünen altyazısı; 1-3 parça, her parça en fazla 42 karakter, "say" metniyle
  aynı kelimeler (sayılar rakamla yazılabilir). Her parçada 1-3 vurgulu kelimeyi *yıldız* içine al (her kelime ayrı: *kanca* *kalıpları*).
- Son segment kapanış çağrısıdır: "{cta_say}" anlamında bir cümle; sahnesi "cta" olmalı.
- Ardışık iki segmentte aynı sahne tipini kullanma; en az 6 farklı sahne tipi kullan.
- Sahne metinleri kısa olsun (etiketler 1-4 kelime).

SAHNE TİPLERİ (type ve params):
{templates}

İLGİLİ ARAÇLAR (açıklamada geçerse yer tutucuyu kullan): {tools}

ÇIKTI: Sadece şu JSON:
{{
 "title": "dosya için kısa başlık",
 "youtube_title": "YouTube başlığı (en fazla 90 karakter, merak uyandıran, 1 emoji olabilir)",
 "caption": "Instagram/YouTube açıklaması: 3-6 kısa paragraf, emoji olabilir. Konuyla ilgili araç geçiyorsa linki yer tutucuyla ver (örn. {{HIGGSFIELD}}). En sonda kapanış çağrısı.",
 "hashtags": ["#yapayzeka", "... 6-10 etiket"],
 "tools": ["açıklamada linki verilen araçların anahtarları, örn. HIGGSFIELD"],
 "segments": [{{"say": "...", "captions": ["..."], "scene": {{"type": "...", "params": {{...}}}}}}]
}}"""


def make_storyboard(topic, cfg):
    tools = ', '.join(f'{k} ({v["name"]}) -> yer tutucu {{{k}}}' for k, v in cfg.get('affiliates', {}).items())
    prompt = STORY_PROMPT.format(topic=topic, templates=TEMPLATE_DOC, tools=tools or 'yok',
                                 cta_say=cfg['cta']['say'])
    body = {
        'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
        'generationConfig': {'responseMimeType': 'application/json', 'temperature': 0.9},
    }
    for attempt in range(3):
        js = _post(cfg['models']['text'], body)
        txt = js['candidates'][0]['content']['parts'][0]['text']
        try:
            sb = json.loads(txt)
            return validate(sb, cfg)
        except Exception as e:  # noqa
            print('Storyboard geçersiz, tekrar deneniyor:', e)
    raise RuntimeError('Geçerli storyboard üretilemedi')


def validate(sb, cfg):
    segs = sb.get('segments') or []
    if len(segs) < 4:
        raise ValueError('çok az segment')
    out = []
    for s in segs:
        say = re.sub(r'\s+', ' ', str(s.get('say', ''))).strip()
        if not say:
            continue
        caps = [str(c).strip() for c in (s.get('captions') or []) if str(c).strip()] or [say]
        sc = s.get('scene') or {}
        tp = sc.get('type') if sc.get('type') in TEMPLATES else 'bigtext'
        params = sc.get('params') or {}
        if tp == 'bigtext' and not params.get('lines'):
            params['lines'] = [caps[0].replace('*', '')[:30]]
        out.append({'say': say, 'captions': caps, 'scene': {'type': tp, 'params': params}})
    if out[-1]['scene']['type'] != 'cta':
        out[-1]['scene'] = {'type': 'cta', 'params': dict(cfg['cta']['scene'])}
    words = sum(len(s['say'].split()) for s in out)
    if words > 200:
        raise ValueError(f'metin çok uzun ({words} kelime)')
    sb['segments'] = out
    sb.setdefault('hashtags', [])
    sb.setdefault('tools', [])
    return sb


def tts(text, cfg, out_wav):
    """Synthesize the full script in one call; returns path to a 24 kHz mono WAV."""
    import wave
    style = cfg['voice'].get('style', '')
    body = {
        'contents': [{'role': 'user', 'parts': [{'text': (style + '\n' if style else '') + text}]}],
        'generationConfig': {
            'responseModalities': ['AUDIO'],
            'speechConfig': {'voiceConfig': {'prebuiltVoiceConfig': {'voiceName': cfg['voice']['name']}}},
        },
    }
    js = _post(cfg['models']['tts'], body)
    part = js['candidates'][0]['content']['parts'][0]['inlineData']
    pcm = base64.b64decode(part['data'])
    rate = 24000
    m = re.search(r'rate=(\d+)', part.get('mimeType', ''))
    if m:
        rate = int(m.group(1))
    with wave.open(out_wav, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return out_wav


TOPIC_PROMPT = """Türkçe "yapay zekâ araçları ve otomasyon" temalı kısa video kanalı için YENİ bir video konusu öner.
Daha önce işlenenler: {history}
Konu somut, faydalı ve merak uyandırıcı olsun (örn. bir aracın az bilinen bir kullanımı, bir iş akışı, bir taktik).
{extra}
Sadece tek satır konu cümlesi yaz."""


def new_topic(history, cfg):
    body = {'contents': [{'role': 'user', 'parts': [{'text': TOPIC_PROMPT.format(
        history='; '.join(history[-40:]) or 'yok', extra=cfg.get('topic_hint', ''))}]}],
        'generationConfig': {'temperature': 1.0}}
    js = _post(cfg['models']['text'], body)
    return js['candidates'][0]['content']['parts'][0]['text'].strip().split('\n')[0]
