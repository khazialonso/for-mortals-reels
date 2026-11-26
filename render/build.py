"""Сборщик рилсов For Mortals v3: ElevenLabs (голос + тайминги) -> HyperFrames.

Очередь берётся из Apps Script (лист «Рилсы», статус «в очереди», проверка «ок», пустой «Результат»).
Сцены в ячейке «Сцены»: одна строка — одна сцена:  № | тип | визуал | экран | фрагмент озвучки
Типы: hook, source, item, number, compare, tip, big, final.
Тест без таблицы: TEST_ITEMS=render/test_items.json — результат кладётся в out/, без загрузки.
"""
import base64
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

HERE = Path(__file__).resolve().parent
ICONS = HERE / "icons"
KEY = os.environ.get("ELEVENLABS_API_KEY", "")
MODEL = os.environ.get("TTS_MODEL", "eleven_multilingual_v2")
WEBAPP_URL = os.environ.get("REELS_WEBAPP_URL", "")
REELS_KEY = os.environ.get("REELS_KEY", "")
REPO = os.environ.get("GITHUB_REPOSITORY", "")
MAX_ITEMS = int(os.environ.get("MAX_ITEMS", "2"))
TEST = os.environ.get("TEST_ITEMS", "")
W, H = 1080, 1920
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
TYPES = {"hook", "source", "item", "number", "compare", "tip", "big", "final"}

CHANNELS = {
    "ai": dict(name="AI for Mortals", handle="@ai_for_mortals", voice="kwajW3Xh5svCeKU5ky2S", char="flash",
               bg="#0F1B4D", grid=False, ink="#FFFFFF", accent="#FFD23F", accent2="#4074FF", dim="rgba(255,255,255,0.5)",
               muted="rgba(255,255,255,0.8)", card="#FFFFFF", cardink="#111111", blob="#4074FF", blobop=0.45,
               seg="rgba(255,255,255,0.18)", hl="#FFD23F", hlink="#111111", shadow="0 30px 80px rgba(0,0,0,0.35)",
               eyes="180 217", arm="114 252"),
    "biz": dict(name="Biz for Mortals", handle="@biz_for_mortals", voice="3EuKHIEZbSzrHGNmdYsx", char="calc",
                bg="#FAFAF7", grid=True, ink="#111111", accent="#E8542E", accent2="#E8542E", dim="#B8B1A6",
                muted="#8A8378", card="#FFFFFF", cardink="#111111", blob="#E8542E", blobop=0.10,
                seg="#ECE6DA", hl="#E8542E", hlink="#FFFFFF", shadow="0 24px 60px rgba(43,33,24,0.14)",
                eyes="195 136", arm="116 178"),
}


def log(*a):
    print(*a, flush=True)


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def run(cmd, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} {cmd[1] if len(cmd) > 1 else ''}: {(r.stderr or r.stdout)[-600:]}")
    return r.stdout


# ---------- сцены ----------

def parse_scenes(raw, voice):
    scenes = []
    for line in str(raw).strip().splitlines():
        if not line.strip():
            continue
        p = [x.strip() for x in re.split(r"\s*\|\s*", line.strip(), maxsplit=4)]
        if len(p) < 5:
            raise ValueError(f"плохая строка сцены: {line[:80]}")
        kind = p[1].lower()
        if kind not in TYPES:
            raise ValueError(f"неизвестный тип сцены «{kind}»")
        icons = [x.strip().lower().replace(" ", "_") for x in p[2].split(",") if x.strip()]
        scenes.append({"kind": kind, "icons": [i for i in icons if (ICONS / f"{i}.png").exists()],
                       "screen": p[3], "text": p[4]})
    if not scenes:
        raise ValueError("нет сцен")
    joined = re.sub(r"\s+", " ", " ".join(s["text"] for s in scenes)).strip()
    if joined != re.sub(r"\s+", " ", voice).strip():
        raise ValueError("фрагменты сцен не совпадают с озвучкой")
    # подряд идущие item — один экран-список
    out = []
    for s in scenes:
        if s["kind"] == "item" and out and out[-1]["kind"] == "list":
            out[-1]["items"].append(s)
        elif s["kind"] == "item":
            out.append({"kind": "list", "items": [s], "icons": [], "screen": "", "text": None})
        else:
            out.append(s)
    return out


def lines_of(screen):
    """«строка / строка» -> до 3 строк; [слово] — подчёркнутое ключевое слово."""
    return [esc(x.strip()) for x in screen.split(" / ") if x.strip()][:3]


def mk(ln):
    return re.sub(r"\[([^\]]+)\]", r'<span class="mk">\1</span>', ln)


# ---------- данные ----------

def tts(text, voice, out):
    last = None
    for attempt in range(3):
        try:
            r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps",
                              headers={"xi-api-key": KEY},
                              json={"text": text, "model_id": MODEL,
                                    "voice_settings": {"stability": 0.4, "similarity_boost": 0.8, "style": 0.35}},
                              timeout=180)
            r.raise_for_status()
            d = r.json()
            (out / "voice.mp3").write_bytes(base64.b64decode(d["audio_base64"]))
            a = d.get("alignment") or d.get("normalized_alignment")
            return a["characters"], a["character_start_times_seconds"], a["character_end_times_seconds"]
        except Exception as e:
            last = e
    raise RuntimeError(f"ElevenLabs: {last}")


def get(url, dst):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=25)
        if r.status_code == 200 and len(r.content) > 500:
            dst.write_bytes(r.content)
            return True
    except Exception as e:
        log("нет", url, e)
    return False


def page_assets(link, ad):
    cover = logo = None
    try:
        html = requests.get(link, headers={"User-Agent": UA}, timeout=25).text
        m = re.search(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]*content=["\']([^"\']+)', html, re.I) \
            or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\'](?:og:image|twitter:image)', html, re.I)
        if m and get(requests.compat.urljoin(link, m.group(1).replace("&amp;", "&")), ad / "cover.img"):
            cover = "assets/cover.img"
    except Exception as e:
        log("обложка:", e)
    dom = re.sub(r"^www\.", "", requests.compat.urlparse(link).netloc)
    if get(f"https://www.google.com/s2/favicons?domain={dom}&sz=128", ad / "logo.png"):
        logo = "assets/logo.png"
    return cover, logo, dom


def words_from(chars, st, en):
    words, cur = [], None
    for c, s, e in zip(chars, st, en):
        if c.isspace():
            if cur:
                words.append(cur)
            cur = None
            continue
        if cur is None:
            cur = {"w": "", "s": s, "e": e}
        cur["w"] += c
        cur["e"] = e
    if cur:
        words.append(cur)
    return words


def mouth_track(chars, st, en):
    raw = []
    for i, (c, s, e) in enumerate(zip(chars, st, en)):
        lc = c.lower()
        if lc in "аоуыэяёю":
            raw.append((s, "open"))
        elif lc in "еи":
            raw.append((s, "mid"))
        elif lc in "мбпвф":
            raw.append((s, "closed"))
        elif not lc.isalpha():
            nxt = st[i + 1] if i + 1 < len(st) else e + 1
            if nxt - e > 0.12 or lc in ".,!?:;":
                raw.append((e, "closed"))
    out = []
    for t, m in raw:
        if out and (out[-1][1] == m or t - out[-1][0] < 0.09):
            continue
        out.append((round(t, 3), m))
    return out


# ---------- композиция ----------

def compose(item, scenes, chars, st, en, cover, logo, dom, out):
    C = CHANNELS[item["table"]]
    rnd = random.Random(item.get("row", 1))
    words = words_from(chars, st, en)
    total = round(en[-1] + 0.9, 2)
    # начало каждого экрана = первое слово его первого фрагмента
    texts = [(s["items"][0]["text"] if s["kind"] == "list" else s["text"]) for s in scenes]
    starts, wi = [], 0
    for s in scenes:
        starts.append(words[min(wi, len(words) - 1)]["s"])
        frs = [x["text"] for x in s["items"]] if s["kind"] == "list" else [s["text"]]
        wi += sum(len(f.split()) for f in frs)
    starts[0] = 0.0
    ends = starts[1:] + [total]
    js, html, digits = [], [], []
    J = js.append

    def icon(k, style, cls):
        return f'<img class="ic {cls}" src="assets/i_{k}.png" style="{style}"/>' if k else ""

    def head(sid, a, screen):
        h = '<div class="head">'
        for j, ln in enumerate(lines_of(screen)):
            h += f'<div class="ln" id="{sid}l{j}">{mk(ln)}</div>'
            J(f'tl.from("#{sid}l{j}",{{opacity:0,y:70,duration:0.4,ease:"power3.out"}},{a + 0.1 * j:.3f});')
        J(f'tl.from("#{sid} .mk",{{"--u":0,duration:0.45,ease:"power2.out"}},{a + 0.35:.3f});')
        return h + "</div>"

    for i, (s, a, b) in enumerate(zip(scenes, starts, ends)):
        sid, dur, k = f"s{i}", round(b - a, 3), s["kind"]
        ic = s["icons"] + [None, None]
        h, v = "", '<div class="vz">'
        if k == "hook":
            h = head(sid, a, s["screen"])
            v += icon(ic[0], "left:170px;top:60px;width:400px;transform:rotate(-10deg)", "f1")
            v += icon(ic[1], "left:560px;top:230px;width:320px;transform:rotate(12deg)", "f2")
        elif k == "source":
            h = head(sid, a, s["screen"])
            if cover:
                img = f'<img class="cov" src="{cover}"/>'
            else:  # сайт не отдал обложку: крупный логотип и адрес
                img = (f'<div class="cov ph">' + (f'<img src="{logo}"/>' if logo else "") + f'<span>{esc(dom)}</span></div>')
            lg = f'<img class="lg" src="{logo}"/>' if logo else ""
            v += (f'<div class="browser" id="{sid}br"><div class="bar"><i></i><i></i><i></i><span>{lg}{esc(dom)}</span></div>'
                  f'<div class="covwrap">{img}</div></div>')
            v += icon(ic[0], "left:780px;top:-80px;width:240px;transform:rotate(10deg)", "f1")
            J(f'tl.from("#{sid}br",{{y:200,opacity:0,rotation:-4,duration:0.55,ease:"back.out(1.4)"}},{a + 0.2:.3f});')
            J(f'tl.fromTo("#{sid} .cov",{{scale:1}},{{scale:1.12,duration:{dur},ease:"none"}},{a:.3f});')
        elif k == "list":
            v = '<div class="vz list">'
            for j, it in enumerate(s["items"]):
                t = next((w["s"] for w in words if w["s"] >= a - 0.01 and w["w"] == it["text"].split()[0]), a + 1.2 * j)
                im = f'<img src="assets/i_{it["icons"][0]}.png"/>' if it["icons"] else f"<b>{j + 1}</b>"
                v += f'<div class="row" id="{sid}r{j}">{im}<span>{esc(it["screen"])}</span></div>'
                J(f'tl.from("#{sid}r{j}",{{x:-140,opacity:0,duration:0.4,ease:"back.out(1.6)"}},{t - 0.1:.3f});')
                J(f'tl.from("#{sid}r{j} img",{{scale:0,rotation:-40,duration:0.45,ease:"back.out(2.2)"}},{t:.3f});')
        elif k == "number":
            val, _, cap = s["screen"].partition(" / ")
            nfs = min(250, int(1750 / max(1, len(val.strip()))))
            v += f'<div class="num" id="{sid}n" style="font-size:{nfs}px">{esc(val.strip())}</div><div class="cap" id="{sid}c">{esc(cap.strip())}</div>'
            v += icon(ic[0], "left:800px;top:330px;width:200px", "f1")
            J(f'tl.from("#{sid}n",{{scale:0.5,opacity:0,duration:0.5,ease:"back.out(2)"}},{a + 0.1:.3f});')
            J(f'tl.from("#{sid}c",{{opacity:0,y:40,duration:0.3}},{a + 0.45:.3f});')
            if C["char"] == "calc":
                digits.append((a, b, val.strip()))
        elif k == "compare":
            parts = [p.strip() for p in s["screen"].split(" / ")][:2]
            cards = ""
            for j, p in enumerate(parts):
                lab, _, val = p.partition(":")
                cards += f'<div class="cmp{" hot" if j else ""}" id="{sid}c{j}"><small>{esc(lab.strip())}</small><b>{esc(val.strip())}</b></div>'
                J(f'tl.from("#{sid}c{j}",{{y:120,opacity:0,duration:0.45,ease:"back.out(1.6)"}},{a + 0.2 + 0.5 * j:.3f});')
            v += f'<div class="cmpwrap">{cards}<div class="arrow" id="{sid}ar">→</div></div>'
            J(f'tl.from("#{sid}ar",{{scale:0,duration:0.3,ease:"back.out(3)"}},{a + 0.55:.3f});')
        elif k == "tip":
            v += f'<div class="quote" id="{sid}q"><div class="qq">“</div>{esc(s["screen"])}</div>'
            v += icon(ic[0], "left:30px;top:-70px;width:210px;transform:rotate(-12deg)", "f1")
            v += icon(ic[1], "left:810px;top:440px;width:190px", "f2")
            J(f'tl.from("#{sid}q",{{scale:0.7,opacity:0,duration:0.5,ease:"back.out(1.7)"}},{a + 0.25:.3f});')
        elif k == "big":
            h = head(sid, a, s["screen"])
            v += icon(ic[0], "left:310px;top:80px;width:460px", "f1")
            v += icon(ic[1], "left:110px;top:40px;width:180px", "f2")
            v += icon(ic[1], "left:780px;top:340px;width:150px", "f3")
        elif k == "final":
            h = head(sid, a, s["screen"])
            v += icon(ic[0], "left:390px;top:10px;width:300px", "f1")
            v += f'<div class="tgpill" id="{sid}tg">Разбор в Telegram · {esc(C["handle"])}</div>'
            J(f'tl.from("#{sid}tg",{{y:60,opacity:0,duration:0.4,ease:"power3.out"}},{a + 0.6:.3f});')
        v += "</div>"
        for c, d0 in ((".f1", 0.15), (".f2", 0.35), (".f3", 0.55)):
            J(f'tl.from("#{sid} {c}",{{scale:0,opacity:0,duration:0.5,ease:"back.out(2)"}},{a + d0:.3f});')
            J(f'tl.to("#{sid} {c}",{{y:-22,duration:0.9,ease:"sine.inOut",yoyo:true,repeat:{max(1, int(dur / 0.9))}}},{a + d0 + 0.5:.3f});')
        html.append(f'<div class="scene clip" id="{sid}" data-start="{a:.3f}" data-duration="{dur}" data-track-index="2">{h}{v}</div>')
        J(f'tl.fromTo("#pg{i} i",{{scaleX:0}},{{scaleX:1,duration:{dur},ease:"none"}},{a:.3f});')

    # субтитры
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        if len(cur) >= 3 or re.search(r"[.,!?:;]$", w["w"]):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    subs, n = [], 0
    for ci, ch in enumerate(chunks):
        a = ch[0]["s"]
        b = chunks[ci + 1][0]["s"] if ci + 1 < len(chunks) else total
        sp = ""
        for w in ch:
            wid, off = f"w{n}", max(w["e"], w["s"] + 0.11) + 0.02
            n += 1
            sp += f'<span class="w" id="{wid}"><em></em><span>{esc(w["w"])}</span></span> '
            J(f'tl.set("#{wid}",{{color:"{C["ink"]}"}},{w["s"]:.3f});tl.fromTo("#{wid} em",{{scaleX:0}},{{scaleX:1,duration:0.1}},{w["s"]:.3f});'
              f'tl.set("#{wid} em",{{scaleX:0}},{off:.3f});tl.set("#{wid} span",{{color:"{C["hlink"]}"}},{w["s"]:.3f});'
              f'tl.set("#{wid} span",{{color:"{C["ink"]}"}},{off:.3f});')
        subs.append(f'<div class="sub clip" id="sub{ci}" data-start="{a:.3f}" data-duration="{round(b - a, 3)}" data-track-index="3">{sp}</div>')
        J(f'tl.from("#sub{ci}",{{y:20,opacity:0,duration:0.12}},{a:.3f});')

    # персонаж
    for t, m in mouth_track(chars, st, en):
        J(f'tl.set("#m-open",{{opacity:{int(m == "open")}}},{t});tl.set("#m-mid",{{opacity:{int(m == "mid")}}},{t});tl.set("#m-closed",{{opacity:{int(m == "closed")}}},{t});')
    J(f'tl.set("#m-open, #m-mid",{{opacity:0}},{en[-1] + 0.05:.3f});tl.set("#m-closed",{{opacity:1}},{en[-1] + 0.05:.3f});')
    J(f'tl.to("#breath",{{scaleY:1.018,scaleX:0.992,duration:1.4,ease:"sine.inOut",yoyo:true,repeat:{int(total / 1.4)}}},0);')
    t = 1.3
    while t < total - 0.4:
        J(f'tl.to("#eyes",{{scaleY:0.08,svgOrigin:"{C["eyes"]}",duration:0.05}},{t:.2f});tl.to("#eyes",{{scaleY:1,svgOrigin:"{C["eyes"]}",duration:0.09}},{t + 0.07:.2f});')
        t += rnd.uniform(2.6, 4.2)
    last = -9
    for w in words:
        if (w["e"] - w["s"] > 0.42) and w["s"] - last > 1.4:
            ts = w["s"]
            J(f'tl.to("#hop",{{y:-34,scaleY:1.05,scaleX:0.96,duration:0.14,ease:"power2.out"}},{ts:.3f});'
              f'tl.to("#hop",{{y:0,scaleY:0.93,scaleX:1.06,duration:0.12,ease:"power2.in"}},{ts + 0.14:.3f});'
              f'tl.to("#hop",{{scaleY:1,scaleX:1,duration:0.18,ease:"back.out(3)"}},{ts + 0.26:.3f});')
            last = ts
    for i, a in enumerate(starts):
        J(f'tl.to("#tilt",{{rotation:{4 if i % 2 else -4},duration:0.5,ease:"sine.inOut"}},{a:.3f});')
        J(f'tl.to("#pupils",{{x:4,y:-4,duration:0.2}},{a + 0.05:.3f});tl.to("#pupils",{{x:0,y:0,duration:0.3}},{a + 1.4:.3f});')
        if scenes[i]["kind"] in ("hook", "final"):
            J(f'tl.to("#arm",{{rotation:-16,svgOrigin:"{C["arm"]}",duration:0.2,ease:"sine.inOut",yoyo:true,repeat:5}},{a + 0.15:.3f});')
        else:
            J(f'tl.to("#arm",{{rotation:30,svgOrigin:"{C["arm"]}",duration:0.25,ease:"back.out(2)"}},{a + 0.1:.3f});'
              f'tl.to("#arm",{{rotation:0,svgOrigin:"{C["arm"]}",duration:0.35,ease:"power2.inOut"}},{a + 1.1:.3f});')
    dsvg = ""
    for j, (a, b, val) in enumerate(digits):  # калькулятор: цифра на дисплее
        fs = 46 if len(val) <= 5 else max(22, int(230 / len(val)))
        dsvg += f'<text id="dg{j}" x="195" y="{142 + fs * 0.35:.0f}" text-anchor="middle" font-family="Inter" font-weight="900" font-size="{fs}" fill="#2E3A24" opacity="0">{esc(val)}</text>'
        J(f'tl.set("#face",{{opacity:0}},{a + 0.1:.3f});tl.set("#dg{j}",{{opacity:1}},{a + 0.1:.3f});'
          f'tl.set("#dg{j}",{{opacity:0}},{b - 0.05:.3f});tl.set("#face",{{opacity:1}},{b - 0.05:.3f});')
    char = (HERE / "chars" / f"{C['char']}.svg").read_text(encoding="utf-8").replace("<!--DIGITS-->", dsvg)
    blobs = ""
    for j, (x, y, r) in enumerate([(-120, 380, 420), (760, 900, 380), (200, 1500, 300), (850, 200, 260)]):
        blobs += f'<div class="blob" id="b{j}" style="left:{x}px;top:{y}px;width:{r * 2}px;height:{r * 2}px"></div>'
        J(f'tl.to("#b{j}",{{x:{rnd.choice([-1, 1]) * rnd.randint(60, 140)},y:{rnd.choice([-1, 1]) * rnd.randint(60, 160)},duration:{total / 2:.2f},ease:"sine.inOut",yoyo:true,repeat:1}},0);')
    grid = ("background-image:linear-gradient(#EFEAE0 2px,transparent 2px),linear-gradient(90deg,#EFEAE0 2px,transparent 2px);background-size:60px 60px;"
            if C["grid"] else "")
    seg = "".join(f'<div class="seg" id="pg{i}"><i></i></div>' for i in range(len(scenes)))
    page = f"""<!doctype html>
<html lang="ru" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={W}, height={H}" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ width:{W}px; height:{H}px; overflow:hidden; background:{C['bg']}; }}
#root {{ position:relative; width:{W}px; height:{H}px; font-family:'Inter', sans-serif; color:{C['ink']}; overflow:hidden; }}
#bg {{ position:absolute; inset:0; {grid} }}
.blob {{ position:absolute; border-radius:50%; background:{C['blob']}; opacity:{C['blobop']}; filter:blur(40px); }}
.top {{ position:absolute; left:60px; right:60px; top:70px; display:flex; justify-content:space-between; font-weight:800; font-size:40px; }}
.segs {{ position:absolute; left:60px; right:60px; top:150px; display:flex; gap:12px; }}
.seg {{ flex:1; height:10px; border-radius:5px; background:{C['seg']}; overflow:hidden; }}
.seg i {{ display:block; height:100%; background:{C['accent']}; transform:scaleX(0); transform-origin:0 50%; }}
.scene {{ position:absolute; left:0; top:0; width:{W}px; height:{H}px; }}
.head {{ position:absolute; left:60px; right:60px; top:230px; }}
.ln {{ font-weight:900; font-size:104px; line-height:1.08; letter-spacing:-3px; }}
.mk {{ --u:1; position:relative; display:inline-block; }}
.mk::after {{ content:""; position:absolute; left:0; right:0; bottom:8px; height:16px; background:{C['accent']}; transform:scaleX(var(--u)); transform-origin:0 50%; z-index:-1; }}
.vz {{ position:absolute; left:0; right:0; top:560px; height:660px; }}
.vz.list {{ top:300px; height:920px; display:flex; flex-direction:column; justify-content:center; }}
.ic {{ position:absolute; }}
.browser {{ position:absolute; left:80px; top:30px; width:920px; height:600px; background:#fff; border-radius:36px; box-shadow:{C['shadow']}; overflow:hidden; }}
.bar {{ height:76px; background:#EEF1F7; display:flex; align-items:center; gap:12px; padding:0 26px; }}
.bar i {{ width:18px; height:18px; border-radius:9px; background:#C9CFDB; }}
.bar span {{ margin-left:18px; flex:1; height:46px; border-radius:23px; background:#fff; display:flex; align-items:center; gap:12px; padding:0 20px; font-size:28px; color:#555; font-weight:600; }}
.lg {{ width:30px; height:30px; border-radius:6px; }}
.covwrap {{ position:absolute; left:0; right:0; top:76px; bottom:0; overflow:hidden; }}
.cov {{ width:100%; height:100%; object-fit:cover; }}
.cov.ph {{ background:linear-gradient(135deg,#E3EBFF,#BFD2FF); display:flex; flex-direction:column; align-items:center; justify-content:center; gap:30px; }}
.cov.ph img {{ width:200px; height:200px; border-radius:40px; }}
.cov.ph span {{ font-size:64px; font-weight:900; color:#111; }}
.row {{ display:flex; align-items:center; gap:34px; margin:0 60px 34px; background:{C['card']}; color:{C['cardink']}; border-radius:48px; padding:34px 40px; font-size:58px; font-weight:800; line-height:1.1; box-shadow:{C['shadow']}; }}
.row img {{ width:150px; height:150px; flex:none; }}
.row b {{ width:120px; height:120px; border-radius:60px; background:{C['accent2']}; color:#fff; display:flex; align-items:center; justify-content:center; flex:none; }}
.num {{ position:absolute; left:60px; right:60px; top:20px; font-weight:900; font-size:250px; letter-spacing:-6px; color:{C['accent']}; line-height:1; white-space:nowrap; }}
.cap {{ position:absolute; left:60px; right:280px; top:330px; font-size:60px; font-weight:700; color:{C['muted']}; line-height:1.15; }}
.cmpwrap {{ position:absolute; left:60px; right:60px; top:60px; display:flex; gap:110px; }}
.cmp {{ flex:1; background:{C['card']}; color:{C['cardink']}; border-radius:44px; padding:46px 40px; box-shadow:{C['shadow']}; }}
.cmp small {{ display:block; font-size:46px; font-weight:700; color:#8A8378; margin-bottom:16px; }}
.cmp b {{ display:block; font-size:74px; font-weight:900; letter-spacing:-2px; line-height:1.05; white-space:nowrap; }}
.cmp.hot {{ background:{C['accent']}; color:{C['hlink']}; }}
.cmp.hot small {{ color:{C['hlink']}; opacity:0.85; }}
.arrow {{ position:absolute; left:50%; top:130px; transform:translateX(-50%); font-size:110px; font-weight:900; color:{C['accent']}; }}
.quote {{ position:absolute; left:60px; right:60px; top:70px; background:{C['card']}; color:{C['cardink']}; border-radius:48px; padding:90px 60px 70px; font-size:70px; font-weight:800; line-height:1.15; box-shadow:{C['shadow']}; }}
.qq {{ position:absolute; left:50px; top:-40px; font-size:220px; color:{C['accent2']}; line-height:1; }}
.tgpill {{ position:absolute; left:60px; right:60px; top:400px; text-align:center; background:{C['card']}; color:{C['cardink']}; border-radius:50px; padding:30px; font-size:48px; font-weight:800; box-shadow:{C['shadow']}; }}
.sub {{ position:absolute; left:60px; right:60px; top:1235px; text-align:center; font-weight:900; font-size:78px; line-height:1.2; color:{C['dim']}; }}
.w {{ position:relative; display:inline-block; }}
.w em {{ position:absolute; left:-10px; right:-10px; top:4px; bottom:4px; background:{C['hl']}; border-radius:14px; transform:scaleX(0); z-index:-1; }}
#char {{ position:absolute; left:-110px; top:1390px; width:640px; height:800px; }}
#tilt, #hop, #breath {{ width:100%; height:100%; transform-origin:50% 100%; }}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{total}" data-width="{W}" data-height="{H}">
<div id="bg" class="clip" data-start="0" data-duration="{total}" data-track-index="0">{blobs}</div>
<div id="topbar" class="top clip" data-start="0" data-duration="{total}" data-track-index="1"><span>{esc(C['name'])}</span></div>
<div id="progress" class="segs clip" data-start="0" data-duration="{total}" data-track-index="1">{seg}</div>
{''.join(html)}
{''.join(subs)}
<div id="char" class="clip" data-start="0" data-duration="{total}" data-track-index="4"><div id="tilt"><div id="hop"><div id="breath">{char}</div></div></div></div>
<audio id="voice" data-start="0" data-duration="{round(en[-1] + 0.3, 2)}" data-track-index="5" data-volume="1" src="voice.mp3"></audio>
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
{chr(10).join(js)}
window.__timelines = window.__timelines || {{}};
window.__timelines["main"] = tl;
tl.seek(0);
</script>
</body>
</html>"""
    (out / "index.html").write_text(page, encoding="utf-8")
    (out / "hyperframes.json").write_text('{"paths":{"assets":"assets"}}', encoding="utf-8")
    return total, starts


def build(item, work):
    if item["table"] not in CHANNELS:
        raise ValueError(f"неизвестная таблица {item['table']}")
    C = CHANNELS[item["table"]]
    voice = str(item["voice"]).strip()
    scenes = parse_scenes(item["scenes"], voice)
    proj = work / "proj"
    (proj / "assets").mkdir(parents=True)
    chars, st, en = tts(voice, C["voice"], proj)
    for s in scenes:
        for k in s.get("icons", []) + [i for it in s.get("items", []) for i in it["icons"]]:
            shutil.copy(ICONS / f"{k}.png", proj / "assets" / f"i_{k}.png")
    cover, logo, dom = page_assets(item["link"], proj / "assets")
    total, starts = compose(item, scenes, chars, st, en, cover, logo, dom, proj)
    log(f"сцены: {[round(x, 1) for x in starts]}, длина {total} c, обложка {'да' if cover else 'нет'}")
    video = work / "reel.mp4"
    run(["hyperframes", "render", str(proj), "-o", str(video), "-q", "delivery"])
    cov = work / "cover.jpg"
    run(["ffmpeg", "-y", "-v", "error", "-ss", "1.0", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(cov)])
    return video, cov, total


# ---------- таблица и загрузка ----------

def fetch_queue():
    r = requests.get(WEBAPP_URL, params={"action": "queue", "key": REELS_KEY}, timeout=60)
    r.raise_for_status()
    d = r.json()
    if "error" in d:
        raise RuntimeError(d["error"])
    return d.get("items", [])


def send_result(item, result):
    body = {"key": REELS_KEY, "action": "result", "table": item["table"], "row": item["row"], "result": result}
    r = requests.post(WEBAPP_URL, data=json.dumps(body), headers={"Content-Type": "text/plain"}, timeout=60)
    log("result ->", r.status_code, r.text[:200])


def upload(item, video, cover):
    tag = f"reel-{item['table']}-{item['row']}-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d-%H%M')}"
    err = ""
    for _ in range(4):
        r = subprocess.run(["gh", "release", "create", tag, str(video), str(cover), "--title", tag,
                            "--notes", f"{item['table']} строка {item['row']} ({item.get('date', '')})"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            base = f"https://github.com/{REPO}/releases/download/{tag}"
            return f"{base}/reel.mp4", f"{base}/cover.jpg", tag
        err = r.stderr[-300:]
        subprocess.run(["gh", "release", "delete", tag, "-y", "--cleanup-tag"], capture_output=True)
        subprocess.run(["sleep", "15"])
    raise RuntimeError(f"загрузка: {err}")


def append_log(line):
    p = Path("log/builds.csv")
    p.parent.mkdir(exist_ok=True)
    if not p.exists():
        p.write_text("время_utc;таблица;строка;результат\n", encoding="utf-8")
    with p.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    if not KEY:
        sys.exit("нет ELEVENLABS_API_KEY")
    if TEST:
        items = json.loads(Path(TEST).read_text(encoding="utf-8"))
        Path("out").mkdir(exist_ok=True)
        for it in items:
            work = Path(tempfile.mkdtemp())
            video, cov, total = build(it, work)
            shutil.copy(video, f"out/test_{it['table']}.mp4")
            shutil.copy(cov, f"out/test_{it['table']}.jpg")
            shutil.copy(work / "proj" / "index.html", f"out/test_{it['table']}.html")
            log("тест собран:", it["table"], total)
        return
    if not WEBAPP_URL or not REELS_KEY:
        sys.exit("нет REELS_WEBAPP_URL или REELS_KEY")
    items = fetch_queue()
    log(f"в очереди: {len(items)}")
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
    for item in items[:MAX_ITEMS]:
        log(f"== {item['table']} строка {item['row']}")
        work = Path(tempfile.mkdtemp())
        try:
            video, cov, total = build(item, work)
            v_url, c_url, tag = upload(item, video, cov)
            send_result(item, f"собран | {v_url} | {c_url}")
            append_log(f"{now};{item['table']};{item['row']};собран {total:.1f} c {tag}")
        except Exception as e:
            traceback.print_exc()
            msg = str(e).replace("\n", " ")[:300]
            send_result(item, f"ошибка сборки: {msg}")
            append_log(f"{now};{item['table']};{item['row']};ошибка: {msg}")
        finally:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
