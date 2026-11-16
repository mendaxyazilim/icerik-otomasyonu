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

VİDEO FORMATI (bu videonun akışı buna göre kurulsun, diğer videolardan farklı olsun):
{fmt}

KURALLAR (çok önemli):
- Sadece genel olarak bilinen, doğrulanabilir özelliklerden bahset. Fiyat, indirim, kampanya, "X gün ücretsiz",
  süreli teklif, kesin kullanıcı sayısı veya uydurma istatistik YAZMA. Emin olmadığın özelliği anlatma.
- Başka bir kişinin başarısını anlatıyorsan "bazı hesaplar/kişiler" diye genel konuş; anlatıcı kendine ait olmayan
  başarı iddia etmesin ("ben 47 bin takipçi yaptım" gibi şeyler YOK).
- Gerçek kullanıcı adı, @hesap, kişi adı geçmesin.
- KANCA (en önemli kısım, izleyici ilk 1-3 saniyede kalıyor ya da kaydırıyor):
  * İlk cümle en fazla 12 kelime; selam, "bugün size", "bu videoda" gibi ısınma cümleleri YASAK.
  * Somut bir isim/nesne/durum içersin ("Excel tablon", "yorum kutusu", "kamera karşısı"); muğlak merak ("inanamayacaksın") YOK.
  * Şu kalıplardan birini seç: karşıt görüş ("X yapıyorsan zaman kaybediyorsun"), sorun ("Her gün ne paylaşacağını düşünmekten yoruldun mu?"),
    sonuç önizlemesi ("Bu videoyu baştan sona yapay zekâ yaptı"), yanlış bilinen ("Çoğu kişi X'i yanlış kullanıyor").
  * İlk segmentin sahnesi "bigtext" olsun ve sesi kapalı izleyen de konuyu anlasın: 2-5 kelimelik net başlık.
  * Kanca neyi vaat ediyorsa video onu GERÇEKTEN versin; abartılı vaat yok.
- Toplam seslendirme 100-140 kelime (yaklaşık 40-55 saniye). 8-12 segment. Her segment bir öncekinden yeni bir şey söylesin; dolgu cümle yok.
- Her segment tek cümle (veya çok kısa iki cümle). "say" alanı sesli okunacak metindir: sayıları okunuşuyla yaz
  (örn. "yüzde altmış", "üç gün"), kısaltma/emoji/URL kullanma.
- "captions": o segmentin ekranda görünen altyazısı; 1-3 parça, her parça en fazla 42 karakter, "say" metniyle
  aynı kelimeler (sayılar rakamla yazılabilir). Her parçada 1-3 vurgulu kelimeyi *yıldız* içine al (her kelime ayrı: *kanca* *kalıpları*).
- Videoya uygun TEK kelimelik, büyük harfli bir yorum anahtar kelimesi seç ("cta_keyword"; örn. SİSTEM, ARAÇ, SES, PROMPT; en fazla 8 harf).
- Son segment kapanış çağrısıdır (metnini sistem kendisi yazar); sahnesi "cta" olmalı.
- "dm": Videonun altına İLK YORUM olarak yazılacak kısa bilgi notu (2-5 satır): videodaki adımların kısa özeti ve araç linki. Konuyla ilgili araç linklerini yer tutucuyla ver (örn. {{ELEVENLABS}}).
  DM'de olmayan bir şeyi (şablon, PDF, rehber, prompt dosyası vb.) "hazır", "ekte" diye VAAT ETME; videoda anlatılan adımları 1-3 kısa maddeyle özetleyebilirsin.
- Ardışık iki segmentte aynı sahne tipini kullanma; en az 6 farklı sahne tipi kullan.
- Sahne metinleri kısa olsun (etiketler 1-4 kelime).
- "stat" sahnesini SADECE "say" metninde açıkça geçen bir sayı için kullan; yüzde artış, oran, kullanıcı sayısı UYDURMA.
- "X kat daha hızlı", "yüzde X verim" gibi ölçülmemiş performans/sonuç iddiaları YAZMA (ne seslendirmede ne sahnede).

SAHNE TİPLERİ (type ve params):
{templates}

İLGİLİ ARAÇLAR (açıklamada geçerse yer tutucuyu kullan): {tools}

ÇIKTI: Sadece şu JSON:
{{
 "title": "dosya için kısa başlık",
 "youtube_title": "YouTube başlığı (en fazla 90 karakter, merak uyandıran, 1 emoji olabilir)",
 "caption": "Açıklama: İLK SATIR en fazla 120 karakter ve aranacak anahtar kelimeyi içersin (örn. 'Yapay zekâ ile otomatik altyazı...'), videodaki kancanın aynısı olmasın. Sonra 1-3 kısa paragraf bağlam. Konuyla ilgili araç geçiyorsa linki yer tutucuyla ver (örn. {{HIGGSFIELD}}). 'Yorumlara yaz', 'takip et', 'beğen' gibi çağrı YAZMA (sistem kendisi ekliyor).",
 "hashtags": ["#yapayzeka", "... toplam 3-5 konuyla ilgili Türkçe etiket"],
 "tools": ["açıklamada linki verilen araçların anahtarları, örn. HIGGSFIELD"],
 "cta_keyword": "SİSTEM",
 "dm": "Selam! 👋 ... {{HIGGSFIELD}} ...",
 "segments": [{{"say": "...", "captions": ["..."], "scene": {{"type": "...", "params": {{...}}}}}}]
}}"""


FORMATS = {
    'liste': "LİSTE: Kancada kaç madde olduğunu söyle ('3 şey'). Her madde ayrı segment ve ayrı sahne (list, checklist, bigtext, stat, icon'lu sahneler). Maddeler numaralı ilerlesin.",
    'once_sonra': "ÖNCE / SONRA: Önce eski, zahmetli yolu anlat (crossed, compare, crowd), sonra aracın getirdiği yeni yolu göster (app, chat, terminal, steps) ve sonucu söyle.",
    'mit': "YANLIŞ BİLİNEN: 'Çoğu kişi X sanıyor' diye başla, neden yanlış olduğunu açıkla, sonra doğrusunu adım adım göster (bigtext, crossed, compare, steps).",
    'tutorial': "ADIM ADIM: Kancada sonucu göster, sonra 3-5 net adımı tek tek anlat (steps, terminal, chat, checklist). Her adım bir segment.",
    'hata': "YAPILAN HATALAR: 'Bunu yapıyorsan dur' tarzı başla, 2-3 yaygın hatayı ve her birinin doğrusunu anlat (crossed, compare, bigtext, list).",
    'senaryo': "KULLANIM HİKÂYESİ: 'Bir içerik üreticisi düşün…' diye üçüncü şahısla başla; sorun → araçla çözüm → sonuç (crowd, chat, app, calendar, connector).",
}


def make_storyboard(topic, cfg, tool=None, fmt=None):
    affs = {k: v for k, v in cfg.get('affiliates', {}).items() if (v.get('url') or '').strip()}
    if tool and tool in affs:
        v = affs[tool]
        tools = (f'Bu video SADECE {v["name"]} hakkında ({v.get("about", "")}). Açıklamada ve DM\'de yalnızca '
                 f'{{{tool}}} yer tutucusunu kullan; başka aracın linkini verme. Aracın adını videoda net söyle.')
    else:
        tools = ', '.join(f'{k} ({v["name"]}) -> yer tutucu {{{k}}}' for k, v in affs.items())
    prompt = STORY_PROMPT.format(topic=topic, templates=TEMPLATE_DOC, tools=tools or 'yok',
                                 cta_say=cfg['cta']['say'], fmt=FORMATS.get(fmt, FORMATS['tutorial']))
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
                data = json.loads(txt)
                if tool and tool in affs:
                    data['_focus_name'] = affs[tool]['name']
                return validate(data, cfg)
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
    # anahtar kelime + sabit kapanış tasarımı
    kw = re.sub(r'[^A-ZÇĞİÖŞÜ]', '', str(sb.get('cta_keyword', '')).replace('i', 'İ').upper())[:10] or cfg['cta']['default_keyword']
    sb['cta_keyword'] = kw
    send = cfg['cta'].get('mode') == 'send'
    out[-1]['say'] = cfg['cta']['send_say'] if send else f"Yorumlara {kw} yaz, {cfg['cta']['say']}"
    params = dict(cfg['cta']['send_scene'] if send else cfg['cta']['scene'])
    if not send:
        params['word'] = kw
    focus = sb.get('_focus_name')
    if not params.get('pills') and focus:
        params['pills'] = [focus]
    out[-1]['scene'] = {'type': 'cta', 'params': params}
    out[-1]['captions'] = list(cfg['cta']['send_captions']) if send else [f'Yorumlara *{kw}* yaz']
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
    style = ''  # talimatı metne eklemiyoruz: yeni modeller bunu sesli okuyor
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


TOOL_TOPIC_PROMPT = """Türkçe kısa video kanalı için {name} hakkında YENİ bir video konusu öner.
{name}: {about}
Daha önce işlenenler: {history}
Konu, aracın gerçek ve bilinen bir özelliğini somut bir kullanım senaryosuyla anlatsın (örn. "X ile Y'yi 2 dakikada yapmak").
Fiyat, kampanya veya uydurma rakam içermesin. Sadece tek satır konu cümlesi yaz."""

TOPIC_PROMPT = """Türkçe "yapay zekâ araçları ve otomasyon" temalı kısa video kanalı için YENİ bir video konusu öner.
Daha önce işlenenler: {history}
Konu somut, faydalı ve merak uyandırıcı olsun (örn. bir aracın az bilinen bir kullanımı, bir iş akışı, bir taktik).
{extra}
Sadece tek satır konu cümlesi yaz."""


def new_topic(history, cfg, tool=None):
    if tool:
        v = cfg['affiliates'][tool]
        text = TOOL_TOPIC_PROMPT.format(name=v['name'], about=v.get('about', ''), history='; '.join(history[-40:]) or 'yok')
    else:
        text = TOPIC_PROMPT.format(history='; '.join(history[-40:]) or 'yok', extra=cfg.get('topic_hint', ''))
    body = {'contents': [{'role': 'user', 'parts': [{'text': text}]}],
        'generationConfig': {'temperature': 1.0, 'thinkingConfig': {'thinkingLevel': 'low'}}}
    js = _post(cfg['models']['text'], body)
    return js['candidates'][0]['content']['parts'][0]['text'].strip().split('\n')[0]
