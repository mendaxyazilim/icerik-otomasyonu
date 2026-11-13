"""Parametric scene templates. Each template: fn(d, t, a, dur, p) where
d: D drawing context, t: local time (s), a: global alpha, dur: scene duration, p: params dict.
Content lives in the area y=330..800 (left column reaches lower; the avatar sits bottom-right)."""
import math
import numpy as np
from PIL import Image
from .core import (D, F, FS, A, eo, eback, ap, clamp, pill, phone, mini_scene, cross, stamp, faceless, icon,
                   OR, YEL, CREAM, GREY, CARD, CARD2, LINE, DARK, RED, S, ICONS)


def _s(p, k, default=''):
    v = p.get(k, default)
    return str(v) if v is not None else default


def _list(p, k, n=None):
    v = p.get(k) or []
    if isinstance(v, str):
        v = [v]
    return v[:n] if n else v


def _times(n, dur, start=0.3, tail=0.8):
    span = max(0.4, dur - start - tail)
    return [start + i * span / max(1, n) for i in range(n)]


# 1 ---------------------------------------------------------------
def bigtext(d, t, a, dur, p):
    lines = _list(p, 'lines', 3) or [_s(p, 'text', '')]
    hl = _s(p, 'highlight').lower()
    y = 470 - (len(lines) - 1) * 45
    for i, ln in enumerate(lines):
        k = eback((t - 0.15 - i * 0.25) / 0.45)
        if k <= 0:
            continue
        f = d.fit(ln, 64, 600, 'Black', True)
        col = OR if hl and hl in ln.lower() else CREAM
        d.t((360, y + i * 90 + (1 - clamp(k)) * 20), ln, f, A(col, a * clamp(k)), 'mm')
    if p.get('stamp'):
        stamp(d, _s(p, 'stamp').upper(), 360, y + len(lines) * 90 + 60, eo((t - 0.9) / 0.3), a, RED, 52, -7)


# 2 ---------------------------------------------------------------
def stat(d, t, a, dur, p):
    val = float(p.get('value', 100) or 0)
    dec = int(p.get('decimals', 0) or 0)
    c = eo((t - 0.2) / max(0.6, min(2.6, dur - 0.8)))
    v = val * c
    s = f"{v:,.{dec}f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    txt = _s(p, 'prefix') + s + _s(p, 'suffix')
    q = ap(t, 0)
    d.rr((60, 360, 660, 640), 30, fill=A(CARD, a * q), outline=A(LINE, a * q))
    ic = _s(p, 'icon', 'chart')
    d.rr((90, 390, 150, 450), 16, fill=A(OR, a * q))
    icon(d, ic if ic in ICONS else 'chart', 120, 420, 36, DARK, a * q)
    f = d.fit(txt, 104, 560, 'ExtraBold', True)
    d.t((360, 510), txt, f, A(OR, a * q), 'mm')
    lab = _s(p, 'label')
    if lab:
        d.t((360, 590), lab, d.fit(lab, 26, 560, 'Bold'), A(CREAM, a * q), 'mm')
    for i, b in enumerate(_list(p, 'badges', 3)):
        k = eback((t - 0.8 - i * 0.35) / 0.4)
        if k > 0:
            pill(d, 360, 690 + i * 56, str(b), [YEL, OR, CARD2][i % 3], DARK if i < 2 else CREAM, 18 * clamp(k) + 1, a)


# 3 ---------------------------------------------------------------
def chart(d, t, a, dur, p):
    k = eo(t / 0.4)
    x0, y0, x1, y1 = 80, 380, 640, 760
    d.rr((60, 350, 660, 790), 26, fill=A(CARD, a * k))
    d.line([(x0, y1), (x1, y1)], A(LINE, a * k), 3)
    d.line([(x0, y0), (x0, y1)], A(LINE, a * k), 3)
    pr = eo((t - 0.4) / 2.0)
    pts = []
    for i in range(61):
        u = i / 60
        if u > pr:
            break
        pts.append((x0 + (x1 - x0) * u, y1 - (y1 - y0 - 40) * (u ** 3)))
    if len(pts) > 1:
        d.line(pts, A(OR, a), 6)
    q = eback((t - 0.3) / 0.4)
    if q > 0:
        px, py = x0 + (x1 - x0) * 0.18, y1 - (y1 - y0 - 40) * 0.18 ** 3
        d.el((px - 14, py - 14, px + 14, py + 14), fill=A(YEL, a))
        pill(d, px + 90, py - 70, _s(p, 'now_label', 'ŞU AN BURADASIN'), YEL, DARK, 16 * clamp(q) + 1, a)
    if p.get('peak_label'):
        pill(d, 480, 420, _s(p, 'peak_label'), OR, DARK, 16, a * ap(t, 2.2))
    d.t((x1, y1 + 18), _s(p, 'x_label', 'zaman'), F(15, 'Medium'), A(GREY, a * k), 'rm')
    d.t((x0 + 10, y0 - 12), _s(p, 'y_label', 'erişim'), F(15, 'Medium'), A(GREY, a * k), 'lm')


# 4 ---------------------------------------------------------------
def listcards(d, t, a, dur, p):
    items = _list(p, 'items', 4)
    title = _s(p, 'title')
    y0 = 350
    if title:
        q = ap(t, 0)
        pill(d, 360, 370, title, CARD, CREAM, 18, a * q, 'Bold', outline=LINE)
        y0 = 410
    n = max(1, len(items))
    hh = min(110, (440 - (n - 1) * 14) / n)
    ts = _times(n, dur)
    for i, it in enumerate(items):
        if isinstance(it, str):
            it = {'title': it}
        k = eback((t - ts[i]) / 0.45)
        if k <= 0:
            continue
        y = y0 + i * (hh + 14)
        x0 = 60 - (1 - clamp(k)) * 80
        d.rr((x0, y, x0 + 600, y + hh), 22, fill=A(CARD, a * clamp(k)), outline=A(OR if i == 0 else LINE, a * clamp(k)))
        s = hh - 36
        d.rr((x0 + 18, y + 18, x0 + 18 + s, y + 18 + s), 14, fill=A(OR, a * clamp(k)))
        ic = it.get('icon') or ICONS[i % len(ICONS)]
        icon(d, ic if ic in ICONS else 'spark', x0 + 18 + s / 2, y + 18 + s / 2, s * 0.62, DARK, a * clamp(k))
        tt = str(it.get('title', ''))
        sub = str(it.get('sub', '') or '')
        tx = x0 + 36 + s
        if sub:
            d.t((tx, y + hh * 0.38), tt, d.fit(tt, 28, 560 - s, 'Bold'), A(CREAM, a * clamp(k)), 'lm')
            d.t((tx, y + hh * 0.7), sub, FS(19), A(GREY, a * clamp(k)), 'lm')
        else:
            d.t((tx, y + hh / 2), tt, d.fit(tt, 28, 560 - s, 'Bold'), A(CREAM, a * clamp(k)), 'lm')


# 5 ---------------------------------------------------------------
def chat(d, t, a, dur, p):
    q = eo(t / 0.35)
    user = _s(p, 'user', 'Bunu benim için yap')
    f = d.fit(user, 20, 520, 'Medium')
    tw = d.tw(user, f) + 40
    d.rr((660 - tw, 340, 660, 384), 22, fill=A(CARD2, a * q))
    d.t((660 - tw / 2, 362), user, f, A(CREAM, a * q), 'mm')
    cmd = _s(p, 'command')
    tag = _s(p, 'tag')
    q2 = eback((t - 0.4) / 0.4)
    if q2 > 0 and (cmd or tag):
        fc = F(19, 'SemiBold')
        cw = d.tw(cmd, fc) + (d.tw(tag, F(16, 'Bold')) + 50 if tag else 0) + 40
        cw = min(cw, 600)
        d.rr((60, 398, 60 + cw * clamp(q2), 438), 20, fill=A(CARD, a), outline=A(OR, a), w=2)
        if q2 > 0.7:
            d.t((80, 418), cmd, fc, A(CREAM, a), 'lm')
            if tag:
                d.t((60 + cw - 20, 418), tag, F(16, 'Bold'), A(YEL, a), 'rm')
    done_t = max(1.6, dur * 0.55)
    q3 = ap(t, 0.8)
    if q3 > 0:
        done = t >= done_t
        if done:
            d.el((60, 452, 84, 476), fill=A(OR, a * q3))
            icon(d, 'check', 72, 464, 14, DARK, a * q3)
        else:
            for k in range(8):
                ang = t * 6 + k * math.pi / 4
                cx, cy = 72 + 9 * math.cos(ang), 464 + 9 * math.sin(ang)
                d.el((cx - 2, cy - 2, cx + 2, cy + 2), fill=A(OR, a * q3 * (k + 1) / 8))
        txt = _s(p, 'done', 'Hazır') if done else _s(p, 'wait', 'Çalışıyor…')
        d.t((96, 464), txt, d.fit(txt, 18, 560, 'Medium'), A(CREAM if done else GREY, a * q3), 'lm')
    # result card: grey -> colourful mini clips
    qq = eo((t - 0.6) / 0.4)
    m = eo((t - done_t) / 0.5)
    for j in range(3):
        x = 60 + j * 205
        mini_scene(d, x, 500, 190, 280, j + 1, a * qq * (0.35 + 0.65 * m))
        if m < 1:
            d.rr((x, 500, x + 190, 780), 8, fill=A((70, 70, 72), a * qq * (1 - m) * 0.8))
    if m > 0.6 and p.get('result'):
        pill(d, 200, 745, _s(p, 'result'), DARK, CREAM, 16, a)


# 6 ---------------------------------------------------------------
def steps(d, t, a, dur, p):
    st = _list(p, 'steps', 5) or ['Adım 1']
    q = eo(t / 0.4)
    title = _s(p, 'title', 'Kurulum')
    pill(d, 195, 360, title, YEL, DARK, 17, a * q)
    px, py, pw, ph = 60, 400, 300, 560
    phone(d, px, py + (1 - q) * 40, pw, ph, a * q)
    ts = _times(len(st), dur, 0.6, 0.6)
    cur = sum(1 for x in ts if t >= x)
    sx, sw = px + 16, pw - 32
    if cur == 0:
        d.t((px + pw / 2, py + 220), _s(p, 'screen_title', 'Başlayalım'), FS(26), A(CREAM, a * q), 'mm')
    else:
        lab = str(st[cur - 1])
        d.t((sx, py + 80), f"Adım {cur}", F(15, 'Bold'), A(YEL, a), 'lm')
        for li, ln in enumerate(d.wrap(lab, F(22, 'Bold'), sw)[:3]):
            d.t((sx, py + 112 + li * 30), ln, F(22, 'Bold'), A(CREAM, a), 'lm')
        for r in range(3):
            hl = r == 1
            y = py + 230 + r * 54
            d.rr((sx, y, sx + sw, y + 44), 12, fill=A(CARD2, a), outline=A(YEL, a) if hl else None, w=2)
            d.rr((sx + 14, y + 16, sx + 14 + (sw - 60) * (0.8 - r * 0.2), y + 28), 6, fill=A(LINE, a))
        rp = clamp((t - ts[cur - 1] - 0.3) / 0.5)
        if 0 < rp < 1:
            d.el((sx + sw / 2 - 60 * rp, py + 306 - 60 * rp, sx + sw / 2 + 60 * rp, py + 306 + 60 * rp), outline=A(YEL, a * (1 - rp)), w=3)
    for i, lab in enumerate(st):
        y = 410 + i * 80
        act = cur == i + 1
        done = cur > i + 1
        col = YEL if act else (OR if done else LINE)
        d.el((380, y, 420, y + 40), fill=A(col if (act or done) else CARD, a * q), outline=A(col, a * q), w=2)
        if done:
            icon(d, 'check', 400, y + 20, 18, DARK, a * q)
        else:
            d.t((400, y + 20), str(i + 1), F(18, 'ExtraBold'), A(DARK if act else GREY, a * q), 'mm')
        lines = d.wrap(str(lab), F(17, 'Bold' if act else 'Medium'), 230)[:2]
        for li, ln in enumerate(lines):
            yy = y + 20 + (li - (len(lines) - 1) / 2) * 22
            d.t((432, yy), ln, F(17, 'Bold' if act else 'Medium'), A(CREAM if (act or done) else GREY, a * q), 'lm')


# 7 ---------------------------------------------------------------
def compare(d, t, a, dur, p):
    half = dur * 0.42
    if t < half:
        q = eo(t / 0.3) * (1 - eo((t - half + 0.25) / 0.25))
        for i in range(6):
            x = 70 + (i % 3) * 200
            y = 360 + (i // 3) * 220
            d.rr((x, y, x + 180, y + 200), 14, fill=A((70, 70, 72), a * q))
            d.el((x + 60, y + 40, x + 120, y + 100), fill=A((110, 110, 112), a * q))
            d.rr((x + 30, y + 120, x + 150, y + 140), 8, fill=A((100, 100, 102), a * q))
        stamp(d, _s(p, 'bad', 'ÖZENSİZ').upper(), 360, 580, eo((t - 0.6) / 0.3) * q, a, RED, 60, -10)
    else:
        lt = t - half
        k = clamp(eback(lt / 0.5))
        fx, fy = 210, 470
        d.rr((fx, fy - 30, fx + 120, fy + 10), 10, fill=A((200, 110, 30), a * k))
        d.rr((fx, fy, fx + 300, fy + 200), 18, fill=A(OR, a * k))
        g = _s(p, 'good', 'sistem/')
        d.t((fx + 150, fy + 100), g, d.fit(g, 34, 270, 'Black', True), A(DARK, a * k), 'mm')
        if p.get('good_sub'):
            d.t((fx + 150, fy + 155), _s(p, 'good_sub'), d.fit(_s(p, 'good_sub'), 20, 270, 'Bold'), A(DARK, a * k), 'mm')
        items = _list(p, 'good_items', 8) or ['kural', 'kalıp', 'ayar', 'şablon']
        for i, lab in enumerate(items):
            ph = clamp((lt - 0.3 - i * 0.25) / 0.7)
            if 0 < ph < 1:
                ang = i / len(items) * 2 * math.pi
                sx, sy = 360 + math.cos(ang) * 300, 560 + math.sin(ang) * 240
                x, y = sx + (360 - sx) * eo(ph), sy + (560 - sy) * eo(ph)
                f = F(15, 'SemiBold')
                w = d.tw(str(lab), f) / 2 + 18
                d.rr((x - w, y - 20, x + w, y + 20), 10, fill=A(CARD, a * (1 - ph * 0.6)), outline=A(LINE, a))
                d.t((x, y), str(lab), f, A(CREAM, a * (1 - ph * 0.6)), 'mm')
        if p.get('strike'):
            qq = clamp(eback((lt - 0.1) / 0.4))
            s = _s(p, 'strike')
            f = F(30, 'Bold')
            d.t((360, 380), s, f, A(GREY, a * qq), 'mm')
            if qq > 0.6:
                w = d.tw(s, f) / 2 + 10
                d.line([(360 - w, 380), (360 + w, 380)], A(RED, a), 5)


# 8 ---------------------------------------------------------------
def connector(d, t, a, dur, p):
    y = 520
    q = eo(t / 0.4)
    g = eo((t - 0.4) / 0.8)
    left, right = _s(p, 'left', 'Araç'), _s(p, 'right', 'Claude')
    d.rr((60, y - 50, 320, y + 50), 50, fill=A(YEL, a * q))
    d.t((190, y), left, d.fit(left, 24, 230, 'ExtraBold'), A(DARK, a * q), 'mm')
    d.line([(320, y), (320 + 90 * g, y)], A(YEL, a * q), 5)
    if g > 0.9:
        for k in range(5):
            ph = (t * 1.2 + k / 5) % 1
            d.el((320 + 90 * ph - 5, y - 5, 320 + 90 * ph + 5, y + 5), fill=A(CREAM, a))
    k = eback((t - 0.9) / 0.4)
    if k > 0:
        d.rr((410, y - 50, 660, y + 50), 50, fill=A(CARD, a), outline=A(OR, a), w=3)
        d.t((535, y), right, d.fit(right, 28 * clamp(k) + 1, 220, 'Bold'), A(CREAM, a), 'mm')
    c = eback((t - 1.5) / 0.4)
    if c > 0:
        d.el((630, y - 70, 670, y - 30), fill=A(YEL, a))
        icon(d, 'check', 650, y - 50, 22 * clamp(c), DARK, a)
    chips = _list(p, 'chips', 3)
    for i, lab in enumerate(chips):
        k2 = eback((t - 1.8 - i * 0.2) / 0.4)
        if k2 <= 0:
            continue
        x = 60 + i * 205
        d.rr((x, 620, x + 190, 666), 23, fill=A(CARD, a * clamp(k2)), outline=A(LINE, a * clamp(k2)))
        d.t((x + 95, 643), str(lab), d.fit(str(lab), 17, 170, 'SemiBold'), A(CREAM, a * clamp(k2)), 'mm')


# 9 ---------------------------------------------------------------
def offer(d, t, a, dur, p):
    k = eback(t / 0.5)
    hh = 230 * (0.8 + 0.2 * clamp(k))
    cy = 590
    glow = 0.7 + 0.3 * math.sin(t * 6)
    d.rr((60, cy - hh, 660, cy + hh), 34, fill=A((22, 26, 12), a * clamp(k)), outline=A(YEL, a * clamp(k) * glow), w=3)
    if k > 0.5:
        d.rr((320, cy - hh + 24, 400, cy - hh + 104), 20, fill=A(YEL, a))
        icon(d, _s(p, 'icon', 'star') if _s(p, 'icon', 'star') in ICONS else 'star', 360, cy - hh + 64, 44, DARK, a)
        if p.get('kicker'):
            d.t((360, cy - hh + 128), _s(p, 'kicker').upper(), F(14, 'ExtraBold'), A(YEL, a), 'mm')
        l1, l2 = _s(p, 'line1'), _s(p, 'line2')
        d.t((360, cy - 50), l1, d.fit(l1, 46, 540, 'Black', True), A(CREAM, a), 'mm')
        d.t((360, cy + 2), l2, d.fit(l2, 46, 540, 'Black', True), A(YEL, a), 'mm')
        if p.get('sub'):
            d.t((360, cy + 46), _s(p, 'sub'), d.fit(_s(p, 'sub'), 22, 540, 'Medium'), A(CREAM, a), 'mm')
        chips = _list(p, 'chips', 12)
        if chips:
            x = 80 - (t * 60) % 400
            for mname in chips * 3:
                f = F(15, 'Medium')
                w = d.tw(str(mname), f) + 28
                if 70 < x and x + w < 650:
                    d.rr((x, cy + 76, x + w, cy + 108), 16, outline=A(GREY, a), w=1)
                    d.t((x + w / 2, cy + 92), str(mname), f, A(CREAM, a), 'mm')
                x += w + 10
        if p.get('button'):
            b = _s(p, 'button')
            d.rr((130, cy + 110 + 2, 590, cy + 170), 30, fill=A(YEL, a))
            d.t((360, cy + 141), b, d.fit(b, 22, 420, 'ExtraBold'), A(DARK, a), 'mm')


# 10 --------------------------------------------------------------
def terminal(d, t, a, dur, p):
    k = eo(t / 0.4)
    d.rr((50, 360, 670, 780), 22, fill=A((14, 13, 12), a * k), outline=A(LINE, a * k))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.el((72 + i * 22, 380, 84 + i * 22, 392), fill=A(c, a * k))
    d.t((360, 386), _s(p, 'title', 'Terminal'), F(17, 'SemiBold'), A(GREY, a * k), 'mm')
    lines = _list(p, 'lines', 6)
    ts = _times(len(lines) + (1 if p.get('typed') else 0), dur, 0.4, 0.6)
    y = 430
    for i, ln in enumerate(lines):
        if t < ts[i]:
            break
        col = OR if str(ln).startswith('✓') else CREAM
        for wl in d.wrap(str(ln), F(18, 'Medium'), 560)[:2]:
            d.t((80, y), wl, F(18, 'Medium'), A(col, a * ap(t, ts[i], 0.25)), 'lm')
            y += 32
        y += 8
    if p.get('typed'):
        t0 = ts[-1]
        if t >= t0:
            txt = '> ' + _s(p, 'typed')
            n = int(len(txt) * clamp((t - t0) / 1.4))
            for wl in d.wrap(txt[:n] + ('▌' if int(t * 3) % 2 == 0 else ''), F(20, 'Medium'), 560)[:3]:
                d.t((80, y + 10), wl, F(20, 'Medium'), A(YEL, a), 'lm')
                y += 32


# 11 --------------------------------------------------------------
def app(d, t, a, dur, p):
    k = eo(t / 0.5)
    px, py = 120, 340 + (1 - k) * 60
    phone(d, px, py, 270, 520, a * k)
    nm = _s(p, 'name', 'Uygulama')
    d.rr((px + 85, py + 120, px + 185, py + 220), 26, fill=A(OR, a * k))
    d.t((px + 135, py + 170), nm[:1].upper(), F(56, 'Bold', True), A(DARK, a * k), 'mm')
    d.t((px + 135, py + 262), nm, d.fit(nm, 26, 230, 'Bold'), A(CREAM, a * k), 'mm')
    tg = _s(p, 'tagline')
    if tg:
        d.t((px + 135, py + 296), tg, d.fit(tg, 16, 230, 'Regular'), A(GREY, a * k), 'mm')
    for i in range(3):
        d.rr((px + 40, py + 330 + i * 26, px + 230 - i * 40, py + 344 + i * 26), 7, fill=A(CARD2, a * k))
    b = _s(p, 'button', 'Başla')
    d.rr((px + 40, py + 420, px + 230, py + 470), 25, fill=A(OR, a * k))
    d.t((px + 135, py + 445), b, d.fit(b, 20, 170, 'Bold'), A(DARK, a * k), 'mm')
    s = eback((t - min(2.0, dur * 0.4)) / 0.5)
    if s > 0 and p.get('sticker_big'):
        img = Image.new('RGBA', (300 * S, 220 * S), (0, 0, 0, 0))
        dd = D(img)
        dd.rr((10, 10, 290, 210), 26, fill=A(CREAM, a))
        dd.t((150, 72), _s(p, 'sticker_top'), dd.fit(_s(p, 'sticker_top'), 26, 250, 'Medium'), A((40, 30, 24), a), 'mm')
        dd.t((150, 128), _s(p, 'sticker_big'), dd.fit(_s(p, 'sticker_big'), 56, 250, 'ExtraBold', True), A(OR, a), 'mm')
        dd.t((150, 176), _s(p, 'sticker_bottom'), dd.fit(_s(p, 'sticker_bottom'), 24, 250, 'Medium'), A((40, 30, 24), a), 'mm')
        img = img.rotate(-8 * clamp(s), resample=Image.BICUBIC, expand=True)
        sc_ = 0.6 + 0.4 * clamp(s)
        img = img.resize((max(1, int(img.width * sc_)), max(1, int(img.height * sc_))))
        d.layer.alpha_composite(img, (int((540 - img.width / S / 2) * S), int((470 - img.height / S / 2) * S)))


# 12 --------------------------------------------------------------
def checklist(d, t, a, dur, p):
    items = _list(p, 'items', 5) or ['Hazır']
    ts = _times(len(items), dur, 0.3, 0.9)
    for i, lab in enumerate(items):
        k = eback((t - ts[i] + 0.3) / 0.4)
        if k <= 0:
            continue
        y = 370 + i * 84
        done = t > ts[i] + 0.5
        d.rr((60, y, 400, y + 70), 20, fill=A(CARD, a * clamp(k)), outline=A(OR if done else LINE, a * clamp(k)), w=2)
        d.el((80, y + 18, 114, y + 52), fill=A(OR if done else CARD2, a * clamp(k)))
        if done:
            icon(d, 'check', 97, y + 35, 18, DARK, a)
        else:
            d.t((97, y + 35), str(i + 1), F(18, 'Bold'), A(GREY, a * clamp(k)), 'mm')
        d.t((130, y + 35), str(lab), d.fit(str(lab), 22, 255, 'Bold'), A(CREAM, a * clamp(k)), 'lm')
    q = eo((t - 0.3) / 0.5)
    phone(d, 430, 360, 230, 420, a * q)
    fill = clamp((t - 0.5) / max(1, dur - 1))
    mini_scene(d, 444, 410, 202, 260, 2, a * q * (0.3 + 0.7 * fill))
    pt = _s(p, 'preview_title')
    for li, ln in enumerate(d.wrap(pt, F(16, 'Bold'), 190)[:2]):
        d.t((545, 700 + li * 22), ln, F(16, 'Bold'), A(CREAM if li == 0 else OR, a * q), 'mm')
    d.rr((450, 750, 640, 760), 5, fill=A(CARD2, a * q))
    d.rr((450, 750, 450 + 190 * fill, 760), 5, fill=A(OR, a * q))


# 13 --------------------------------------------------------------
def crossed(d, t, a, dur, p):
    items = _list(p, 'items', 3) or ['KAMERA', 'YÜZ', 'KURGU']
    n = len(items)
    w = (600 - (n - 1) * 20) / n
    ts = _times(n, dur, 0.0, 0.6)
    for i, lab in enumerate(items):
        k = eback((t - ts[i]) / 0.4)
        if k <= 0:
            continue
        x = 60 + i * (w + 20)
        d.rr((x, 400, x + w, 640), 22, fill=A(CARD, a * clamp(k)))
        cx, cy = x + w / 2, 500
        icon(d, ['clock', 'chat', 'gear', 'lock', 'mic'][i % 5], cx, cy, 60, GREY, a * clamp(k))
        cross(d, cx, cy, min(62, w / 2 - 14) * clamp(k), a)
        d.t((cx, 600), str(lab).upper(), d.fit(str(lab).upper(), 22, w - 20, 'Black', True), A(CREAM, a * clamp(k)), 'mm')


# 14 --------------------------------------------------------------
_CROWD = np.random.default_rng(3).uniform(0, 1, size=(160, 2))


def crowd(d, t, a, dur, p):
    k = eo(t / 0.4)
    for i, (u, v) in enumerate(_CROWD):
        x, y = 70 + u * 580, 380 + v * 380
        if math.hypot(x - 360, y - 570) < 80:
            continue
        q = ap(t, i * 0.004, 0.2)
        d.el((x - 9, y - 9, x + 9, y + 9), fill=A((70, 64, 60), a * q * 0.9))
    if t > 1.0:
        for j in range(4):
            ph = ((t - 1.0) * 0.6 + j * 0.25) % 1
            rr = 50 + 260 * ph
            d.el((360 - rr, 570 - rr, 360 + rr, 570 + rr), outline=A(OR, a * (1 - ph)), w=4)
    d.rr((320, 510, 400, 630), 14, fill=A(OR, a * k), outline=A(CREAM, a * k), w=3)
    icon(d, 'play', 360, 570, 40, DARK, a * k)
    if p.get('top'):
        pill(d, 360, 380, _s(p, 'top'), CARD, CREAM, 16, a * ap(t, 0.3), 'SemiBold')
    if p.get('highlight'):
        q = eback((t - 1.6) / 0.4)
        if q > 0:
            pill(d, 360, 690, _s(p, 'highlight'), YEL, DARK, 20 * clamp(q) + 1, a)


# 15 --------------------------------------------------------------
def calendar(d, t, a, dur, p):
    q = clamp(eback(t / 0.5))
    d.rr((90, 370, 330, 620), 22, fill=A(CREAM, a * q))
    d.d.rectangle([90 * S, 370 * S, 330 * S, 430 * S], fill=A(RED, a * q))
    d.t((210, 400), _s(p, 'top', '+3 AY'), d.fit(_s(p, 'top', '+3 AY'), 26, 220, 'Black', True), A(CREAM, a * q), 'mm')
    big = _s(p, 'big', '3')
    d.t((210, 520), big, d.fit(big, 120, 220, 'Black', True), A(DARK, a * q), 'mm')
    d.t((210, 600), _s(p, 'unit', 'AY SONRA'), F(18, 'Bold'), A(DARK, a * q), 'mm')
    c = eo((t - 0.5) / 2)
    for i in range(60):
        if i / 60 > c:
            break
        faceless(d, 380 + (i % 10) * 28, 380 + (i // 10) * 40, 12, a * q, (110, 100, 92))
    if p.get('note'):
        pill(d, 520, 650, _s(p, 'note'), CARD, CREAM, 16, a * q * ap(t, 0.8), 'SemiBold')
    if p.get('banner'):
        q3 = clamp(eback((t - min(2.3, dur * 0.5)) / 0.4))
        if q3 > 0:
            d.rr((90, 690, 640, 770), 20, fill=A(OR, a * q3))
            b = _s(p, 'banner')
            d.t((365, 730), b, d.fit(b, 24, 520, 'ExtraBold'), A(DARK, a * q3), 'mm')


# 16 --------------------------------------------------------------
def cta(d, t, a, dur, p):
    q = clamp(eback(t / 0.4))
    top = _s(p, 'top', 'Takip et')
    d.t((360, 220), top, d.fit(top, 56, 620, 'Black', True), A(CREAM, a * q), 'mm')
    b = eback((t - 0.25) / 0.45)
    word = _s(p, 'word', 'KAYDET').upper()
    if b > 0:
        glow = 0.7 + 0.3 * math.sin(t * 7)
        d.rr((70, 290, 650, 490), 32, fill=A((40, 24, 10), a), outline=A(OR, a * glow), w=5)
        d.poly([(130, 488), (180, 488), (120, 540)], A(OR, a * glow))
        f = d.fit(word, 118 * clamp(b) + 1, 540, 'Black', True)
        d.t((360, 390), word, f, A(OR, a), 'mm')
    c = eo((t - 1.2) / 0.4)
    if c > 0:
        for li, ln in enumerate(d.wrap(_s(p, 'line'), F(28, 'SemiBold'), 600)[:2]):
            d.t((360, 585 + li * 40), ln, F(28, 'SemiBold'), A(CREAM, a * c), 'mm')
        for i, lab in enumerate(_list(p, 'pills', 3)):
            k = eback((t - 1.8 - i * 0.25) / 0.35)
            if k > 0:
                pill(d, 140 + i * 220, 700, str(lab), CARD, CREAM, d_size(d, str(lab)) * clamp(k) + 1, a, 'Bold')


def d_size(d, lab):
    s = 17
    while s > 11 and d.tw(lab, F(s, 'Bold')) > 170:
        s -= 1
    return s


TEMPLATES = {
    'bigtext': bigtext, 'stat': stat, 'chart': chart, 'list': listcards, 'chat': chat, 'steps': steps,
    'compare': compare, 'connector': connector, 'offer': offer, 'terminal': terminal, 'app': app,
    'checklist': checklist, 'crossed': crossed, 'crowd': crowd, 'calendar': calendar, 'cta': cta,
}

TEMPLATE_DOC = """
bigtext   {lines:[1-3 kısa satır], highlight:"vurgulanacak kelime", stamp:"opsiyonel damga metni"}
stat      {value:sayı, decimals:0-1, prefix:"", suffix:"K/+/%", label:"altındaki açıklama", badges:["en fazla 3 kısa etiket"], icon:IKON}
chart     {now_label:"ŞU AN BURADASIN", peak_label:"tepe etiketi", x_label:"zaman", y_label:"erişim"}  (erken dönem / büyüme eğrisi)
list      {title:"opsiyonel başlık", items:[{title:"", sub:"", icon:IKON}] (2-4 madde)}
chat      {user:"kullanıcının isteği", command:"/komut veya istek", tag:"araç adı", wait:"işlem sürüyor metni", done:"bitti metni", result:"sonuç etiketi"}
steps     {title:"Kurulum · 1 dk", screen_title:"", steps:["kısa adım", ...] (3-5)}
compare   {bad:"ÖZENSİZ", strike:"üstü çizilecek kötü yöntem", good:"iyi yöntem adı", good_sub:"alt yazı", good_items:["4-8 kısa etiket"]}
connector {left:"Araç A", right:"Araç B", chips:["en fazla 3 kısa özellik"]}
offer     {kicker:"üst etiket", line1:"", line2:"", sub:"", chips:["araç/model adları"], button:"buton metni", icon:IKON}
terminal  {title:"Claude Code / Terminal", lines:["satır", "✓ başarılı satır"], typed:"sonda yazılan komut/istek"}
app       {name:"uygulama adı", tagline:"", button:"", sticker_top:"", sticker_big:"KISA", sticker_bottom:""}
checklist {items:["3-4 adım"], preview_title:"telefonda görünen video başlığı"}
crossed   {items:["2-3 kısa şey: üstü çizilenler"]}
crowd     {top:"üst etiket", highlight:"alt vurgu"}  (kalabalık içinde öne çıkan tek içerik)
calendar  {top:"+3 AY", big:"3", unit:"AY SONRA", note:"", banner:"alt şerit metni"}
cta       {top:"üst satır", word:"TEK KELİME", line:"açıklama", pills:["en fazla 3 araç adı"]}  (SADECE son sahne)
IKON = spark|check|play|bolt|chat|gear|folder|mic|clock|star|chart|lock
"""
