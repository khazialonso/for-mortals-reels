"""Пилот новой сборки: ElevenLabs (голос + тайминги) -> HTML-композиция HyperFrames."""
import base64
import json
import os
import re
import sys
from pathlib import Path

import requests

KEY = os.environ.get("ELEVENLABS_API_KEY", "")
VOICE = os.environ.get("VOICE_ID", "kwajW3Xh5svCeKU5ky2S")  # Dmitry, AI for Mortals
MODEL = os.environ.get("TTS_MODEL", "eleven_multilingual_v2")
OUT = Path(os.environ.get("OUT_DIR", "reel"))
W, H = 1080, 1920
BLUE, INK, GREY = "#4074FF", "#111111", "#9A9A9A"

# тестовый сценарий (в проде его пишет агент REELS)
SCENES = [
    {"kind": "hook", "text": "Браузерные агенты теперь сами покупают билеты.",
     "lines": ["Браузер-агент", "сам покупает", "билеты"], "mark": 1},
    {"kind": "number", "text": "Рутины в браузере станет меньше на восемьдесят процентов.",
     "big": "−80%", "caption": "рутины в браузере"},
    {"kind": "list", "text": "Он ищет дешёвые рейсы, заполняет анкеты и сравнивает цены.",
     "title": ["3 вещи, которые", "он умеет уже сейчас"],
     "items": [("ищет", "ищет дешёвые рейсы"), ("заполняет", "заполняет анкеты"), ("сравнивает", "сравнивает цены")]},
    {"kind": "final", "text": "Сохрани, чтобы не потерять!", "lines": ["Сохрани,", "чтобы не потерять"]},
]

VOWEL_OPEN = set("аоуыэяёю")
VOWEL_MID = set("еи")
CLOSED = set("мбп")


def tts(text):
    r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}/with-timestamps",
                      headers={"xi-api-key": KEY},
                      json={"text": text, "model_id": MODEL,
                            "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.3}},
                      timeout=180)
    r.raise_for_status()
    d = r.json()
    (OUT / "voice.mp3").write_bytes(base64.b64decode(d["audio_base64"]))
    a = d.get("alignment") or d.get("normalized_alignment")
    return a["characters"], a["character_start_times_seconds"], a["character_end_times_seconds"]


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


def mouth_track(chars, st):
    out, last = [], None
    for c, s in zip(chars, st):
        lc = c.lower()
        if lc in VOWEL_OPEN:
            m = "open"
        elif lc in VOWEL_MID:
            m = "mid"
        elif lc in CLOSED or not lc.isalpha():
            m = "closed"
        else:
            m = "mid"
        if m != last:
            out.append((round(s, 3), m))
            last = m
    return out


CHAR_SVG = """
<svg viewBox="0 0 360 450" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
<defs><clipPath id="mclip"><path d="M140 252 Q180 304 220 252 Q180 262 140 252 Z"/></clipPath></defs>
<path d="M158 330 Q148 378 120 392" stroke="#3366EE" stroke-width="18" fill="none" stroke-linecap="round"/>
<ellipse cx="110" cy="397" rx="24" ry="13" fill="#2F5FD9"/>
<path d="M205 335 Q212 378 232 398" stroke="#3366EE" stroke-width="18" fill="none" stroke-linecap="round"/>
<ellipse cx="244" cy="404" rx="24" ry="13" fill="#2F5FD9"/>
<path d="M258 226 Q302 246 292 290 Q284 314 262 304" stroke="#3366EE" stroke-width="16" fill="none" stroke-linecap="round"/>
<g id="arm">
<path d="M114 252 Q70 244 66 196" stroke="#3366EE" stroke-width="18" fill="none" stroke-linecap="round"/>
<g stroke="#3366EE" stroke-width="11" stroke-linecap="round"><line x1="54" y1="176" x2="44" y2="156"/><line x1="62" y1="170" x2="58" y2="146"/><line x1="72" y1="170" x2="76" y2="148"/><line x1="80" y1="180" x2="92" y2="166"/></g>
<circle cx="65" cy="184" r="16" fill="#3366EE"/>
</g>
<g transform="rotate(10 180 240)">
<rect x="130" y="66" width="100" height="84" rx="4" fill="#D9DDE4"/>
<rect x="212" y="66" width="18" height="84" fill="#B4BAC5"/>
<rect x="150" y="88" width="20" height="18" rx="2" fill="#3A3F4A"/><rect x="190" y="88" width="20" height="18" rx="2" fill="#3A3F4A"/>
<rect x="105" y="140" width="150" height="200" rx="40" fill="#4074FF"/>
<path d="M232 146 Q255 150 255 180 L255 300 Q255 336 222 340 Q244 320 244 290 L244 180 Q244 160 232 146 Z" fill="#2F5FD9"/>
<rect x="118" y="156" width="18" height="76" rx="9" fill="#6E9BFF"/>
<g id="brows"><path d="M135 190 Q150 178 166 187" stroke="#10183A" stroke-width="7" fill="none" stroke-linecap="round"/>
<path d="M194 187 Q210 178 225 190" stroke="#10183A" stroke-width="7" fill="none" stroke-linecap="round"/></g>
<g id="eyes"><ellipse cx="150" cy="217" rx="18" ry="21" fill="#F7F9FF"/><ellipse cx="210" cy="217" rx="18" ry="21" fill="#F7F9FF"/>
<circle cx="154" cy="220" r="10" fill="#10183A"/><circle cx="206" cy="220" r="10" fill="#10183A"/>
<circle cx="157" cy="215" r="3.5" fill="#fff"/><circle cx="209" cy="215" r="3.5" fill="#fff"/></g>
<g id="m-open" opacity="0"><path d="M140 252 Q180 304 220 252 Q180 262 140 252 Z" fill="#1B2554"/>
<path d="M152 255 Q180 263 208 255 L205 264 Q180 271 155 264 Z" fill="#FFFFFF"/>
<ellipse cx="182" cy="276" rx="18" ry="9" fill="#F28FA8" clip-path="url(#mclip)"/></g>
<g id="m-mid" opacity="0"><path d="M150 256 Q180 284 210 256 Q180 264 150 256 Z" fill="#1B2554"/>
<path d="M158 258 Q180 263 202 258 L200 263 Q180 267 160 263 Z" fill="#FFFFFF"/></g>
<g id="m-closed"><path d="M150 258 Q180 276 210 258" stroke="#10183A" stroke-width="6" fill="none" stroke-linecap="round"/></g>
</g>
</svg>"""


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;")


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    full = " ".join(s["text"] for s in SCENES)
    chars, st, en = tts(full)
    words = words_from(chars, st, en)
    total = round(en[-1] + 0.8, 2)
    # границы сцен по словам
    idx, starts = 0, []
    for s in SCENES:
        starts.append(words[idx]["s"] if idx < len(words) else total)
        idx += len(s["text"].split())
    starts[0] = 0.0
    ends = starts[1:] + [total]

    html_sc, js = [], []
    for i, (s, a, b) in enumerate(zip(SCENES, starts, ends)):
        sid = f"s{i}"
        dur = round(b - a, 3)
        inner = ""
        if s["kind"] in ("hook", "final"):
            center = s["kind"] == "final"
            for j, ln in enumerate(s["lines"]):
                mark = s.get("mark") == j
                inner += (f'<div class="ln{" c" if center else ""}" id="{sid}l{j}">{esc(ln)}'
                          + (f'<span class="bar" id="{sid}bar"></span>' if mark else "") + "</div>")
                js.append(f'tl.from("#{sid}l{j}",{{opacity:0,y:60,duration:0.35,ease:"power3.out"}},{a + 0.12 * j:.3f});')
            if "mark" in s:
                js.append(f'tl.from("#{sid}bar",{{scaleX:0,transformOrigin:"0 50%",duration:0.4,ease:"power2.out"}},{a + 0.5:.3f});')
            if center:
                inner += '<div class="handle">@ai_for_mortals</div>'
        elif s["kind"] == "number":
            inner += f'<div class="big" id="{sid}big">{esc(s["big"])}</div><div class="cap" id="{sid}cap">{esc(s["caption"])}</div>'
            js.append(f'tl.from("#{sid}big",{{scale:0.6,opacity:0,duration:0.45,ease:"back.out(2)"}},{a + 0.05:.3f});')
            js.append(f'tl.from("#{sid}cap",{{opacity:0,y:30,duration:0.3}},{a + 0.35:.3f});')
        elif s["kind"] == "list":
            inner += "".join(f'<div class="ln sm" id="{sid}t{j}">{esc(t)}</div>' for j, t in enumerate(s["title"]))
            js.append(f'tl.from("#{sid}t0, #{sid}t1",{{opacity:0,y:40,duration:0.3,stagger:0.1}},{a:.3f});')
            # слово-якорь каждого пункта ищем в словах сцены
            sw = [w for w in words if a <= w["s"] < b]
            for j, (anchor, label) in enumerate(s["items"]):
                t = next((w["s"] for w in sw if w["w"].lower().startswith(anchor)), a + 0.6 * (j + 1))
                inner += f'<div class="item" id="{sid}i{j}"><span class="num">{j + 1}</span>{esc(label)}</div>'
                js.append(f'tl.from("#{sid}i{j}",{{opacity:0,x:-80,duration:0.35,ease:"power3.out"}},{t - 0.05:.3f});')
        html_sc.append(f'<div class="scene clip" id="{sid}" data-start="{a:.3f}" data-duration="{dur}" data-track-index="1">{inner}</div>')
        # сегменты прогресса
        js.append(f'tl.fromTo("#pg{i} i",{{scaleX:0}},{{scaleX:1,transformOrigin:"0 50%",duration:{dur},ease:"none"}},{a:.3f});')

    # субтитры: куски по 3 слова, активное слово подчёркнуто
    subs, k = [], 0
    chunks = [words[i:i + 3] for i in range(0, len(words), 3)]
    for ci, ch in enumerate(chunks):
        a = ch[0]["s"]
        b = chunks[ci + 1][0]["s"] if ci + 1 < len(chunks) else total
        spans = ""
        for w in ch:
            wid = f"w{k}"
            k += 1
            spans += f'<span class="w" id="{wid}">{esc(w["w"])}<i></i></span> '
            js.append(f'tl.set("#{wid}",{{color:"{INK}"}},{w["s"]:.3f});')
            js.append(f'tl.fromTo("#{wid} i",{{scaleX:0}},{{scaleX:1,duration:0.12}},{w["s"]:.3f});')
            js.append(f'tl.set("#{wid} i",{{scaleX:0}},{max(w["e"] + 0.02, w["s"] + 0.14):.3f});')
        subs.append(f'<div class="sub clip" data-start="{a:.3f}" data-duration="{round(b - a, 3)}" data-track-index="3">{spans}</div>')

    # персонаж: рот, моргание, взмахи, покачивание, переезды между сценами
    for t, m in mouth_track(chars, st):
        js.append(f'tl.set("#m-open",{{opacity:{1 if m == "open" else 0}}},{t});'
                  f'tl.set("#m-mid",{{opacity:{1 if m == "mid" else 0}}},{t});'
                  f'tl.set("#m-closed",{{opacity:{1 if m == "closed" else 0}}},{t});')
    js.append(f'tl.set("#m-open, #m-mid",{{opacity:0}},{en[-1] + 0.05:.3f});tl.set("#m-closed",{{opacity:1}},{en[-1] + 0.05:.3f});')
    t = 1.6
    while t < total - 0.3:
        js.append(f'tl.to("#eyes",{{scaleY:0.1,svgOrigin:"180 217",duration:0.06}},{t:.2f});'
                  f'tl.to("#eyes",{{scaleY:1,svgOrigin:"180 217",duration:0.08}},{t + 0.08:.2f});')
        t += 3.1
    js.append(f'tl.to("#bob",{{y:-14,duration:0.45,ease:"sine.inOut",yoyo:true,repeat:{int(total / 0.45)}}},0);')
    for a in (0.2, starts[-1] + 0.1):
        js.append(f'tl.to("#arm",{{rotation:-16,svgOrigin:"114 252",duration:0.22,ease:"sine.inOut",yoyo:true,repeat:5}},{a:.3f});')
    # сцена 1 — крупно по центру, дальше в угол
    js.append('tl.set("#char",{x:300,y:-260,scale:1.25},0);')
    js.append(f'tl.to("#char",{{x:0,y:0,scale:1,duration:0.5,ease:"power3.inOut"}},{starts[1] - 0.2:.3f});')
    js.append(f'tl.to("#char",{{x:280,y:-300,scale:1.2,duration:0.5,ease:"power3.inOut"}},{starts[-1] - 0.1:.3f});')
    js.append(f'tl.from("#brows",{{y:-8,duration:0.2,yoyo:true,repeat:1}},{starts[1]:.3f});')

    seg = "".join(f'<div class="seg" id="pg{i}"><i></i></div>' for i in range(len(SCENES)))
    html = f"""<!doctype html>
<html lang="ru" data-resolution="portrait">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={W}, height={H}" />
<script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
html, body {{ width:{W}px; height:{H}px; overflow:hidden; background:#fff; }}
#root {{ position:relative; width:{W}px; height:{H}px; font-family:'Inter', sans-serif; color:{INK}; }}
.top {{ position:absolute; left:60px; right:60px; top:70px; display:flex; justify-content:space-between; font-weight:800; font-size:40px; }}
.top .n {{ color:{GREY}; font-weight:600; }}
.segs {{ position:absolute; left:60px; right:60px; top:150px; display:flex; gap:14px; }}
.seg {{ flex:1; height:10px; border-radius:5px; background:#E8ECF5; overflow:hidden; }}
.seg i {{ display:block; height:100%; background:{BLUE}; transform:scaleX(0); transform-origin:0 50%; }}
.scene {{ position:absolute; left:60px; right:60px; top:240px; }}
.ln {{ font-weight:900; font-size:118px; line-height:1.08; letter-spacing:-3px; position:relative; }}
.ln.sm {{ font-size:78px; letter-spacing:-2px; }}
.ln.c {{ text-align:center; }}
.bar {{ position:absolute; left:0; bottom:-6px; width:88%; height:22px; background:{BLUE}; }}
.big {{ font-weight:900; font-size:330px; color:{BLUE}; letter-spacing:-12px; margin-top:120px; }}
.cap {{ font-size:56px; color:#666; margin-top:10px; }}
.item {{ display:flex; align-items:center; gap:34px; background:#F2F5FC; border-radius:42px; padding:38px 40px; margin-top:34px; font-size:58px; font-weight:600; }}
.item:first-of-type {{ margin-top:80px; }}
.num {{ width:92px; height:92px; border-radius:46px; background:{BLUE}; color:#fff; display:flex; align-items:center; justify-content:center; font-weight:800; }}
.handle {{ text-align:center; font-size:52px; color:{BLUE}; font-weight:700; margin-top:40px; }}
.sub {{ position:absolute; left:500px; right:50px; top:1330px; font-weight:800; font-size:66px; line-height:1.25; }}
.w {{ color:#C4C4C4; position:relative; display:inline-block; }}
.w i {{ position:absolute; left:0; right:0; bottom:-4px; height:12px; background:{BLUE}; transform:scaleX(0); transform-origin:0 50%; }}
#char {{ position:absolute; left:-120px; top:1110px; width:760px; height:950px; transform-origin:50% 100%; }}
#bob {{ width:100%; height:100%; }}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{total}" data-width="{W}" data-height="{H}">
<div class="top clip" data-start="0" data-duration="{total}" data-track-index="0"><span>AI for Mortals</span><span class="n">пилот</span></div>
<div class="segs clip" data-start="0" data-duration="{total}" data-track-index="0">{seg}</div>
{''.join(html_sc)}
{''.join(subs)}
<div id="char" class="clip" data-start="0" data-duration="{total}" data-track-index="4"><div id="bob">{CHAR_SVG}</div></div>
<audio id="voice" data-start="0" data-duration="{total}" data-track-index="5" data-volume="1" src="voice.mp3"></audio>
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
    (OUT / "index.html").write_text(html, encoding="utf-8")
    (OUT / "words.json").write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    print("готово:", total, "c, сцены:", [round(x, 2) for x in starts])


if __name__ == "__main__":
    if not KEY:
        sys.exit("нет ELEVENLABS_API_KEY")
    build()
