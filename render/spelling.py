"""Субтитры: названия и аббревиатуры латиницей, хотя голос читает их кириллицей.

Два источника: словарь частых названий (ниже) и строка «написание | звучит=пишется; ...»
в ячейке «Сцены», которую пишет агент REELS для новых и редких названий.
"""
import re

ENDINGS = "(|а|у|ом|е|ы|ов|ам|ами|ах|ой|ю|я|и)"
COMMON = {
    "чат джи-пи-ти": "ChatGPT", "джи-пи-ти": "GPT", "опен-эй-ай": "OpenAI", "опенэйай": "OpenAI",
    "клод": "Claude", "антропик": "Anthropic", "джемини": "Gemini", "гугл": "Google",
    "майкрософт": "Microsoft", "эппл": "Apple", "эпл": "Apple", "миджорни": "Midjourney",
    "перплексити": "Perplexity", "копайлот": "Copilot", "дипсик": "DeepSeek", "грок": "Grok",
    "мистраль": "Mistral", "нотион": "Notion", "ноушн": "Notion", "фигма": "Figma", "канва": "Canva",
    "гитхаб": "GitHub", "хаггинг фейс": "Hugging Face", "слак": "Slack", "шопифай": "Shopify",
    "страйп": "Stripe", "эксель": "Excel", "ютуб": "YouTube", "инстаграм": "Instagram",
    "тикток": "TikTok", "телеграм": "Telegram", "амазон": "Amazon", "нвидиа": "NVIDIA",
    "эн-вид-иа": "NVIDIA", "тесла": "Tesla", "эй-пи-ай": "API", "ай-ти": "IT", "эс-эм-эм": "SMM",
    "си-ар-эм": "CRM", "эс-и-о": "SEO", "ви-пи-эн": "VPN", "пи-ди-эф": "PDF", "эс-ди-кей": "SDK",
    "эм-си-пи": "MCP", "ю-ай": "UI", "ю-икс": "UX", "би-ту-би": "B2B", "би-ту-си": "B2C",
    "ар-оу-ай": "ROI", "кей-пи-ай": "KPI", "эм-ви-пи": "MVP", "эс-эй-эй-эс": "SaaS", "сааc": "SaaS",
}
VERSION = {"один": "1", "два": "2", "три": "3", "четыре": "4", "пять": "5", "шесть": "6", "семь": "7",
           "восемь": "8", "девять": "9", "десять": "10", "о": "o"}


def norm(w):
    return re.sub(r"[^а-яa-z0-9\-]", "", w.lower().replace("ё", "е"))


def parse_line(line):
    """«написание | Джанктс=Juncts; чат джи-пи-ти=ChatGPT» -> {звучит: пишется}."""
    body = line.split("|", 1)[1] if "|" in line else ""
    res = {}
    for pair in re.split(r"[;\n]", body):
        if "=" in pair:
            k, v = pair.split("=", 1)
            if norm(k.strip()) and v.strip():
                res[k.strip().lower().replace("ё", "е")] = v.strip()
    return res


def _match(words, i, key):
    parts = key.split()
    if i + len(parts) > len(words):
        return False
    for j, p in enumerate(parts):
        w = norm(words[i + j]["w"])
        last = j == len(parts) - 1
        pat = re.escape(norm(p)) + (ENDINGS if last and "-" not in p else "")
        if not re.fullmatch(pat, w):
            return False
    return True


def apply(words, extra=None):
    """words: [{'w','s','e'}] -> токены, где названия заменены латиницей."""
    table = {**COMMON, **(extra or {})}
    keys = sorted(table, key=lambda k: -len(k.split()))  # сначала длинные фразы
    out, i = [], 0
    while i < len(words):
        hit = next((k for k in keys if _match(words, i, k)), None)
        if not hit:
            out.append(dict(words[i]))
            i += 1
            continue
        n = len(hit.split())
        run = words[i:i + n]
        text = table[hit]
        last = run[-1]
        # версия: «джи-пи-ти пять» -> GPT-5 (если агент не дал готовое написание)
        tail = re.sub(r"^.*?([.,!?:;»\"]*)$", r"\1", last["w"])
        if not tail and i + n < len(words) and norm(words[i + n]["w"]) in VERSION and text in ("GPT", "Gemini", "Claude", "Grok"):
            v = words[i + n]
            text = f"{text}{'-' if text == 'GPT' else ' '}{VERSION[norm(v['w'])]}"
            last = v
            n += 1
            tail = re.sub(r"^.*?([.,!?:;»\"]*)$", r"\1", v["w"])
        out.append({"w": text + tail, "s": run[0]["s"], "e": last["e"], "latin": True})
        i += n
    return out
