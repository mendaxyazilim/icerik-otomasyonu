"""Timeline building (audio alignment) and video rendering."""
import math
import subprocess
import wave
import numpy as np
import cv2
from PIL import Image

from .core import W, H, FPS, S, D, A, eo, OR, YEL, background, Avatar, layout_caption, draw_caption
from .scenes import TEMPLATES


def load_audio(path):
    with wave.open(path) as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


def silences(a, sr, thr_db=-32, min_len=0.12):
    """Return list of (start, end) silent intervals."""
    hop = int(sr * 0.01)
    n = len(a) // hop
    rms = np.sqrt(np.mean(a[:n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms + 1e-9)
    quiet = db < thr_db
    out, i = [], 0
    while i < n:
        if quiet[i]:
            j = i
            while j < n and quiet[j]:
                j += 1
            if (j - i) * 0.01 >= min_len:
                out.append((i * 0.01, j * 0.01))
            i = j
        else:
            i += 1
    return out


def align(segments, a, sr):
    """Assign (start, end) speech times to each segment using pauses in the narration."""
    dur = len(a) / sr
    sil = silences(a, sr)
    lead = sil[0][1] if sil and sil[0][0] <= 0.05 else 0.0
    tail = sil[-1][0] if sil and sil[-1][1] >= dur - 0.05 else dur
    inner = [s for s in sil if s[0] > lead + 0.05 and s[1] < tail - 0.05]
    lens = [max(1, len(s['say'])) for s in segments]
    tot = sum(lens)
    bounds, cum, last = [], 0, lead
    for i in range(len(segments) - 1):
        cum += lens[i]
        exp = lead + (tail - lead) * cum / tot
        cands = [s for s in inner if s[0] > last + 0.4]
        if cands:
            best = min(cands, key=lambda s: abs((s[0] + s[1]) / 2 - exp) - 0.6 * min(0.6, s[1] - s[0]))
            if abs((best[0] + best[1]) / 2 - exp) < 2.5:
                bounds.append(best)
                last = best[1]
                continue
        bounds.append((exp, exp))
        last = exp
    times = []
    st = lead
    for i in range(len(segments)):
        en = bounds[i][0] if i < len(bounds) else tail
        times.append((st, max(en, st + 0.3)))
        st = bounds[i][1] if i < len(bounds) else tail
    return times, dur


def build_timeline(sb, audio_path):
    a, sr = load_audio(audio_path)
    times, adur = align(sb['segments'], a, sr)
    end = adur + 0.8
    scenes, caps = [], []
    for i, (seg, (s0, s1)) in enumerate(zip(sb['segments'], times)):
        sc_start = 0.0 if i == 0 else (times[i - 1][1] + s0) / 2
        sc_end = end if i == len(times) - 1 else (s1 + times[i + 1][0]) / 2
        scenes.append({'start': sc_start, 'end': sc_end, **seg['scene']})
        if seg['scene']['type'] == 'cta':
            continue
        pieces = seg['captions']
        L = [max(1, len(p)) for p in pieces]
        c0 = s0
        for p, l in zip(pieces, L):
            c1 = c0 + (s1 - s0) * l / sum(L)
            caps.append({'start': c0, 'end': c1, 'lines': layout_caption(p)})
            c0 = c1
    # keep captions <= 2 lines by splitting long ones
    fixed = []
    for c in caps:
        if len(c['lines']) <= 2:
            fixed.append(c)
            continue
        words = [w[0] if not w[1] else f'*{w[0]}*' for ln in c['lines'] for w in ln]
        half = len(words) // 2
        mid = c['start'] + (c['end'] - c['start']) / 2
        fixed.append({'start': c['start'], 'end': mid, 'lines': layout_caption(' '.join(words[:half]))[:2]})
        fixed.append({'start': mid, 'end': c['end'], 'lines': layout_caption(' '.join(words[half:]))[:2]})
    return {'scenes': scenes, 'captions': fixed, 'duration': end, 'audio': (a, sr)}


def render(tl, audio_path, out_mp4, avatar=None, cta_accent=YEL):
    avatar = avatar or Avatar()
    a, sr = tl['audio']
    scenes, caps = tl['scenes'], tl['captions']
    nfr = int(round(tl['duration'] * FPS))

    def env_at(t):
        i, n = int(t * sr), int(sr / FPS)
        seg = a[max(0, i - n // 2): i + n // 2]
        if len(seg) == 0:
            return 0.0
        r = math.sqrt(float(np.mean(seg ** 2)))
        return min(1.0, max(0.0, (20 * math.log10(r + 1e-6) + 38) / 22))

    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}',
                          '-r', str(FPS), '-i', '-', '-i', audio_path,
                          '-c:v', 'libx264', '-preset', 'medium', '-crf', '22', '-pix_fmt', 'yuv420p',
                          '-profile:v', 'high', '-c:a', 'aac', '-b:a', '160k', '-ar', '44100',
                          '-af', 'loudnorm=I=-14:TP=-1.5,apad', '-t', f'{tl["duration"]:.2f}',
                          '-movflags', '+faststart', out_mp4], stdin=subprocess.PIPE)
    sm = 0.0
    ci = 0
    for fi in range(nfr):
        t = fi / FPS
        e = env_at(t)
        sm = e if e > sm else sm * 0.55 + e * 0.45
        si = next((i for i, s in enumerate(scenes) if s['start'] <= t < s['end']), len(scenes) - 1)
        scn = scenes[si]
        is_cta = scn['type'] == 'cta'
        fr = background(t, YEL if is_cta or scn['type'] == 'offer' else OR)
        layer = Image.new('RGBA', (W * S, H * S), (0, 0, 0, 0))
        d = D(layer)
        lt = t - scn['start']
        dur = scn['end'] - scn['start']
        al = eo(lt / 0.3) * (1 - eo((t - (scn['end'] - 0.22)) / 0.22)) if si < len(scenes) - 1 else eo(lt / 0.3)
        try:
            TEMPLATES[scn['type']](d, lt, al, dur, scn.get('params') or {})
        except Exception as ex:  # never crash the whole render on a bad param
            print('Sahne hatası', scn['type'], ex)
        small = np.array(layer.resize((W, H), Image.LANCZOS)).astype(np.float32)
        alpha = small[..., 3:4] / 255
        fr = (fr.astype(np.float32) * (1 - alpha) + small[..., [2, 1, 0]] * alpha).astype(np.uint8)
        avatar.paste(fr, t, sm)
        if not is_cta:
            cap = None
            for c in caps:
                if c['start'] <= t:
                    cap = c
            if cap is not None:
                pil = Image.fromarray(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB))
                draw_caption(pil, cap, t, YEL if scn['type'] == 'offer' else OR)
                fr = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        p.stdin.write(fr.tobytes())
    p.stdin.close()
    p.wait()
    if p.returncode != 0:
        raise RuntimeError('ffmpeg başarısız')
    return out_mp4
