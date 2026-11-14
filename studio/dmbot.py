"""Instagram yorum → DM botu.

Her çalıştığında son gönderilere bakar. Açıklamasında "Yorumlara <KELİME> yaz" geçen bir gönderiye
o kelimeyi içeren yorum yazan herkese:
  1) Instagram'ın "private reply" özelliğiyle DM gönderir (yoruma yanıt olarak, 7 gün içinde izinli),
  2) yorumun altına "DM'den gönderdim ✅" gibi bir yanıt yazar.
Aynı yoruma iki kez işlem yapmamak için, yorumun altında hesabın kendi yanıtı varsa atlar (durum dosyası gerekmez).

Gerekli: Instagram API with Instagram Login erişim anahtarı (secret IG_ACCESS_TOKEN) ve şu izinler:
instagram_business_basic, instagram_business_manage_comments, instagram_business_manage_messages.
"""
import datetime as dt
import json
import os
import random
import re
import time
import unicodedata
import requests

VERSION = 'v26.0'


def _base():
    # Instagram Login anahtarları "IG" ile başlar (graph.instagram.com);
    # Unified / Facebook Login (system-user) anahtarları graph.facebook.com ile çalışır.
    return f"https://graph.{'instagram' if _tok().startswith('IG') else 'facebook'}.com/{VERSION}"
MEDIA_BRANCH_RAW = 'https://raw.githubusercontent.com/{repo}/media/{name}'


def _tok():
    t = os.environ.get('IG_ACCESS_TOKEN')
    if not t:
        raise SystemExit('IG_ACCESS_TOKEN yok (GitHub Secrets).')
    return t


def _get(path, **params):
    params['access_token'] = _tok()
    r = requests.get(f'{_base()}/{path}', params=params, timeout=30)
    js = r.json()
    if 'error' in js:
        raise RuntimeError(f"GET {path}: {js['error'].get('message')}")
    return js


def _post(path, payload=None, **params):
    params['access_token'] = _tok()
    r = requests.post(f'{_base()}/{path}', params=params, json=payload, timeout=30)
    js = r.json()
    if 'error' in js:
        raise RuntimeError(f"POST {path}: {js['error'].get('message')}")
    return js


def norm(s):
    s = s.replace('İ', 'i').replace('I', 'ı').lower()
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return s.replace('ı', 'i')


KW_RE = re.compile(r'Yorumlara\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)\s+yaz', re.I)


def load_dm_texts():
    """keyword -> dm text, from meta files on the media branch (last videos)."""
    repo = os.environ.get('GITHUB_REPOSITORY')
    out = {}
    if not repo:
        return out
    try:
        r = requests.get(f'https://api.github.com/repos/{repo}/contents', params={'ref': 'media'}, timeout=30,
                         headers={'Authorization': f"Bearer {os.environ['GH_TOKEN']}"} if os.environ.get('GH_TOKEN') else {})
        for f in r.json():
            if isinstance(f, dict) and f.get('name', '').endswith('.json'):
                m = requests.get(MEDIA_BRANCH_RAW.format(repo=repo, name=f['name']), timeout=30).json()
                if m.get('keyword') and m.get('dm'):
                    txt = m['dm'].replace('(Bazı linkler ortaklık linkidir; üzerinden abone olursan sana ek maliyet olmadan komisyon kazanabilirim.)', '').strip()
                    out[norm(m['keyword'])] = txt
    except Exception as e:  # noqa
        print('Meta dosyaları okunamadı:', e)
    return out


def default_dm(cfg):
    lines = [cfg['dm']['default'], '']
    lines += [f"{v['name']}: {v['url']}" for v in cfg['affiliates'].values()]
    if cfg['dm'].get('disclosure'):
        lines += ['', cfg['dm']['disclosure']]
    return '\n'.join(lines)


def _try(path, **params):
    try:
        js = _get(path, **params)
        print(f'  {path}: {str(js)[:160]}')
        return js
    except RuntimeError as e:
        print(f'  {path}: {e}')
        return {}


def discover_ig_id():
    """System-user anahtarına atanmış Instagram hesabını bulmaya çalışır."""
    print('Instagram hesap kimliği aranıyor:')
    js = _try('me/accounts', fields='instagram_business_account{id,username}')
    for it in js.get('data', []):
        if it.get('instagram_business_account'):
            return it['instagram_business_account']['id']
    for path in ('me/instagram_accounts', 'me/owned_instagram_accounts'):
        js = _try(path, fields='id,username')
        if js.get('data'):
            return js['data'][0]['id']
    js = _try('me', fields='id,name,business')
    bid = (js.get('business') or {}).get('id')
    if not bid:
        bl = _try('me/businesses', fields='id,name')
        bid = (bl.get('data') or [{}])[0].get('id')
    if bid:
        for edge in ('owned_instagram_accounts', 'instagram_accounts', 'instagram_business_accounts'):
            js = _try(f'{bid}/{edge}', fields='id,username')
            if js.get('data'):
                return js['data'][0]['id']
    return None


def run(cfg):
    uid = os.environ.get('IG_USER_ID', '').strip()
    if _tok().startswith('IG'):
        me = _get('me', fields='user_id,username')
        uid = uid or me.get('user_id') or me.get('id')
    elif not uid:
        uid = discover_ig_id()
        if not uid:
            raise SystemExit('Instagram hesap kimliği bulunamadı. IG_USER_ID adlı bir GitHub değişkeni/secret ekle.')
    uname = _get(uid, fields='username').get('username')
    print(f'Hesap: @{uname}')
    dms = load_dm_texts()
    now = dt.datetime.now(dt.timezone.utc)
    max_age = dt.timedelta(days=cfg['dm'].get('max_age_days', 7))
    media = _get(f'{uid}/media', fields='id,caption,timestamp,permalink', limit=15).get('data', [])
    sent = failed = 0
    for m in media:
        cap = m.get('caption') or ''
        mk = KW_RE.search(cap)
        if not mk:
            print(f"- gönderi {m['id']} ({m.get('timestamp','')[:16]}): anahtar kelime yok, atlandı")
            continue
        kw = norm(mk.group(1))
        ts = dt.datetime.fromisoformat(m['timestamp'].replace('+0000', '+00:00'))
        if now - ts > max_age + dt.timedelta(days=1):
            continue
        comments = _get(f"{m['id']}/comments", fields='id,text,username,timestamp,from', limit=50).get('data', [])
        print(f"- gönderi {m['id']} ({m.get('timestamp','')[:16]}): kelime={kw.upper()}, {len(comments)} yorum")
        for c in comments:
            print(f"    @{c.get('username') or (c.get('from') or {}).get('username')}: {c.get('text','')[:60]!r}")
            if (c.get('username') or (c.get('from') or {}).get('username')) == uname:
                print('      → kendi hesabın, atlandı')
                continue
            if not re.search(r'(?<![a-z0-9])' + re.escape(kw) + r'(?![a-z0-9])', norm(c.get('text', ''))):
                print(f'      → "{kw.upper()}" geçmiyor, atlandı')
                continue
            cts = dt.datetime.fromisoformat(c['timestamp'].replace('+0000', '+00:00'))
            if now - cts > max_age:
                print('      → 7 günden eski, atlandı')
                continue
            reps = _get(f"{c['id']}/replies", fields='id,text,username,from').get('data', [])
            mine = [r for r in reps if (r.get('username') or (r.get('from') or {}).get('username')) == uname]
            if mine:
                print(f"      → zaten yanıtlanmış: {mine[0].get('text','')[:50]!r}")
                continue
            text = dms.get(kw) or default_dm(cfg)
            try:
                _post(f'{uid}/messages', {'recipient': {'comment_id': c['id']}, 'message': {'text': text}})
                reply = random.choice(cfg['dm']['replies_ok'])
                sent += 1
                print(f"DM gönderildi → @{c.get('username')} ({kw})")
            except RuntimeError as e:
                reply = random.choice(cfg['dm']['replies_fail'])
                failed += 1
                print(f"DM gönderilemedi → @{c.get('username')}: {e}")
            try:
                _post(f"{c['id']}/replies", message=f"@{c.get('username')} {reply}" if c.get('username') else reply)
            except RuntimeError as e:
                print('Yorum yanıtı yazılamadı:', e)
            time.sleep(random.uniform(2, 5))  # spam gibi görünmesin
    print(f'Bitti: {sent} DM gönderildi, {failed} başarısız.')


def run_loop(cfg, minutes=340, interval=180):
    """Botu uzun süre açık tutar: her `interval` saniyede bir kontrol eder."""
    end = time.time() + minutes * 60
    n = 0
    while True:
        n += 1
        print(f'=== Kontrol #{n} ({dt.datetime.now(dt.timezone.utc):%H:%M} UTC) ===', flush=True)
        try:
            run(cfg)
        except SystemExit:
            raise
        except Exception as e:  # noqa — tek bir hatada döngü durmasın
            print('Kontrol hatası:', e, flush=True)
        if time.time() + interval > end:
            break
        time.sleep(interval)
