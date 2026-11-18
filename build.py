"""Сборщик рилсов For Mortals.

Берёт из Apps Script (web app) строки листа «Рилсы» со статусом «в очереди»,
проверкой «ок» и пустым «Результатом», собирает вертикальное видео 1080x1920
(озвучка edge-tts, сцены, титры, субтитры), выкладывает его в GitHub Release
и возвращает ссылки в колонку «Результат».
"""

import asyncio
import datetime as dt
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
VOICE = os.environ.get("TTS_VOICE", "ru-RU-DmitryNeural")
TTS_RATE = os.environ.get("TTS_RATE", "+8%")
MAX_ITEMS = int(os.environ.get("MAX_ITEMS", "2"))
TAIL = 0.6  # секунд тишины после озвучки
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

WEBAPP_URL = os.environ.get("REELS_WEBAPP_URL", "")
REELS_KEY = os.environ.get("REELS_KEY", "")
PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "")
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY", "")
REPO = os.environ.get("GITHUB_REPOSITORY", "")

FONT_CANDIDATES = [
    os.path.abspath("fonts/Montserrat-ExtraBold.ttf"),
    "/usr/share/fonts/truetype/montserrat/Montserrat-ExtraBold.ttf",
    "/usr/share/fonts/opentype/montserrat/Montserrat-ExtraBold.otf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
ACCENT = {"ai": (64, 116, 255), "biz": (232, 84, 46)}


def log(*a):
    print(*a, flush=True)


def find_font():
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    out = subprocess.run(["fc-match", "-f", "%{file}", "sans:bold"], capture_output=True, text=True)
    return out.stdout.strip()


FONT = find_font()
FONT_NAME = "Montserrat ExtraBold" if "Montserrat" in FONT else "DejaVu Sans"


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {r.stderr[-800:]}")
    return r.stdout


def duration_of(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                      "-of", "default=nw=1:nk=1", str(path)]).strip())


# ---------- Apps Script ----------

def fetch_queue():
    r = requests.get(WEBAPP_URL, params={"action": "queue", "key": REELS_KEY}, timeout=60)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    return data.get("items", [])


def send_result(item, result):
    body = {"key": REELS_KEY, "action": "result", "table": item["table"],
            "row": item["row"], "result": result}
    r = requests.post(WEBAPP_URL, data=json.dumps(body),
                      headers={"Content-Type": "text/plain"}, timeout=60)
    log("result ->", r.status_code, r.text[:200])


# ---------- текст ----------

def parse_scenes(raw):
    scenes = []
    for line in raw.strip().splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(" | ")]
        if len(parts) < 5:
            raise ValueError(f"плохая строка сцены: {line[:80]}")
        num, kind, param, titr = parts[:4]
        frag = " | ".join(parts[4:])
        scenes.append({"kind": kind.lower(), "param": param, "titr": titr, "text": frag})
    if not scenes:
        raise ValueError("нет сцен")
    return scenes


def wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=font) <= max_w or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_text(draw, text, max_w, max_h, start=120, minimum=56):
    size = start
    while size >= minimum:
        font = ImageFont.truetype(FONT, size)
        lines = wrap(draw, text, font, max_w)
        lh = int(size * 1.18)
        if lh * len(lines) <= max_h:
            return font, lines, lh
        size -= 6
    font = ImageFont.truetype(FONT, minimum)
    return font, wrap(draw, text, font, max_w), int(minimum * 1.18)


# ---------- озвучка ----------

async def _tts(text, mp3):
    import edge_tts
    try:
        comm = edge_tts.Communicate(text, VOICE, rate=TTS_RATE, boundary="WordBoundary")
    except TypeError:
        comm = edge_tts.Communicate(text, VOICE, rate=TTS_RATE)
    words = []
    with open(mp3, "wb") as f:
        async for ch in comm.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                s = ch["offset"] / 1e7
                words.append([s, s + ch["duration"] / 1e7, ch["text"]])
    return words


def tts(text, mp3):
    return asyncio.run(_tts(text, mp3))


def align_words(text, words, total):
    """Каждому слову озвучки — позиция в тексте. Если таймингов нет, делим по символам."""
    low = text.lower()
    out, pos = [], 0
    for s, e, w in words:
        i = low.find(w.lower(), pos)
        if i < 0:
            continue
        out.append({"start": s, "end": e, "pos": i, "len": len(w)})
        pos = i + len(w)
    if len(out) >= max(3, len(words) // 2):
        return out
    out, t = [], 0.0
    tokens = [(m.start(), m.group()) for m in re.finditer(r"\S+", text)]
    per = total / max(1, len(text))
    for i, w in tokens:
        d = len(w) * per
        out.append({"start": i * per, "end": i * per + d, "pos": i, "len": len(w)})
    return out


def time_at(aligned, char_pos, total):
    for w in aligned:
        if w["pos"] >= char_pos:
            return w["start"]
    return total


def scene_timings(text, scenes, aligned, total):
    bounds, pos = [], 0
    for sc in scenes:
        i = text.find(sc["text"], pos)
        if i < 0:
            i = pos
        bounds.append(i)
        pos = i + len(sc["text"])
    starts = [0.0] + [time_at(aligned, b, total) for b in bounds[1:]]
    ends = starts[1:] + [total + TAIL]
    out = []
    for s, e in zip(starts, ends):
        out.append(max(0.8, e - s))
    return out


def ass_time(t):
    t = max(0, t)
    h, m = int(t // 3600), int(t % 3600 // 60)
    return f"{h}:{m:02d}:{t % 60:05.2f}"


def make_subs(text, aligned, path):
    chunks, cur = [], []
    for w in aligned:
        cur.append(w)
        word = text[w["pos"]:w["pos"] + w["len"]]
        chars = sum(x["len"] for x in cur) + len(cur)
        if len(cur) >= 3 or chars > 18 or re.search(r"[.!?,:;]$", text[w["pos"]:w["pos"] + w["len"] + 1].strip() or word):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    lines = []
    for i, ch in enumerate(chunks):
        start = ch[0]["start"]
        end = chunks[i + 1][0]["start"] if i + 1 < len(chunks) else ch[-1]["end"] + 0.3
        a, b = ch[0]["pos"], ch[-1]["pos"] + ch[-1]["len"]
        shown = re.sub(r"\s+", " ", text[a:b]).strip()
        shown = shown.replace("{", "(").replace("}", ")")
        lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Sub,,0,0,0,,{shown}")
    head = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 0\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, "
        "Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Sub,{FONT_NAME},84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,2,2,80,80,520,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    Path(path).write_text(head + "\n".join(lines) + "\n", encoding="utf-8")


# ---------- картинки ----------

def gradient_bg(table):
    acc = ACCENT.get(table, (90, 90, 90))
    img = Image.new("RGB", (W, H), (14, 15, 20))
    top = Image.new("RGB", (W, H), tuple(int(c * 0.55) for c in acc))
    mask = Image.linear_gradient("L").resize((W, H)).point(lambda v: 255 - v)
    img.paste(top, (0, 0), mask)
    return img


def title_image(text, table, path):
    img = gradient_bg(table)
    d = ImageDraw.Draw(img)
    font, lines, lh = fit_text(d, text or " ", W - 180, 900)
    y = (H - lh * len(lines)) // 2 - 120
    for ln in lines:
        w = d.textlength(ln, font=font)
        d.text(((W - w) / 2, y), ln, font=font, fill="white")
        y += lh
    acc = ACCENT.get(table, (200, 200, 200))
    d.rounded_rectangle(((W - 160) / 2, y + 40, (W + 160) / 2, y + 56), radius=8, fill=acc)
    img.save(path, quality=95)


def titr_overlay(text, path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font, lines, lh = fit_text(d, text, W - 240, 300, start=72, minimum=48)
    bw = max(d.textlength(ln, font=font) for ln in lines) + 80
    bh = lh * len(lines) + 50
    x0, y0 = (W - bw) / 2, 230
    d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), radius=28, fill=(0, 0, 0, 170))
    y = y0 + 25
    for ln in lines:
        w = d.textlength(ln, font=font)
        d.text(((W - w) / 2, y), ln, font=font, fill="white")
        y += lh
    img.save(path)


def fill_frame(src, path):
    im = Image.open(src).convert("RGB")
    bg = im.copy()
    scale = max(W / bg.width, H / bg.height)
    bg = bg.resize((int(bg.width * scale) + 1, int(bg.height * scale) + 1))
    bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
    bg = bg.filter(ImageFilter.GaussianBlur(40)).point(lambda v: int(v * 0.55))
    fg_scale = min(W / im.width, (H * 0.6) / im.height)
    fg = im.resize((int(im.width * fg_scale), int(im.height * fg_scale)))
    bg.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2))
    bg.save(path, quality=95)


# ---------- источники сцен ----------

def og_image(url, out):
    r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
    r.raise_for_status()
    m = re.search(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]*content=["\']([^"\']+)', r.text, re.I) \
        or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\'](?:og:image|twitter:image)', r.text, re.I)
    if not m:
        raise RuntimeError("нет og:image")
    img_url = requests.compat.urljoin(url, m.group(1).replace("&amp;", "&"))
    ir = requests.get(img_url, headers={"User-Agent": UA}, timeout=20)
    ir.raise_for_status()
    Path(out).write_bytes(ir.content)
    Image.open(out).verify()


def site_shot(url, out):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome")
        except Exception:
            b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 432, "height": 768}, device_scale_factor=2.5,
                            user_agent=UA, is_mobile=True, has_touch=True, locale="en-US")
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3500)
        for sel in ["button:has-text('Accept')", "button:has-text('Agree')", "button:has-text('Accept all')",
                    "button:has-text('Принять')", "button:has-text('OK')"]:
            try:
                page.locator(sel).first.click(timeout=800)
                break
            except Exception:
                pass
        page.screenshot(path=out, full_page=True)
        b.close()
    im = Image.open(out).convert("RGB")
    im = im.resize((W, int(im.height * W / im.width)))
    im = im.crop((0, 0, W, min(im.height, H * 4)))
    if im.height < H:
        raise RuntimeError("страница слишком короткая")
    im.save(out)


def stock_clip(query, out):
    """Стоковое видео с Pixabay (бесплатный ключ). Pexels — запасной, если есть ключ."""
    if PIXABAY_KEY:
        r = requests.get("https://pixabay.com/api/videos/",
                         params={"key": PIXABAY_KEY, "q": query, "per_page": 20,
                                 "safesearch": "true", "min_height": 720}, timeout=30)
        r.raise_for_status()
        hits = [h for h in r.json().get("hits", []) if h.get("duration", 0) >= 4]
        if not hits:
            raise RuntimeError(f"pixabay: ничего по «{query}»")
        # сначала вертикальные ролики, среди них случайный из первых пяти
        hits.sort(key=lambda h: h["videos"]["medium"].get("height", 0) <= h["videos"]["medium"].get("width", 1))
        h = random.choice(hits[:5])
        v = h["videos"].get("medium") or h["videos"].get("small")
        link = v["url"]
    elif PEXELS_KEY:
        r = requests.get("https://api.pexels.com/videos/search",
                         params={"query": query, "orientation": "portrait", "per_page": 10},
                         headers={"Authorization": PEXELS_KEY}, timeout=30)
        r.raise_for_status()
        vids = [v for v in r.json().get("videos", []) if v.get("duration", 0) >= 4]
        if not vids:
            raise RuntimeError(f"pexels: ничего по «{query}»")
        v = random.choice(vids[:5])
        files = [f for f in v["video_files"] if f.get("height") and f["height"] >= 1280]
        files = files or [f for f in v["video_files"] if f.get("height")]
        link = min(files, key=lambda x: abs(x["height"] - 1920))["link"]
    else:
        raise RuntimeError("нет PIXABAY_API_KEY")
    with requests.get(link, stream=True, timeout=60, headers={"User-Agent": UA}) as rr:
        rr.raise_for_status()
        with open(out, "wb") as fh:
            for chunk in rr.iter_content(1 << 20):
                fh.write(chunk)


# ---------- рендер сцен ----------

ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS), "-an"]


def render_still(img, dur, out, overlay=None):
    frames = max(1, round(dur * FPS))
    zoom = f"zoompan=z='min(zoom+0.0007,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS}"
    cmd = ["ffmpeg", "-y", "-loop", "1", "-i", img]
    if overlay:
        cmd += ["-loop", "1", "-i", overlay, "-filter_complex", f"[0:v]scale={W}:{H},{zoom}[b];[b][1:v]overlay=0:0"]
    else:
        cmd += ["-vf", f"scale={W}:{H},{zoom}"]
    run(cmd + ["-frames:v", str(frames)] + ENC + [out])


def render_scroll(img, dur, out, overlay=None):
    frames = max(1, round(dur * FPS))
    crop = f"crop={W}:{H}:0:'min(max(0,(t-0.4))/{max(dur - 0.8, 0.5):.2f},1)*(ih-{H})'"
    cmd = ["ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", img]
    if overlay:
        cmd += ["-loop", "1", "-i", overlay, "-filter_complex", f"[0:v]{crop}[b];[b][1:v]overlay=0:0"]
    else:
        cmd += ["-vf", crop]
    run(cmd + ["-frames:v", str(frames)] + ENC + [out])


def render_clip(src, dur, out, overlay=None):
    frames = max(1, round(dur * FPS))
    base = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1"
    cmd = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", src]
    if overlay:
        cmd += ["-loop", "1", "-i", overlay, "-filter_complex", f"[0:v]{base}[b];[b][1:v]overlay=0:0"]
    else:
        cmd += ["-vf", base]
    run(cmd + ["-frames:v", str(frames)] + ENC + [out])


def render_scene(sc, dur, idx, item, work):
    table = item["table"]
    out = str(work / f"scene{idx:02d}.mp4")
    overlay = None
    if sc["titr"] and sc["kind"] != "title":
        overlay = str(work / f"titr{idx}.png")
        titr_overlay(sc["titr"], overlay)
    kind = sc["kind"]
    try:
        if kind == "site":
            shot = str(work / f"site{idx}.png")
            site_shot(sc["param"] or item["link"], shot)
            render_scroll(shot, dur, out, overlay)
            return out
        if kind == "stock":
            clip = str(work / f"stock{idx}.mp4")
            stock_clip(sc["param"] or "technology", clip)
            render_clip(clip, dur, out, overlay)
            return out
        if kind == "cover":
            raw = str(work / f"og{idx}")
            og_image(item["link"], raw)
            img = str(work / f"cover{idx}.jpg")
            fill_frame(raw, img)
            render_still(img, dur, out, overlay)
            return out
    except Exception as e:
        log(f"сцена {idx + 1} ({kind}) -> титр вместо неё: {e}")
    img = str(work / f"title{idx}.jpg")
    title_image(sc["titr"] or item.get("cover") or "", table, img)
    render_still(img, dur, out)
    return out


# ---------- сборка ----------

def build(item, work):
    text = item["voice"].strip()
    scenes = parse_scenes(item["scenes"])
    joined = " ".join(s["text"] for s in scenes)
    if re.sub(r"\s+", " ", joined) != re.sub(r"\s+", " ", text):
        raise ValueError("фрагменты сцен не совпадают с озвучкой")

    mp3 = str(work / "voice.mp3")
    words = tts(text, mp3)
    total = duration_of(mp3)
    aligned = align_words(text, words, total)
    durs = scene_timings(text, scenes, aligned, total)
    log(f"озвучка {total:.1f} c, сцены: {[round(d, 1) for d in durs]}")

    parts = [render_scene(sc, d, i, item, work) for i, (sc, d) in enumerate(zip(scenes, durs))]
    lst = work / "list.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    joined_mp4 = str(work / "joined.mp4")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", joined_mp4])

    subs = str(work / "subs.ass")
    make_subs(text, aligned, subs)
    fonts_dir = str(Path(FONT).parent)
    final = str(work / "reel.mp4")
    length = total + TAIL
    run(["ffmpeg", "-y", "-i", joined_mp4, "-i", mp3,
         "-filter_complex", f"[0:v]subtitles={subs}:fontsdir={fonts_dir}[v];[1:a]apad,aresample=48000[a]",
         "-map", "[v]", "-map", "[a]", "-t", f"{length:.2f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-r", str(FPS),
         "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", final])

    cover = str(work / "cover.jpg")
    title_image(item.get("cover") or scenes[0]["titr"], item["table"], cover)
    return final, cover, length


def upload(item, video, cover):
    stamp = dt.datetime.utcnow().strftime("%Y%m%d-%H%M")
    tag = f"reel-{item['table']}-{item['row']}-{stamp}"
    run(["gh", "release", "create", tag, video, cover, "--title", tag,
         "--notes", f"{item['table']} строка {item['row']} ({item.get('date', '')})"])
    base = f"https://github.com/{REPO}/releases/download/{tag}"
    return f"{base}/reel.mp4", f"{base}/cover.jpg", tag


def append_log(line):
    p = Path("log/builds.csv")
    p.parent.mkdir(exist_ok=True)
    if not p.exists():
        p.write_text("время_utc;таблица;строка;результат\n", encoding="utf-8")
    with p.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    if not WEBAPP_URL or not REELS_KEY:
        sys.exit("нет REELS_WEBAPP_URL или REELS_KEY")
    items = fetch_queue()
    log(f"в очереди: {len(items)}")
    now = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    for item in items[:MAX_ITEMS]:
        log(f"== {item['table']} строка {item['row']}")
        work = Path(tempfile.mkdtemp())
        try:
            video, cover, length = build(item, work)
            v_url, c_url, tag = upload(item, video, cover)
            send_result(item, f"собран | {v_url} | {c_url}")
            append_log(f"{now};{item['table']};{item['row']};собран {length:.1f} c {tag}")
        except Exception as e:
            traceback.print_exc()
            msg = str(e).replace("\n", " ")[:300]
            send_result(item, f"ошибка сборки: {msg}")
            append_log(f"{now};{item['table']};{item['row']};ошибка: {msg}")
        finally:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
