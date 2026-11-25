"""Пробы русских голосов из библиотеки ElevenLabs (shared voices).

Ищет русскоязычные голоса по типажу персонажа, озвучивает нашу фразу.
Если библиотечный голос нельзя озвучить без добавления в аккаунт,
берёт его официальное превью. Всё складывает в релиз voice-library.
"""
import csv
import os
import subprocess
import sys
from pathlib import Path

import requests

KEY = os.environ.get("ELEVENLABS_API_KEY", "")
MODEL = os.environ.get("TTS_MODEL", "eleven_multilingual_v2")
PER = int(os.environ.get("PER_GROUP", "6"))
API = "https://api.elevenlabs.io"
OUT = Path("voice_out")
GROUPS = [
    ("flash", {"gender": "male", "age": "young"},
     "Привет! Это AI for Mortals: нейросеть теперь сама покупает билеты за две минуты. Сейчас покажу, как это работает."),
    ("calc", {"gender": "male", "age": "middle_aged"},
     "Это Biz for Mortals. Кофейня подняла выручку на сорок процентов без рекламы. Разбираем, за счёт чего."),
]


def search(h, flt):
    base = {"page_size": 40, "language": "ru", **flt}
    for extra in ({"sort": "cloned_by_count"}, {}):
        r = requests.get(f"{API}/v1/shared-voices", headers=h, params={**base, **extra}, timeout=60)
        if r.status_code == 200:
            vs = r.json().get("voices", [])
            vs.sort(key=lambda v: v.get("cloned_by_count") or 0, reverse=True)
            return vs
        print("shared-voices", r.status_code, r.text[:200])
    return []


def main():
    if not KEY:
        sys.exit("нет ELEVENLABS_API_KEY")
    h = {"xi-api-key": KEY}
    OUT.mkdir(exist_ok=True)
    rows, n = [], 0
    for tag, flt, text in GROUPS:
        got = 0
        for v in search(h, flt):
            if got >= PER:
                break
            vid = v["voice_id"]
            name = (v.get("name") or "voice").split(" ")[0].replace("/", "_")
            n += 1
            fn = f"{tag}_{n:02d}_{name}.mp3"
            how = "наша фраза"
            tr = requests.post(f"{API}/v1/text-to-speech/{vid}", headers=h,
                               json={"text": text, "model_id": MODEL}, timeout=120)
            if tr.status_code == 200:
                (OUT / fn).write_bytes(tr.content)
            elif v.get("preview_url"):
                pr = requests.get(v["preview_url"], timeout=60)
                if pr.status_code != 200:
                    n -= 1
                    continue
                (OUT / fn).write_bytes(pr.content)
                how = f"превью ({tr.status_code})"
            else:
                n -= 1
                continue
            got += 1
            rows.append([n, tag, v.get("name", ""), vid, v.get("public_owner_id", ""), v.get("age", ""),
                         v.get("accent", ""), v.get("cloned_by_count", ""), how,
                         (v.get("description") or "").replace("\n", " ")[:160]])
            print("ok", fn, how)
    with open(OUT / "voices.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["№", "персонаж", "имя", "voice_id", "public_owner_id", "возраст", "акцент",
                    "клонов", "что в файле", "описание"])
        w.writerows(rows)
    subprocess.run(["gh", "release", "delete", "voice-library", "-y", "--cleanup-tag"], check=False)
    subprocess.run(["gh", "release", "create", "voice-library", *map(str, sorted(OUT.iterdir())),
                    "--title", "Русские голоса из библиотеки", "--notes", f"Модель {MODEL}"], check=True)


if __name__ == "__main__":
    main()
