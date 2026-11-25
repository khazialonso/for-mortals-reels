"""Пробы голосов ElevenLabs для персонажей роликов.

Берёт голоса из аккаунта, озвучивает каждым одну и ту же фразу
и складывает mp3 + список голосов в релиз voice-samples.
"""
import csv
import os
import subprocess
import sys
from pathlib import Path

import requests

KEY = os.environ.get("ELEVENLABS_API_KEY", "")
MODEL = os.environ.get("TTS_MODEL", "eleven_multilingual_v2")
LIMIT = int(os.environ.get("VOICE_LIMIT", "12"))
TEXT = ("Привет! Это AI for Mortals: нейросеть теперь сама покупает билеты за две минуты. "
        "А в Biz for Mortals: кофейня подняла выручку на сорок процентов без рекламы.")
API = "https://api.elevenlabs.io"
OUT = Path("voice_out")


def main():
    if not KEY:
        sys.exit("нет ELEVENLABS_API_KEY")
    h = {"xi-api-key": KEY}
    r = requests.get(f"{API}/v1/voices", headers=h, timeout=60)
    r.raise_for_status()
    voices = r.json().get("voices", [])[:LIMIT]
    print("голосов:", len(voices))
    OUT.mkdir(exist_ok=True)
    rows = []
    for i, v in enumerate(voices, 1):
        name = v.get("name", "voice").split(" ")[0]
        labels = v.get("labels") or {}
        fn = f"{i:02d}_{name}.mp3"
        tr = requests.post(f"{API}/v1/text-to-speech/{v['voice_id']}", headers=h,
                           json={"text": TEXT, "model_id": MODEL}, timeout=120)
        if tr.status_code != 200:
            print("ошибка", name, tr.status_code, tr.text[:200])
            continue
        (OUT / fn).write_bytes(tr.content)
        rows.append([i, v.get("name", ""), v["voice_id"], labels.get("gender", ""),
                     labels.get("age", ""), labels.get("accent", ""), labels.get("description", "")])
        print("ok", fn)
    with open(OUT / "voices.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["№", "имя", "voice_id", "пол", "возраст", "акцент", "описание"])
        w.writerows(rows)
    subprocess.run(["gh", "release", "delete", "voice-samples", "-y", "--cleanup-tag"], check=False)
    subprocess.run(["gh", "release", "create", "voice-samples", *map(str, sorted(OUT.iterdir())),
                    "--title", "Пробы голосов", "--notes", f"Модель {MODEL}. Номер файла = № в voices.csv"],
                   check=True)


if __name__ == "__main__":
    main()
