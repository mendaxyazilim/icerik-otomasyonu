"""Drawing primitives, avatar, captions and background shared by all scenes."""
import math
import os
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, 'assets', 'fonts')

W, H, FPS = 720, 1280, 30
S = 2  # supersampling for scene layer

OR = (255, 122, 26)
YEL = (255, 210, 50)
CREAM = (245, 237, 227)
GREY = (150, 140, 130)
CARD = (31, 27, 24)
CARD2 = (42, 36, 32)
LINE = (66, 57, 50)
DARK = (20, 14, 8)
RED = (240, 70, 60)


# ---------------- easing ----------------
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def eo(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def eback(x):
    x = clamp(x)
    c = 1.70158
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def ap(t, t0, d=0.4):
    return eo((t - t0) / d)


def A(c, a):
    return tuple(c[:3]) + (int(255 * clamp(a)),)


# ---------------- fonts ----------------
_fc = {}


def F(size, w='SemiBold', disp=False, scale=S):
    key = (round(size, 1), w, disp, scale)
    if key not in _fc:
        name = ('InterDisplay-' if disp else 'Inter-') + w + '.otf'
        path = os.path.join(FONTS, name)
        if not os.path.exists(path):
            path = os.path.join(FONTS, 'InterDisplay-Black.otf' if disp else 'Inter-Bold.otf')
        _fc[key] = ImageFont.truetype(path, max(1, int(size * scale)))
    return _fc[key]


def FS(size, scale=S):
    key = ('serif', round(size, 1), scale)
    if key not in _fc:
        _fc[key] = ImageFont.truetype(os.path.join(FONTS, 'Lora-Italic-Variable.ttf'), max(1, int(size * scale)))
    return _fc[key]


def sc(v):
    return [x * S for x in v]


class D:
    """Drawing context in 720x1280 coordinates on a supersampled RGBA layer."""

    def __init__(self, img):
        self.layer = img
        self.d = ImageDraw.Draw(img, 'RGBA')

    def rr(self, box, r, fill=None, outline=None, w=2):
        x0, y0, x1, y1 = box
        if x1 <= x0 or y1 <= y0:
            return
        r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
        self.d.rounded_rectangle(sc(box), radius=max(0, r) * S, fill=fill, outline=outline, width=int(w * S))

    def el(self, box, fill=None, outline=None, w=2):
        x0, y0, x1, y1 = box
        if x1 <= x0 or y1 <= y0:
            return
        self.d.ellipse(sc(box), fill=fill, outline=outline, width=int(w * S))

    def poly(self, pts, fill):
        self.d.polygon([(x * S, y * S) for x, y in pts], fill=fill)

    def line(self, pts, fill, w=3):
        self.d.line([(x * S, y * S) for x, y in pts], fill=fill, width=max(1, int(w * S)), joint='curve')

    def t(self, xy, text, font, fill, anchor='la'):
        self.d.text((xy[0] * S, xy[1] * S), text, font=font, fill=fill, anchor=anchor)

    def tw(self, text, font):
        return font.getlength(text) / S

    def fit(self, text, size, maxw, w='Bold', disp=False, minsize=12):
        """Largest font size <= size so that text fits maxw."""
        s = size
        while s > minsize and self.tw(text, F(s, w, disp)) > maxw:
            s -= 1
        return F(s, w, disp)

    def wrap(self, text, font, maxw):
        lines, cur = [], ''
        for wd in text.split():
            test = (cur + ' ' + wd).strip()
            if cur and self.tw(test, font) > maxw:
                lines.append(cur)
                cur = wd
            else:
                cur = test
        if cur:
            lines.append(cur)
        return lines


# ---------------- common widgets ----------------
def pill(d, cx, cy, txt, fill, col, size=18, a=1, w='ExtraBold', outline=None):
    f = F(size, w)
    tw = d.tw(txt, f) + 36
    d.rr((cx - tw / 2, cy - size * 1.1, cx + tw / 2, cy + size * 1.1), size * 1.1, fill=A(fill, a),
         outline=A(outline, a) if outline else None)
    d.t((cx, cy), txt, f, A(col, a), 'mm')


def phone(d, x, y, w, h, a=1):
    d.rr((x, y, x + w, y + h), 38, fill=A((12, 11, 10), a), outline=A((90, 80, 72), a), w=3)
    d.rr((x + w / 2 - 45, y + 14, x + w / 2 + 45, y + 36), 11, fill=A((0, 0, 0), a))


def mini_scene(d, x, y, w, h, seed, a=1):
    hue = [(58, 44, 70), (40, 52, 66), (66, 46, 36), (36, 58, 52), (70, 40, 50)][seed % 5]
    d.rr((x, y, x + w, y + h), 8, fill=A(hue, a))
    d.d.rectangle(sc((x, y + h * 0.66, x + w, y + h)), fill=A(tuple(int(c * 0.7) for c in hue), a))
    for k in range(2):
        cx = x + w * (0.33 + 0.34 * k)
        hy = y + h * 0.38
        hr = w * 0.09
        d.poly([(cx - hr * 1.6, y + h * 0.9), (cx + hr * 1.6, y + h * 0.9), (cx + hr * 1.1, hy + hr * 1.4),
                (cx - hr * 1.1, hy + hr * 1.4)], A((200, 190, 175) if k else (150, 110, 90), a))
        d.poly([(cx, hy - hr), (cx + hr, hy - hr * 0.2), (cx + hr * 0.7, hy + hr), (cx - hr * 0.7, hy + hr),
                (cx - hr, hy - hr * 0.2)], A((236, 196, 160), a))


def cross(d, cx, cy, r, a):
    if r <= 1:
        return
    d.el((cx - r, cy - r, cx + r, cy + r), outline=A(RED, a), w=6)
    d.line([(cx - r * 0.7, cy + r * 0.7), (cx + r * 0.7, cy - r * 0.7)], A(RED, a), 6)


def stamp(d, txt, cx, cy, k, a, col=RED, size=70, rot=-8):
    if k <= 0:
        return
    f = F(size, 'Black', True)
    tw = d.tw(txt, f) + 60
    bw, bh = int(tw), int(size * 2)
    img = Image.new('RGBA', (bw * S, bh * S), (0, 0, 0, 0))
    dd = D(img)
    dd.rr((6, 6, bw - 6, bh - 6), 18, outline=A(col, a), w=7)
    dd.t((bw / 2, bh / 2), txt, f, A(col, a), 'mm')
    img = img.rotate(rot, resample=Image.BICUBIC, expand=True)
    s = (1.6 - 0.6 * clamp(k)) * 0.8
    img = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))))
    al = img.getchannel('A').point(lambda v: int(v * clamp(k)))
    img.putalpha(al)
    d.layer.alpha_composite(img, (int(cx * S - img.width / 2), int(cy * S - img.height / 2)))


def faceless(d, cx, cy, r, a, col=(90, 80, 72)):
    d.el((cx - r, cy - r, cx + r, cy + r), fill=A(CARD2, a))
    d.el((cx - r * 0.38, cy - r * 0.6, cx + r * 0.38, cy + r * 0.15), fill=A(col, a))
    d.d.pieslice(sc((cx - r * 0.7, cy + r * 0.2, cx + r * 0.7, cy + r * 1.4)), 180, 360, fill=A(col, a))


def icon(d, kind, cx, cy, s, col, a):
    """Small generic icons drawn with shapes. kind in: spark, check, play, bolt, chat, gear, folder, mic, clock, star, chart, lock."""
    c = A(col, a)
    if kind == 'check':
        d.line([(cx - s * 0.5, cy), (cx - s * 0.1, cy + s * 0.4), (cx + s * 0.55, cy - s * 0.45)], c, s * 0.18)
    elif kind == 'play':
        d.poly([(cx - s * 0.35, cy - s * 0.5), (cx + s * 0.5, cy), (cx - s * 0.35, cy + s * 0.5)], c)
    elif kind == 'bolt':
        d.poly([(cx + s * 0.1, cy - s * 0.6), (cx - s * 0.4, cy + s * 0.1), (cx, cy + s * 0.1), (cx - s * 0.1, cy + s * 0.6),
                (cx + s * 0.4, cy - s * 0.1), (cx, cy - s * 0.1)], c)
    elif kind == 'chat':
        d.rr((cx - s * 0.55, cy - s * 0.45, cx + s * 0.55, cy + s * 0.3), s * 0.2, fill=c)
        d.poly([(cx - s * 0.3, cy + s * 0.25), (cx - s * 0.05, cy + s * 0.25), (cx - s * 0.4, cy + s * 0.6)], c)
    elif kind == 'gear':
        for k in range(8):
            ang = k * math.pi / 4
            d.line([(cx, cy), (cx + math.cos(ang) * s * 0.55, cy + math.sin(ang) * s * 0.55)], c, s * 0.22)
        d.el((cx - s * 0.38, cy - s * 0.38, cx + s * 0.38, cy + s * 0.38), fill=c)
    elif kind == 'folder':
        d.rr((cx - s * 0.55, cy - s * 0.45, cx - s * 0.05, cy - s * 0.2), s * 0.08, fill=c)
        d.rr((cx - s * 0.55, cy - s * 0.3, cx + s * 0.55, cy + s * 0.45), s * 0.12, fill=c)
    elif kind == 'mic':
        d.rr((cx - s * 0.2, cy - s * 0.55, cx + s * 0.2, cy + s * 0.15), s * 0.2, fill=c)
        d.d.arc(sc((cx - s * 0.38, cy - s * 0.3, cx + s * 0.38, cy + s * 0.35)), 0, 180, fill=c, width=int(s * 0.12 * S))
        d.line([(cx, cy + s * 0.35), (cx, cy + s * 0.55)], c, s * 0.12)
    elif kind == 'clock':
        d.el((cx - s * 0.55, cy - s * 0.55, cx + s * 0.55, cy + s * 0.55), outline=c, w=s * 0.12)
        d.line([(cx, cy), (cx, cy - s * 0.35)], c, s * 0.1)
        d.line([(cx, cy), (cx + s * 0.25, cy + s * 0.1)], c, s * 0.1)
    elif kind == 'star':
        pts = []
        for k in range(10):
            r = s * (0.55 if k % 2 == 0 else 0.24)
            ang = -math.pi / 2 + k * math.pi / 5
            pts.append((cx + math.cos(ang) * r, cy + math.sin(ang) * r))
        d.poly(pts, c)
    elif kind == 'chart':
        for k, hh in enumerate([0.3, 0.55, 0.85]):
            x = cx - s * 0.45 + k * s * 0.33
            d.rr((x, cy + s * 0.45 - s * hh, x + s * 0.24, cy + s * 0.45), 3, fill=c)
    elif kind == 'lock':
        d.d.arc(sc((cx - s * 0.3, cy - s * 0.6, cx + s * 0.3, cy)), 180, 360, fill=c, width=int(s * 0.12 * S))
        d.rr((cx - s * 0.45, cy - s * 0.2, cx + s * 0.45, cy + s * 0.5), s * 0.1, fill=c)
    else:  # spark
        r = s * 0.6
        d.poly([(cx, cy - r), (cx + r * 0.22, cy - r * 0.22), (cx + r, cy), (cx + r * 0.22, cy + r * 0.22),
                (cx, cy + r), (cx - r * 0.22, cy + r * 0.22), (cx - r, cy), (cx - r * 0.22, cy - r * 0.22)], c)


ICONS = ['spark', 'check', 'play', 'bolt', 'chat', 'gear', 'folder', 'mic', 'clock', 'star', 'chart', 'lock']

# ---------------- background ----------------
_yy, _xx = np.mgrid[0:H, 0:W].astype(np.float32)
_BG = np.zeros((H, W, 3), np.float32)
_top = np.array([16, 19, 23], np.float32)
_bot = np.array([10, 11, 13], np.float32)
_BG[:] = _top + (_bot - _top) * (_yy / H)[..., None]
_PR = np.random.default_rng(11)
_PART = [(_PR.uniform(0, W), _PR.uniform(0, H), _PR.uniform(6, 22), _PR.uniform(1, 2.5)) for _ in range(40)]


def background(t, glowc=OR):
    g = np.exp(-(((_xx - 360) / 330) ** 2 + ((_yy - 560 - 20 * math.sin(t * 0.7)) / 380) ** 2))
    fr = _BG + g[..., None] * np.array(glowc, np.float32)[None, None, ::-1] * 0.16
    fr = fr.astype(np.uint8)
    for (px, py, sp, r) in _PART:
        y = (py - t * sp) % H
        cv2.circle(fr, (int(px), int(y)), int(r), (60, 90, 140), -1, cv2.LINE_AA)
    return fr


# ---------------- avatar ----------------
class Avatar:
    """Bust avatar with blink, bob and amplitude-driven mouth.

    The mouth/eye coordinates refer to assets/avatar.png (full 1438px-wide source)."""

    def __init__(self, path=None, width=420, mouth=(722, 1288), eyes=((560, 978), (890, 978)), crop_top=369):
        path = path or os.path.join(ROOT, 'assets', 'avatar.png')
        im = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        self.off = crop_top
        self.src = im[crop_top:]
        self.w = width
        self.sc = width / self.src.shape[1]
        self.mouth = mouth
        self.eyes = eyes
        ex, ey = eyes[0]
        self.skin = tuple(int(v) for v in im[ey - 73, ex][:3])
        rng = np.random.default_rng(3)
        self.blinks, tt = [], 1.0
        while tt < 200:
            self.blinks.append(tt)
            tt += rng.uniform(2.6, 4.6)

    def is_blink(self, t):
        return any(0 <= t - b < 0.13 for b in self.blinks)

    def frame(self, o, blink):
        a = self.src.copy()
        mx, my = self.mouth
        cy = my - self.off
        if o > 0.08:
            h = int(12 + 62 * o)
            hw = int(64 + 22 * o)
            cv2.ellipse(a, (mx, cy + h // 2 - 2), (hw, h // 2 + 2), 0, 0, 360, (20, 20, 20, 255), -1, cv2.LINE_AA)
            cv2.ellipse(a, (mx, cy + h // 2), (hw - 6, h // 2), 0, 0, 360, (45, 30, 95, 255), -1, cv2.LINE_AA)
            cv2.ellipse(a, (mx, cy + 2), (hw - 14, max(3, h // 5)), 0, 0, 180, (245, 245, 250, 255), -1, cv2.LINE_AA)
            cv2.ellipse(a, (mx, cy + h - 2), (hw - 4, 7), 0, 0, 180, (150, 150, 215, 255), -1, cv2.LINE_AA)
        if blink:
            for ex, ey in self.eyes:
                cv2.ellipse(a, (ex, ey - self.off), (95, 46), 0, 0, 360, self.skin + (255,), -1, cv2.LINE_AA)
                cv2.ellipse(a, (ex, ey + 7 - self.off), (78, 14), 0, 0, 180, (25, 25, 25, 255), 6, cv2.LINE_AA)
        return cv2.resize(a, (self.w, int(a.shape[0] * self.sc)), interpolation=cv2.INTER_AREA)

    def paste(self, fr, t, o):
        bob = 4 * math.sin(2 * math.pi * t / 1.8) + 5 * o
        ang = 1.3 * math.sin(2 * math.pi * t / 3.3) + 1.2 * o * math.sin(2 * math.pi * t / 0.9)
        rgba = self.frame(o, self.is_blink(t))
        ent = eo(t / 0.6)
        x = W - self.w + 30
        y = H - rgba.shape[0] + 40 + bob + (1 - ent) * 300
        h, w = rgba.shape[:2]
        M = cv2.getRotationMatrix2D((w / 2, h), ang, 1.0)
        rgba = cv2.warpAffine(rgba, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
        x0, y0 = int(x), int(y)
        xa, ya = max(0, x0), max(0, y0)
        xb, yb = min(W, x0 + w), min(H, y0 + h)
        if xb <= xa or yb <= ya:
            return
        sub = rgba[ya - y0:yb - y0, xa - x0:xb - x0]
        al = sub[..., 3:4].astype(np.float32) / 255
        sh = cv2.GaussianBlur(sub[..., 3].astype(np.float32) / 255, (0, 0), 10)[..., None] * 0.45
        reg = fr[ya:yb, xa:xb].astype(np.float32) * (1 - sh)
        reg = reg * (1 - al) + sub[..., :3].astype(np.float32) * al
        fr[ya:yb, xa:xb] = reg.astype(np.uint8)


# ---------------- captions ----------------
CAP_SANS = None
CAP_SERIF = None


def _cap_fonts():
    global CAP_SANS, CAP_SERIF
    if CAP_SANS is None:
        CAP_SANS = F(42, 'Medium', scale=1)
        CAP_SERIF = FS(46, scale=1)
    return CAP_SANS, CAP_SERIF


def layout_caption(text, maxw=630):
    sans, serif = _cap_fonts()
    words = []
    for tok in text.split():
        acc = tok.startswith('*') and tok.endswith('*') and len(tok) > 2
        words.append((tok.strip('*'), acc))
    lines, cur, x = [], [], 0
    sp = sans.getlength(' ')
    for wd, acc in words:
        f = serif if acc else sans
        ww = f.getlength(wd)
        if cur and x + sp + ww > maxw:
            lines.append(cur)
            cur, x = [], 0
        if cur:
            x += sp
        cur.append((wd, acc, x))
        x += ww
    if cur:
        lines.append(cur)
    return lines


def draw_caption(pil, cap, t, accent=OR):
    """cap = dict(start, end, lines). Words reveal progressively."""
    sans, serif = _cap_fonts()
    d = ImageDraw.Draw(pil, 'RGBA')
    flat = [w for ln in cap['lines'] for w in ln]
    total = sum(len(w[0]) + 1 for w in flat) or 1
    s, e = cap['start'], cap['end']
    cum = 0
    for li, ln in enumerate(cap['lines']):
        for wd, acc, x in ln:
            wt = s + (e - s) * 0.92 * cum / total
            cum += len(wd) + 1
            k = (t - wt) / 0.14
            if k <= 0:
                continue
            k = min(1, k)
            a = int(255 * k)
            y = 178 + li * 56 + (1 - k) * 10
            if acc:
                d.text((44 + x, y - 4), wd, font=serif, fill=tuple(accent) + (a,))
            else:
                d.text((44 + x, y), wd, font=sans, fill=(255, 255, 255, a))
