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


_MODELS_CACHE = None


def available_models():
    """Model names (without 'models/') that support generateContent, newest first."""
    global _MODELS_CACHE
    if _MODELS_CACHE is not None:
        return _MODELS_CACHE
    names, tok = [], None
    try:
        for _ in range(10):
            r = requests.get('https://generativelanguage.googleapis.com/v1beta/models',
                             params={'key': _key(), 'pageSize': 200, **({'pageToken': tok} if tok else {})}, timeout=60)
            js = r.json()
            for m in js.get('models', []):
                if 'generateContent' in m.get('supportedGenerationMethods', ['generateContent']):
                    names.append(m['name'].split('/', 1)[-1])
            tok = js.get('nextPageToken')
            if not tok:
                break
    except Exception as e:  # noqa
        print('Model listesi alınamadı:', e)

    def ver(n):
        m = re.search(r'(\d+(?:\.\d+)?)', n)
        return float(m.group(1)) if m else 0
    _MODELS_CACHE = sorted(set(names), key=ver, reverse=True)
    return _MODELS_CACHE


def pick_models(preferred, kind):
    """preferred list + discovered models of the given kind ('text' or 'tts')."""
    av = available_models()
    out = [m for m in preferred if not av or m in av]
    bad = ('image', 'live', 'embedding', 'audio', 'native', 'veo', 'imagen', 'robotics', 'computer')
    for m in av:
        is_tts = 'tts' in m
        if kind == 'tts' and is_tts and m not in out:
            out.append(m)
        if kind == 'text' and not is_tts and 'gemini' in m and 'flash' in m and not any(b in m for b in bad) and m not in out:
            out.append(m)
    return out or preferred


class GeminiError(RuntimeError):
    def __init__(self, msg, status):
        super().__init__(msg)
        self.status = status


def _post(model, body, tries=6, _hops=0):
    url = API.format(model=model)
    last, status = None, None
    for i in range(tries):
        try:
            r = requests.post(url, params={'key': _key()}, json=body, timeout=300)
        except requests.exceptions.RequestException as e:
            last, status = f'bağlantı/zaman aşımı: {e}', 'timeout'
            print(f'{model}: {last} — tekrar deneniyor')
            if i >= 1:
                break
            continue
        if r.status_code == 200:
            return r.json()
        status = r.status_code
        last = f'{r.status_code}: {r.text[:600]}'
        if r.status_code == 404 and _hops < 2:
            m = re.search(r'use models/([\w.\-]+)', r.text)
            if m and m.group(1) != model:
                print(f'Model {model} kullanılamıyor, {m.group(1)} deneniyor')
                return _post(m.group(1), body, tries, _hops + 1)
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(90, 8 * (2 ** i)))
            continue
        break
    raise GeminiError(f'Gemini hatası ({model}) {last}', status)


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
- "stat" sahnesini SADECE "say" metninde açıkça geçen bir sayı için kullan; yüzde artış, oran, kullanıcı sayısı UYDURMA.

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
    models = pick_models([cfg['models']['text']] + cfg['models'].get('text_fallbacks', []), 'text')[:5]
    print('Senaryo modelleri:', models)
    gen_variants = [
        {'responseMimeType': 'application/json', 'temperature': 0.9, 'thinkingConfig': {'thinkingLevel': 'low'}},
        {'responseMimeType': 'application/json', 'temperature': 0.9, 'thinkingConfig': {'thinkingBudget': 512}},
        {'responseMimeType': 'application/json', 'temperature': 0.9},
    ]
    errors = []
    for model in models:
        for gc in gen_variants:
            body = {'contents': [{'role': 'user', 'parts': [{'text': prompt}]}], 'generationConfig': gc}
            try:
                js = _post(model, body, tries=5)
            except GeminiError as e:
                errors.append(str(e)[:300])
                if e.status == 400:
                    continue  # bu model bu ayarı desteklemiyor, sıradakini dene
                break  # zaman aşımı/404 vb: sonraki modele geç
            parts = js['candidates'][0]['content']['parts']
            txt = ''.join(p.get('text', '') for p in parts if not p.get('thought'))
            txt = txt.strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip()
            try:
                return validate(json.loads(txt), cfg)
            except Exception as e:  # noqa
                errors.append(f'geçersiz storyboard: {e}')
                print('Storyboard geçersiz, tekrar deneniyor:', e)
    print('\n'.join(errors[-6:]))
    raise RuntimeError('Geçerli storyboard üretilemedi')


_NUM_WORDS = {'bir': 1, 'iki': 2, 'üç': 3, 'dört': 4, 'beş': 5, 'altı': 6, 'yedi': 7, 'sekiz': 8, 'dokuz': 9, 'on': 10,
              'yirmi': 20, 'otuz': 30, 'kırk': 40, 'elli': 50, 'altmış': 60, 'yetmiş': 70, 'seksen': 80, 'doksan': 90,
              'yüz': 100, 'bin': 1000, 'milyon': 10 ** 6}


def _number_in_text(value, text):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return False
    t = text.lower()
    digits = [float(x.replace(',', '.')) for x in re.findall(r'\d+(?:[.,]\d+)?', t)]
    if any(abs(d - v) < 1e-6 for d in digits):
        return True
    words = re.findall(r'[a-zçğıöşü]+', t)
    total, cur = 0, 0
    vals = set()
    for w in words:
        if w in _NUM_WORDS:
            n = _NUM_WORDS[w]
            if n >= 100:
                cur = max(cur, 1) * n
            else:
                cur += n
            vals.add(cur)
        else:
            if cur:
                total = cur
                vals.add(total)
            cur = 0
    return v in vals or (v >= 1000 and v / 1000 in vals)


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
        if tp == 'stat' and not _number_in_text(params.get('value'), say + ' ' + ' '.join(caps)):
            # sayı seslendirmede geçmiyorsa uydurma istatistik riski: düz metne çevir
            print('stat sahnesi metinde geçmeyen sayı içeriyor, bigtext yapıldı:', params.get('value'))
            tp = 'bigtext'
            params = {'lines': [str(params.get('label') or caps[0].replace('*', ''))[:28]]}
        if tp == 'bigtext' and not params.get('lines'):
            params['lines'] = [caps[0].replace('*', '')[:30]]
        out.append({'say': say, 'captions': caps, 'scene': {'type': tp, 'params': params}})
    # kapanış sahnesi her zaman config'teki sabit tasarım
    out[-1]['scene'] = {'type': 'cta', 'params': dict(cfg['cta']['scene'])}
    words = sum(len(s['say'].split()) for s in out)
    if words > 200:
        raise ValueError(f'metin çok uzun ({words} kelime)')
    sb['segments'] = out
    sb.setdefault('hashtags', [])
    sb.setdefault('tools', [])
    return sb


def _voice_cfgs(name):
    yield {'voiceConfig': {'voice': name}}
    yield {'voiceConfig': {'prebuiltVoiceConfig': {'voiceName': name}}}


def tts(text, cfg, out_wav):
    """Synthesize the full script in one call; writes a mono WAV and returns its path."""
    import io
    import wave
    style = cfg['voice'].get('style', '')
    voices = [cfg['voice']['name']] + [v for v in cfg['voice'].get('fallbacks', []) if v != cfg['voice']['name']]
    models = pick_models([cfg['models']['tts']] + cfg['models'].get('tts_fallbacks', []), 'tts')[:4]
    print('Seslendirme modelleri:', models)
    errors = []
    for model in models:
        for voice in voices:
            for sc in _voice_cfgs(voice):
                body = {
                    'contents': [{'role': 'user', 'parts': [{'text': (style + '\n' if style else '') + text}]}],
                    'generationConfig': {'responseModalities': ['AUDIO'], 'speechConfig': sc},
                }
                try:
                    js = _post(model, body, tries=4)
                except GeminiError as e:
                    errors.append(str(e)[:300])
                    if e.status in (400, 404, 'timeout'):
                        continue
                    raise
                part = js['candidates'][0]['content']['parts'][0]['inlineData']
                data = base64.b64decode(part['data'])
                if data[:4] == b'RIFF':
                    with open(out_wav, 'wb') as f:
                        f.write(data)
                    # normalise to plain 16-bit PCM WAV for the renderer
                    try:
                        with wave.open(out_wav) as w:
                            w.getnframes()
                    except Exception:
                        import subprocess
                        tmp = out_wav + '.src.wav'
                        os.replace(out_wav, tmp)
                        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', tmp, '-ac', '1', '-ar', '24000',
                                        '-c:a', 'pcm_s16le', out_wav], check=True)
                else:
                    rate = 24000
                    m = re.search(r'rate=(\d+)', part.get('mimeType', ''))
                    if m:
                        rate = int(m.group(1))
                    with wave.open(out_wav, 'wb') as w:
                        w.setnchannels(1)
                        w.setsampwidth(2)
                        w.setframerate(rate)
                        w.writeframes(data)
                print(f'Seslendirme: model={model} ses={voice}')
                return out_wav
    raise RuntimeError('Seslendirme başarısız:\n' + '\n'.join(errors[-6:]))


TOPIC_PROMPT = """Türkçe "yapay zekâ araçları ve otomasyon" temalı kısa video kanalı için YENİ bir video konusu öner.
Daha önce işlenenler: {history}
Konu somut, faydalı ve merak uyandırıcı olsun (örn. bir aracın az bilinen bir kullanımı, bir iş akışı, bir taktik).
{extra}
Sadece tek satır konu cümlesi yaz."""


def new_topic(history, cfg):
    body = {'contents': [{'role': 'user', 'parts': [{'text': TOPIC_PROMPT.format(
        history='; '.join(history[-40:]) or 'yok', extra=cfg.get('topic_hint', ''))}]}],
        'generationConfig': {'temperature': 1.0, 'thinkingConfig': {'thinkingLevel': 'low'}}}
    js = _post(cfg['models']['text'], body)
    return js['candidates'][0]['content']['parts'][0]['text'].strip().split('\n')[0]
