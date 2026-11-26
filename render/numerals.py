"""Субтитры с цифрами: «двадцать восемь тысяч девятьсот тридцать пять рублей» -> «28 935 ₽».

Озвучка пишется словами (так её правильно читает голос), а на экране числа удобнее цифрами.
Работает с падежами и порядковыми («две тысячи двадцать седьмого года» -> «2027 года»).
"""
import re

CARD = {}


def _add(forms, v, kind):
    for f in forms.split():
        CARD[f] = (v, kind)


_add("один одна одно одного одной одному одним одном одну", 1, "u")
_add("два две двух двум двумя", 2, "u")
_add("три трех трем тремя", 3, "u")
_add("четыре четырех четырем четырьмя", 4, "u")
for v, st in [(5, "пят"), (6, "шест"), (7, "сем"), (9, "девят"), (10, "десят")]:
    _add(f"{st}ь {st}и {st}ью", v, "u" if v < 10 else "t")
_add("восемь восьми восемью", 8, "u")
for v, st in [(11, "одиннадцат"), (12, "двенадцат"), (13, "тринадцат"), (14, "четырнадцат"), (15, "пятнадцат"),
              (16, "шестнадцат"), (17, "семнадцат"), (18, "восемнадцат"), (19, "девятнадцат"),
              (20, "двадцат"), (30, "тридцат")]:
    _add(f"{st}ь {st}и {st}ью", v, "t")
_add("сорок сорока", 40, "t")
_add("пятьдесят пятидесяти пятьюдесятью", 50, "t")
_add("шестьдесят шестидесяти шестьюдесятью", 60, "t")
_add("семьдесят семидесяти семьюдесятью", 70, "t")
_add("восемьдесят восьмидесяти восемьюдесятью", 80, "t")
_add("девяносто девяноста", 90, "t")
_add("сто ста", 100, "h")
_add("двести двухсот", 200, "h")
_add("триста трехсот", 300, "h")
_add("четыреста четырехсот", 400, "h")
for v, st in [(500, "пят"), (600, "шест"), (700, "сем"), (900, "девят")]:
    _add(f"{st}ьсот {st}исот", v, "h")
_add("восемьсот восьмисот", 800, "h")
for f in ["тысяча", "тысячи", "тысячу", "тысяч", "тысячей", "тысячам", "тысячами", "тысячах"]:
    CARD[f] = (1000, "m")
for st, v in [("миллион", 10 ** 6), ("миллиард", 10 ** 9)]:
    for e in ["", "а", "у", "ом", "е", "ов", "ам", "ами", "ах"]:
        CARD[st + e] = (v, "m")

ORD_STEMS = [("перв", 1), ("втор", 2), ("трет", 3), ("четверт", 4), ("пят", 5), ("шест", 6), ("седьм", 7),
             ("восьм", 8), ("девят", 9), ("десят", 10), ("одиннадцат", 11), ("двенадцат", 12), ("тринадцат", 13),
             ("четырнадцат", 14), ("пятнадцат", 15), ("шестнадцат", 16), ("семнадцат", 17), ("восемнадцат", 18),
             ("девятнадцат", 19), ("двадцат", 20), ("тридцат", 30), ("сороков", 40), ("пятидесят", 50),
             ("шестидесят", 60), ("семидесят", 70), ("восьмидесят", 80), ("девяност", 90), ("сот", 100),
             ("тысячн", 1000)]
ORD_END = re.compile(r"(ый|ой|ий|ого|его|ому|ему|ым|им|ом|ем|ая|яя|ую|юю|ое|ее|ые|ие|ых|их|ыми|ими|ья|ье|ьего|ьей|ьему|ьим|ьем|ью|ьи|ьих)")
ORD_KIND = {1: "u", 2: "u", 3: "u", 4: "u", 5: "u", 6: "u", 7: "u", 8: "u", 9: "u"}

UNITS = r"(процент\w*|рубл\w*|доллар\w*|евро|год\w*|лет|дн\w*|день|месяц\w*|недел\w*|час\w*|минут\w*|секунд\w*|раз|раза|человек\w*|штук\w*|сотрудник\w*|клиент\w*|заказ\w*|товар\w*|компани\w*|пользовател\w*|январ\w*|феврал\w*|март\w*|апрел\w*|ма[йяе]\w*|июн\w*|июл\w*|август\w*|сентябр\w*|октябр\w*|ноябр\w*|декабр\w*)"
ORDER = {"u": 1, "t": 2, "h": 3}


def norm(w):
    return re.sub(r"[^а-я\-]", "", w.lower().replace("ё", "е"))


def num_of(w):
    """(значение, вид, порядковое) или None."""
    if w in CARD:
        v, k = CARD[w]
        return v, k, False
    for st, v in ORD_STEMS:
        if w.startswith(st) and ORD_END.fullmatch(w[len(st):]):
            if w in ("пятой", "пятом") and False:
                pass
            k = "m" if v == 1000 else ("h" if v >= 100 else ("t" if v >= 10 else "u"))
            return v, k, True
    return None


def fmt(n, year=False):
    for d, name in ((10 ** 9, "млрд"), (10 ** 6, "млн")):
        if n >= d and n % (d // 10) == 0:
            return f"{n / d:g}".replace(".", ",") + " " + name
    s = str(n)
    if n >= 10000 and not year:
        s = f"{n:,}".replace(",", " ")
    return s


def tokens(words):
    """words: [{'w','s','e'}] -> такие же токены, где числа собраны в цифры."""
    out, i = [], 0
    while i < len(words):
        w = words[i]
        raw = w["w"]
        nw = norm(raw)
        # «три-четыре» -> «3–4»
        if "-" in nw:
            parts = nw.split("-")
            vals = [num_of(p) for p in parts]
            if all(vals) and len(parts) == 2:
                tail = re.sub(r"^.*?([^\wа-яА-ЯёЁ\-]*)$", r"\1", raw)
                text, e, step = f"{vals[0][0]}–{vals[1][0]}", w["e"], 1
                nx = words[i + 1] if i + 1 < len(words) else None
                if nx and not tail and norm(nx["w"]).startswith("процент"):
                    text, e, step = text + "%", nx["e"], 2
                    tail = re.sub(r"^.*?([.,!?:;»\"]*)$", r"\1", nx["w"])
                out.append({"w": text + tail, "s": w["s"], "e": e, "num": True})
                i += step
                continue
        if nw in ("полтора", "полторы") and i + 1 < len(words):
            t = num_of(norm(words[i + 1]["w"]))
            if t and t[1] == "m":
                name = {1000: "1,5 тыс.", 10 ** 6: "1,5 млн", 10 ** 9: "1,5 млрд"}[t[0]]
                tail = re.sub(r"^.*?([.,!?:;»\"]*)$", r"\1", words[i + 1]["w"])
                out.append({"w": name + tail, "s": w["s"], "e": words[i + 1]["e"], "num": True})
                i += 2
                continue
        if num_of(nw) is None or norm(raw) != raw.lower().replace("ё", "е").strip(".,!?:;»«\"()"):
            out.append(dict(w))
            i += 1
            continue
        # собираем последовательность числительных
        total, group, last_order, j, ordinal = 0, 0, 9, i, False
        while j < len(words):
            t = num_of(norm(words[j]["w"]))
            if t is None:
                break
            v, k, is_ord = t
            if k == "m":
                group = group or 1
                total += group * v
                group, last_order = 0, 9
            else:
                if ORDER[k] >= last_order:
                    break
                group += v
                last_order = ORDER[k]
            j += 1
            if is_ord:
                ordinal = True
                break
            if re.search(r"[.,!?:;]$", words[j - 1]["w"]):
                break
        value = total + group
        run = words[i:j]
        nxt = norm(words[j]["w"]) if j < len(words) else ""
        unit_ok = bool(re.fullmatch(UNITS, nxt)) and not re.search(r"[.,!?:;]$", run[-1]["w"])
        if len(run) == 1 and not ordinal and value <= 10 and not unit_ok:
            out.append(dict(w))  # «один из», «две компании» оставляем словами
            i += 1
            continue
        if len(run) == 1 and value == 1 and not ordinal:
            out.append(dict(w))
            i += 1
            continue
        tail = re.sub(r"^.*?([.,!?:;»\"]*)$", r"\1", run[-1]["w"])
        year = ordinal or nxt.startswith("год") or (1900 <= value <= 2100)
        text = fmt(value, year)
        e = run[-1]["e"]
        if unit_ok and not tail:
            u = words[j]
            un = norm(u["w"])
            utail = re.sub(r"^.*?([.,!?:;»\"]*)$", r"\1", u["w"])
            if un.startswith("процент"):
                text, e, j, tail = text + "%", u["e"], j + 1, utail
            elif un.startswith("рубл"):
                text, e, j, tail = text + " ₽", u["e"], j + 1, utail
            elif un.startswith("доллар"):
                text, e, j, tail = "$" + text, u["e"], j + 1, utail
        out.append({"w": text + tail, "s": run[0]["s"], "e": e, "num": True})
        i = j
    return out
