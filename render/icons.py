"""Справочник 3D-иконок Microsoft Fluent Emoji (лицензия MIT).

Ключ — то, что агент REELS пишет в поле «визуал». Файлы лежат в render/icons/<ключ>.png,
их скачивает workflow vendor-icons (один раз).
"""
FOLDERS = [
    # ИИ и техника
    "Robot", "Laptop", "Desktop computer", "Mobile phone", "Keyboard", "Computer mouse", "Light bulb", "Gear",
    "Rocket", "Sparkles", "Magic wand", "Brain", "Magnifying glass tilted left", "Speech balloon",
    "Thought balloon", "Globe with meridians", "Link", "Locked", "Unlocked", "Key", "Shield", "Warning",
    "Check mark button", "Cross mark", "Hourglass done", "Alarm clock", "Stopwatch", "Spiral calendar",
    "Camera with flash", "Clapper board", "Microphone", "Headphone", "Artist palette", "Framed picture",
    "Memo", "Page facing up", "File folder", "Clipboard", "Pushpin", "Puzzle piece", "Hammer and wrench",
    "Toolbox", "Electric plug", "Battery", "Satellite antenna", "Envelope", "Bell", "Megaphone", "Bookmark",
    "Books", "Graduation cap", "Eyes", "Exploding head", "Face with monocle", "Thinking face",
    # деньги и бизнес
    "Bar chart", "Chart increasing", "Chart decreasing", "Money bag", "Dollar banknote", "Coin", "Credit card",
    "Money with wings", "Shopping cart", "Shopping bags", "Package", "Delivery truck", "Department store",
    "Office building", "Briefcase", "Handshake", "Bust in silhouette", "Busts in silhouette", "Thumbs up",
    "Clapping hands", "Flexed biceps", "Fire", "High voltage", "Glowing star", "Trophy", "1st place medal",
    "Bullseye", "Hundred points", "Red question mark", "Red exclamation mark", "Party popper", "Gem stone",
    "Crown", "Hot beverage", "Stop sign", "Prohibited", "Receipt", "Abacus", "Calendar", "Balance scale",
]


def key(folder):
    return folder.lower().replace(" ", "_").replace("-", "_")


if __name__ == "__main__":
    import sys
    from pathlib import Path
    from urllib.parse import quote

    import requests

    base = "https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/assets/"
    out = Path(__file__).with_name("icons")
    out.mkdir(exist_ok=True)
    miss = []
    for f in FOLDERS:
        k = key(f)
        if (out / f"{k}.png").exists():
            continue
        urls = [f"{base}{quote(f)}/3D/{k}_3d.png", f"{base}{quote(f)}/Default/3D/{k}_3d_default.png"]
        for u in urls:
            r = requests.get(u, timeout=30)
            if r.status_code == 200:
                (out / f"{k}.png").write_bytes(r.content)
                break
        else:
            miss.append(f)
    print("нет:", miss)
    sys.exit(0)
