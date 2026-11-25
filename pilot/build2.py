"""Пилот v2: реальная новость, визуал (обложка, лого, 3D-иконки), живой персонаж, форматы A и B."""
import base64
import json
import math
import os
import random
import re
import sys
from pathlib import Path
from urllib.parse import quote

import requests

KEY = os.environ.get("ELEVENLABS_API_KEY", "")
MODEL = os.environ.get("TTS_MODEL", "eleven_multilingual_v2")
W, H = 1080, 1920
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
FLUENT = "https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/assets/{folder}/3D/{file}_3d.png"
random.seed(7)

THEMES = {
    "A": dict(bg="#FFFFFF", ink="#111111", accent="#4074FF", dim="#C4C4C4", muted="#7A7A7A", card="#F2F5FC",
              cardink="#111111", blob="#4074FF", blobop=0.08, seg="#E8ECF5", hl="#4074FF", hlink="#111111", subcenter=False),
    "B": dict(bg="#3D6BFF", ink="#FFFFFF", accent="#FFD23F", dim="rgba(255,255,255,0.5)", muted="rgba(255,255,255,0.8)",
              card="#FFFFFF", cardink="#111111", blob="#7FA0FF", blobop=0.35, seg="rgba(255,255,255,0.3)", hl="#FFD23F",
              hlink="#111111", subcenter=True),
}


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------- данные ----------

def tts(text, voice, out):
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


def get(url, dst):
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=25)
        if r.status_code == 200 and len(r.content) > 500:
            dst.write_bytes(r.content)
            return True
        print("нет", url, r.status_code)
    except Exception as e:
        print("ошибка", url, e)
    return False


def assets(spec, out):
    ad = out / "assets"
    ad.mkdir(exist_ok=True)
    have = set()
    icons = []
    for s in spec["scenes"]:
        icons += s.get("icons", [])
        icons += [it[2] for it in s.get("items", [])]
    for folder, file in icons:
        if file in have:
            continue
        if get(FLUENT.format(folder=quote(folder), file=file), ad / f"{file}.png"):
            have.add(file)
    cover = None
    try:
        html = requests.get(spec["link"], headers={"User-Agent": UA}, timeout=25).text
        m = re.search(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]*content=["\']([^"\']+)', html, re.I) \
            or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\'](?:og:image|twitter:image)', html, re.I)
        if m and get(requests.compat.urljoin(spec["link"], m.group(1).replace("&amp;", "&")), ad / "cover.img"):
            cover = "assets/cover.img"
    except Exception as e:
        print("обложка:", e)
    logo = "assets/logo.png" if get(f"https://www.google.com/s2/favicons?domain={spec['domain']}&sz=128", ad / "logo.png") else None
    return have, cover, logo


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
    """Рот по слогам: гласная открывает, губные закрывают, пауза закрывает; минимум 90 мс на форму."""
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
        if out and out[-1][1] == m:
            continue
        if out and t - out[-1][0] < 0.09:
            continue
        out.append((round(t, 3), m))
    return out


# ---------- сборка ----------

CHAR = Path(__file__).with_name("char_flash.svg").read_text(encoding="utf-8")


def icon(file, have, cls, style):
    if file not in have:
        return ""
    return f'<img class="ic {cls}" src="assets/{file}.png" style="{style}"/>'


def build(fmt, spec, chars, st, en, have, cover, logo, out):
    T = THEMES[fmt]
    words = words_from(chars, st, en)
    total = round(en[-1] + 0.9, 2)
    idx, starts = 0, []
    for s in spec["scenes"]:
        starts.append(words[min(idx, len(words) - 1)]["s"])
        idx += len(s["text"].split())
    starts[0] = 0.0
    ends = starts[1:] + [total]
    js, html = [], []
    J = js.append

    for i, (s, a, b) in enumerate(zip(spec["scenes"], starts, ends)):
        sid, dur, k = f"s{i}", round(b - a, 3), s["kind"]
        sw = [w for w in words if a <= w["s"] < b]
        h = '<div class="head">'
        for j, ln in enumerate(s["lines"]):
            mk = s.get("mark") == j
            h += f'<div class="ln" id="{sid}l{j}"><span class="{"mk" if mk else ""}">{esc(ln)}</span></div>'
            J(f'tl.from("#{sid}l{j}",{{opacity:0,y:70,duration:0.4,ease:"power3.out"}},{a + 0.1 * j:.3f});')
        h += "</div>"
        if "mark" in s:
            J(f'tl.from("#{sid} .mk",{{"--u":0,duration:0.45,ease:"power2.out"}},{a + 0.35:.3f});')
        v = '<div class="vz">'
        ic = s.get("icons", [])
        if k == "hook":
            v += icon(ic[0][1], have, "f1", "left:170px;top:60px;width:400px;transform:rotate(-10deg)")
            v += icon(ic[1][1], have, "f2", "left:520px;top:220px;width:330px;transform:rotate(12deg)")
            v += '<div class="qmark">?</div>'
        elif k == "source":
            img = f'<img class="cov" src="{cover}"/>' if cover else '<div class="cov ph"></div>'
            lg = f'<img class="lg" src="{logo}"/>' if logo else ""
            v += (f'<div class="browser" id="{sid}br"><div class="bar"><i></i><i></i><i></i><span>{lg}{esc(spec["domain"])}</span></div>'
                  f'<div class="covwrap">{img}</div><div class="srcpill">{esc(spec["source"])}</div></div>')
            v += icon(ic[0][1], have, "f1", "left:760px;top:-70px;width:250px;transform:rotate(10deg)")
            J(f'tl.from("#{sid}br",{{y:200,opacity:0,rotation:-4,duration:0.55,ease:"back.out(1.4)"}},{a + 0.2:.3f});')
            J(f'tl.fromTo("#{sid} .cov",{{scale:1}},{{scale:1.12,duration:{dur},ease:"none"}},{a:.3f});')
        elif k == "list":
            for j, (anchor, label, (_, f)) in enumerate(s["items"]):
                t = next((w["s"] for w in sw if w["w"].lower().startswith(anchor)), a + 1.5 * (j + 1))
                im = f'<img src="assets/{f}.png"/>' if f in have else f'<b>{j + 1}</b>'
                v += f'<div class="row" id="{sid}r{j}">{im}<span>{esc(label)}</span></div>'
                J(f'tl.from("#{sid}r{j}",{{x:-140,opacity:0,duration:0.4,ease:"back.out(1.6)"}},{t - 0.1:.3f});')
                J(f'tl.from("#{sid}r{j} img",{{scale:0,rotation:-40,duration:0.45,ease:"back.out(2.2)"}},{t:.3f});')
        elif k == "tip":
            v += f'<div class="quote" id="{sid}q"><div class="qq">“</div>{esc(s["quote"])}</div>'
            v += icon(ic[0][1], have, "f1", "left:40px;top:-60px;width:220px;transform:rotate(-12deg)")
            v += icon(ic[1][1], have, "f2", "left:800px;top:420px;width:200px")
            J(f'tl.from("#{sid}q",{{scale:0.7,opacity:0,duration:0.5,ease:"back.out(1.7)"}},{a + 0.25:.3f});')
        elif k == "big":
            v += icon(ic[1][1], have, "f1", "left:310px;top:90px;width:460px")
            v += icon(ic[0][1], have, "f2", "left:120px;top:40px;width:180px")
            v += icon(ic[0][1], have, "f3", "left:770px;top:330px;width:150px")
        elif k == "final":
            v += icon(ic[0][1], have, "f1", "left:380px;top:20px;width:320px")
            v += f'<div class="tgpill" id="{sid}tg">{esc(s["note"])} · {esc(spec["handle"])}</div>'
            J(f'tl.from("#{sid}tg",{{y:60,opacity:0,duration:0.4,ease:"power3.out"}},{a + 0.6:.3f});')
        v += "</div>"
        # всплытие и парение иконок
        for c, d0 in ((".f1", 0.15), (".f2", 0.35), (".f3", 0.55)):
            J(f'tl.from("#{sid} {c}",{{scale:0,opacity:0,duration:0.5,ease:"back.out(2)"}},{a + d0:.3f});')
            rep = max(1, int(dur / 0.9))
            J(f'tl.to("#{sid} {c}",{{y:-22,duration:0.9,ease:"sine.inOut",yoyo:true,repeat:{rep}}},{a + d0 + 0.5:.3f});')
        if k == "hook":
            J(f'tl.from("#{sid} .qmark",{{scale:0,rotation:30,duration:0.5,ease:"back.out(2.5)"}},{a + 0.5:.3f});')
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
            wid = f"w{n}"
            n += 1
            sp += f'<span class="w" id="{wid}"><em></em><span>{esc(w["w"])}</span></span> '
            J(f'tl.set("#{wid}",{{color:"{T["ink"] if not T["subcenter"] else "#FFFFFF"}"}},{w["s"]:.3f});')
            J(f'tl.fromTo("#{wid} em",{{scaleX:0}},{{scaleX:1,duration:0.1}},{w["s"]:.3f});')
            J(f'tl.set("#{wid} em",{{scaleX:0}},{max(w["e"], w["s"] + 0.11) + 0.02:.3f});')
            if T["subcenter"]:
                J(f'tl.set("#{wid} span",{{color:"{T["hlink"]}"}},{w["s"]:.3f});tl.set("#{wid} span",{{color:"#FFFFFF"}},{max(w["e"], w["s"] + 0.11) + 0.02:.3f});')
        subs.append(f'<div class="sub clip" id="sub{ci}" data-start="{a:.3f}" data-duration="{round(b - a, 3)}" data-track-index="3">{sp}</div>')
        J(f'tl.from("#sub{ci}",{{y:20,opacity:0,duration:0.12}},{a:.3f});')

    # персонаж
    for t, m in mouth_track(chars, st, en):
        J(f'tl.set("#m-open",{{opacity:{int(m == "open")}}},{t});tl.set("#m-mid",{{opacity:{int(m == "mid")}}},{t});tl.set("#m-closed",{{opacity:{int(m == "closed")}}},{t});')
    J(f'tl.set("#m-open, #m-mid",{{opacity:0}},{en[-1] + 0.05:.3f});tl.set("#m-closed",{{opacity:1}},{en[-1] + 0.05:.3f});')
    J(f'tl.to("#breath",{{scaleY:1.018,scaleX:0.992,duration:1.4,ease:"sine.inOut",yoyo:true,repeat:{int(total / 1.4)}}},0);')
    t = 1.3
    while t < total - 0.4:
        J(f'tl.to("#eyes",{{scaleY:0.08,svgOrigin:"180 217",duration:0.05}},{t:.2f});tl.to("#eyes",{{scaleY:1,svgOrigin:"180 217",duration:0.09}},{t + 0.07:.2f});')
        t += random.uniform(2.6, 4.2)
    last = -9
    for w in words:  # подскок на длинных и важных словах
        if (w["e"] - w["s"] > 0.42 or any(ch.isdigit() for ch in w["w"])) and w["s"] - last > 1.4:
            ts = w["s"]
            J(f'tl.to("#hop",{{y:-34,scaleY:1.05,scaleX:0.96,duration:0.14,ease:"power2.out"}},{ts:.3f});'
              f'tl.to("#hop",{{y:0,scaleY:0.93,scaleX:1.06,duration:0.12,ease:"power2.in"}},{ts + 0.14:.3f});'
              f'tl.to("#hop",{{scaleY:1,scaleX:1,duration:0.18,ease:"back.out(3)"}},{ts + 0.26:.3f});')
            last = ts
    for i, a in enumerate(starts):
        J(f'tl.to("#tilt",{{rotation:{4 if i % 2 else -4},duration:0.5,ease:"sine.inOut"}},{a:.3f});')
        J(f'tl.to("#pupils",{{x:5,y:-5,duration:0.2}},{a + 0.05:.3f});tl.to("#pupils",{{x:0,y:0,duration:0.3}},{a + 1.4:.3f});')
        kind = spec["scenes"][i]["kind"]
        if kind in ("hook", "final"):
            J(f'tl.to("#arm",{{rotation:-18,svgOrigin:"114 252",duration:0.2,ease:"sine.inOut",yoyo:true,repeat:5}},{a + 0.15:.3f});')
        else:
            J(f'tl.to("#arm",{{rotation:38,svgOrigin:"114 252",duration:0.25,ease:"back.out(2)"}},{a + 0.1:.3f});'
              f'tl.to("#arm",{{rotation:0,svgOrigin:"114 252",duration:0.35,ease:"power2.inOut"}},{a + 1.1:.3f});')
        emo = spec["scenes"][i].get("emotion")
        if emo == "surprised":
            J(f'tl.to("#brows",{{y:-12,duration:0.15}},{a + 0.1:.3f});tl.to("#brows",{{y:0,duration:0.3}},{a + 1.6:.3f});')
        if emo == "happy":
            J(f'tl.to("#brows",{{y:-6,duration:0.15,yoyo:true,repeat:3}},{a + 0.2:.3f});')
    # фон: плавающие пятна
    blobs = ""
    for j, (x, y, r) in enumerate([(-120, 380, 420), (760, 900, 380), (200, 1500, 300), (850, 200, 260)]):
        blobs += f'<div class="blob" id="b{j}" style="left:{x}px;top:{y}px;width:{r * 2}px;height:{r * 2}px"></div>'
        J(f'tl.to("#b{j}",{{x:{random.choice([-1, 1]) * random.randint(60, 140)},y:{random.choice([-1, 1]) * random.randint(60, 160)},duration:{total / 2:.2f},ease:"sine.inOut",yoyo:true,repeat:1}},0);')

    seg = "".join(f'<div class="seg" id="pg{i}"><i></i></div>' for i in range(len(spec["scenes"])))
    subcss = (f".sub {{ position:absolute; left:60px; right:60px; top:1235px; text-align:center; font-weight:900; font-size:78px; line-height:1.2; color:{T['dim']}; }}"
              if T["subcenter"] else
              f".sub {{ position:absolute; left:480px; right:50px; top:1330px; font-weight:800; font-size:64px; line-height:1.22; color:{T['dim']}; }}")
    emcss = (f".w em {{ position:absolute; left:-10px; right:-10px; top:4px; bottom:4px; background:{T['hl']}; border-radius:14px; transform:scaleX(0); z-index:-1; }}"
             if T["subcenter"] else
             f".w em {{ position:absolute; left:0; right:0; bottom:-2px; height:12px; background:{T['hl']}; transform:scaleX(0); transform-origin:0 50%; }}")
    charcss = ("#char { position:absolute; left:-110px; top:1420px; width:600px; height:750px; }" if T["subcenter"]
               else "#char { position:absolute; left:-120px; top:1110px; width:760px; height:950px; }")
    page = f"""<!doctype html>
<html lang="ru" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={W}, height={H}" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ width:{W}px; height:{H}px; overflow:hidden; background:{T['bg']}; }}
#root {{ position:relative; width:{W}px; height:{H}px; font-family:'Inter', sans-serif; color:{T['ink']}; overflow:hidden; }}
.blob {{ position:absolute; border-radius:50%; background:{T['blob']}; opacity:{T['blobop']}; filter:blur(40px); }}
.top {{ position:absolute; left:60px; right:60px; top:70px; display:flex; justify-content:space-between; font-weight:800; font-size:40px; }}
.top .n {{ color:{T['muted']}; font-weight:600; }}
.segs {{ position:absolute; left:60px; right:60px; top:150px; display:flex; gap:12px; }}
.seg {{ flex:1; height:10px; border-radius:5px; background:{T['seg']}; overflow:hidden; }}
.seg i {{ display:block; height:100%; background:{T['accent']}; transform:scaleX(0); transform-origin:0 50%; }}
.scene {{ position:absolute; left:0; top:0; width:{W}px; height:{H}px; }}
.head {{ position:absolute; left:60px; right:60px; top:230px; }}
.ln {{ font-weight:900; font-size:104px; line-height:1.08; letter-spacing:-3px; }}
.mk {{ --u:1; position:relative; display:inline-block; }}
.mk::after {{ content:""; position:absolute; left:0; right:0; bottom:2px; height:22px; background:{T['accent']}; transform:scaleX(var(--u)); transform-origin:0 50%; z-index:-1; }}
.vz {{ position:absolute; left:0; right:0; top:560px; height:660px; }}
.ic {{ position:absolute; }}
.qmark {{ position:absolute; left:700px; top:-10px; font-size:300px; font-weight:900; color:{T['accent']}; transform:rotate(14deg); }}
.browser {{ position:absolute; left:80px; top:30px; width:920px; height:600px; background:#fff; border-radius:36px; box-shadow:0 30px 80px rgba(16,24,58,0.18); overflow:hidden; }}
.bar {{ height:76px; background:#EEF1F7; display:flex; align-items:center; gap:12px; padding:0 26px; }}
.bar i {{ width:18px; height:18px; border-radius:9px; background:#C9CFDB; }}
.bar span {{ margin-left:18px; flex:1; height:46px; border-radius:23px; background:#fff; display:flex; align-items:center; gap:12px; padding:0 20px; font-size:28px; color:#555; font-weight:600; }}
.lg {{ width:30px; height:30px; border-radius:6px; }}
.covwrap {{ position:absolute; left:0; right:0; top:76px; bottom:0; overflow:hidden; }}
.cov {{ width:100%; height:100%; object-fit:cover; }}
.cov.ph {{ background:linear-gradient(135deg,#E3EBFF,#BFD2FF); }}
.srcpill {{ position:absolute; left:30px; bottom:30px; background:#111; color:#fff; font-size:34px; font-weight:800; padding:14px 28px; border-radius:40px; }}
.row {{ display:flex; align-items:center; gap:30px; margin:0 60px 28px; background:{T['card']}; color:{T['cardink']}; border-radius:44px; padding:26px 34px; font-size:52px; font-weight:700; line-height:1.1; }}
.row img {{ width:130px; height:130px; flex:none; }}
.row b {{ width:110px; height:110px; border-radius:55px; background:#4074FF; color:#fff; display:flex; align-items:center; justify-content:center; }}
.quote {{ position:absolute; left:60px; right:60px; top:70px; background:{T['card']}; color:{T['cardink']}; border-radius:48px; padding:90px 60px 70px; font-size:72px; font-weight:800; line-height:1.15; }}
.qq {{ position:absolute; left:50px; top:-40px; font-size:220px; color:#4074FF; line-height:1; }}
.tgpill {{ position:absolute; left:60px; right:60px; top:420px; text-align:center; background:{T['card']}; color:{T['cardink']}; border-radius:50px; padding:30px; font-size:48px; font-weight:800; }}
{subcss}
.w {{ position:relative; display:inline-block; }}
{emcss}
{charcss}
#tilt, #hop, #breath {{ width:100%; height:100%; transform-origin:50% 100%; }}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{total}" data-width="{W}" data-height="{H}">
<div id="bg" class="clip" data-start="0" data-duration="{total}" data-track-index="0">{blobs}</div>
<div id="topbar" class="top clip" data-start="0" data-duration="{total}" data-track-index="1"><span>{esc(spec['channel'])}</span><span class="n">пилот v2 · {fmt}</span></div>
<div id="progress" class="segs clip" data-start="0" data-duration="{total}" data-track-index="1">{seg}</div>
{''.join(html)}
{''.join(subs)}
<div id="char" class="clip" data-start="0" data-duration="{total}" data-track-index="4"><div id="tilt"><div id="hop"><div id="breath">{CHAR}</div></div></div></div>
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
    print(fmt, "готово:", total, "c, сцены:", [round(x, 2) for x in starts])


def main():
    if not KEY:
        sys.exit("нет ELEVENLABS_API_KEY")
    spec = json.loads(Path(__file__).with_name("scenes_v2.json").read_text(encoding="utf-8"))
    base = Path("reel_v2")
    base.mkdir(exist_ok=True)
    full = " ".join(s["text"] for s in spec["scenes"])
    chars, st, en = tts(full, spec["voice_id"], base)
    have, cover, logo = assets(spec, base)
    print("иконки:", sorted(have), "обложка:", cover, "лого:", logo)
    for fmt in ("A", "B"):
        out = Path(f"reel_{fmt}")
        out.mkdir(exist_ok=True)
        os.system(f"cp -r {base}/voice.mp3 {base}/assets {out}/")
        build(fmt, spec, chars, st, en, have, cover, logo, out)


if __name__ == "__main__":
    main()
