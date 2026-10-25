import json, re, sys, os

D = sys.argv[1]
ads = json.load(open(os.path.join(D, "ads.json")))

# rough laptop-GPU tiers (higher = faster); >=3.5 holds 90+ fps in CS2 at 1080p low with a decent CPU
GPU = [
    (r"rtx\s?-?50\s?90", 9.5, "RTX 5090"), (r"rtx\s?-?50\s?80", 9, "RTX 5080"), (r"rtx\s?-?50\s?70\s?ti", 8.3, "RTX 5070 Ti"),
    (r"rtx\s?-?50\s?70", 7.5, "RTX 5070"), (r"rtx\s?-?50\s?60", 6.5, "RTX 5060"), (r"rtx\s?-?50\s?50", 5.5, "RTX 5050"),
    (r"rtx\s?-?40\s?90", 9.3, "RTX 4090"), (r"rtx\s?-?40\s?80", 8.5, "RTX 4080"), (r"rtx\s?-?40\s?70", 6.8, "RTX 4070"),
    (r"rtx\s?-?40\s?60", 6, "RTX 4060"), (r"rtx\s?-?40\s?50", 5, "RTX 4050"),
    (r"rtx\s?-?30\s?80\s?ti", 8, "RTX 3080 Ti"), (r"rtx\s?-?30\s?80", 7.5, "RTX 3080"), (r"rtx\s?-?30\s?70\s?ti", 7, "RTX 3070 Ti"),
    (r"rtx\s?-?30\s?70", 6.5, "RTX 3070"), (r"rtx\s?-?30\s?60", 5.5, "RTX 3060"), (r"rtx\s?-?30\s?50\s?ti", 4, "RTX 3050 Ti"),
    (r"rtx\s?-?30\s?50", 3.5, "RTX 3050"), (r"rtx\s?-?20\s?80", 6, "RTX 2080"), (r"rtx\s?-?20\s?70", 5, "RTX 2070"),
    (r"rtx\s?-?20\s?60", 4, "RTX 2060"), (r"rtx\s?-?20\s?50", 2.5, "RTX 2050"),
    (r"gtx\s?-?10\s?80", 5, "GTX 1080"), (r"gtx\s?-?10\s?70", 4, "GTX 1070"), (r"gtx\s?-?16\s?60\s?ti", 3.5, "GTX 1660 Ti"),
    (r"gtx\s?-?16\s?60", 3.3, "GTX 1660"), (r"gtx\s?-?16\s?50\s?ti", 2.5, "GTX 1650 Ti"), (r"gtx\s?-?16\s?50", 2.2, "GTX 1650"),
    (r"gtx\s?-?10\s?60", 3, "GTX 1060"), (r"gtx\s?-?10\s?50", 1, "GTX 1050"), (r"gtx\s?-?9[6-8]0m?", 0.8, "GTX 9xx"),
    (r"rx\s?-?7600s", 6, "RX 7600S"), (r"rx\s?-?6[78]00[ms]", 6.5, "RX 6700M/6800M"), (r"rx\s?-?6[56]50m", 5.7, "RX 6650M"),
    (r"rx\s?-?6600m", 5.5, "RX 6600M"), (r"rx\s?-?6500m", 3, "RX 6500M"), (r"rx\s?-?5600m", 4, "RX 5600M"),
    (r"rx\s?-?5500m", 3, "RX 5500M"), (r"\bmx\s?\d{3}", 0.5, "MX"),
]
CPU = [
    ('ultra\\s?[579]\\s?2\\d{2}[hvx]?', 5.5, 'Core Ultra 200'),
    ('ultra\\s?[579]\\s?1\\d{2}h', 5, 'Core Ultra 1xxH'),
    ('ultra\\s?[579]\\s?1\\d{2}u?', 4, 'Core Ultra 1xxU'),
    ('i[3579]\\s?-?\\s?14\\d{3}hx?', 5.5, 'Intel 14th H'),
    ('i[3579]\\s?-?\\s?13\\d{3}hx?', 5, 'Intel 13th H'),
    ('i[3579]\\s?-?\\s?12\\d{3}hx?', 4.5, 'Intel 12th H'),
    ('i[3579]\\s?-?\\s?11\\d{3}h', 3.5, 'Intel 11th H'),
    ('i[3579]\\s?-?\\s?10\\d{3}h', 2.5, 'Intel 10th H'),
    ('i[3579]\\s?-?\\s?9\\d{3}h', 2, 'Intel 9th H'),
    ('i[3579]\\s?-?\\s?8\\d{3}h', 1.5, 'Intel 8th H'),
    ('i[3579]\\s?-?\\s?1[23]\\d{2}[up]', 3, 'Intel 12/13th U/P'),
    ('i[3579]\\s?-?\\s?11\\d{2}g\\d', 2.5, 'Intel 11th U'),
    ('i[3579]\\s?-?\\s?10\\d{2,3}u', 1.5, 'Intel 10th U'),
    ('i[3579]\\s?-?\\s?[78]\\d{3}u', 1, 'Intel 7/8th U'),
    ('ryzen\\s?(ai)?\\s?[579]?\\s?(hx\\s?)?3[67]\\d\\b', 6, 'Ryzen AI 300'),
    ('\\b(8[4-9]\\d{2}hs?)\\b', 5, 'Ryzen 8000'),
    ('\\b(7[4-9][4-5]\\dhs|7[4-9][4-5]\\dh|7945hx|7845hx)\\b', 5, 'Ryzen 7040/7045'),
    ('\\b(7[3-7]35hs?|7[3-7]35h)\\b', 4, 'Ryzen 7x35'),
    ('\\b(6[6-9]00hs?|6[6-9]00h)\\b', 4, 'Ryzen 6000H'),
    ('\\b(5[6-9]00hs?|5[6-9]00hx|5[6-9]00h)\\b', 3.5, 'Ryzen 5000H'),
    ('\\b(4[6-9]00hs?|4[6-9]00h)\\b', 2.7, 'Ryzen 4000H'),
    ('\\b(3[5-7]50h)\\b', 1.3, 'Ryzen 3000H'),
    ('\\b(5[5-9]00u|5[5-8]25u|7[5-7]30u)\\b', 2, 'Ryzen U'),
    ('\\b(7[3-8]40u|8[6-8]40u)\\b', 3, 'Ryzen 7040U'),
    ('\\bm4\\s?(pro|max)\\b', 9, 'Apple M4 Pro/Max'),
    ('\\bm4\\b', 8, 'Apple M4'),
    ('\\bm3\\s?(pro|max)\\b', 8, 'Apple M3 Pro/Max'),
    ('\\bm3\\b', 7, 'Apple M3'),
    ('\\bm2\\s?(pro|max)\\b', 7, 'Apple M2 Pro/Max'),
    ('\\bm2\\b', 6, 'Apple M2'),
    ('\\bm1\\s?(pro|max)\\b', 6, 'Apple M1 Pro/Max'),
    ('\\bm1\\b', 5, 'Apple M1'),
    ('snapdragon\\s?x', 5, 'Snapdragon X'),
]
BAD = r"defekt|bastler|ersatzteil|für teile|fuer teile|kaputt|gebrochen|bootet nicht|startet nicht|ohne festplatte|ohne ssd|mainboard defekt|wasserschaden|display riss|\bsuche\b|\bkaufe\b|tausche nur|gesperrt|icloud|bios passwort|bios-passwort"
DESKTOP = r"\b(tower|gaming[- ]?pc|desktop|komplett[- ]?pc|pc[- ]?system|midi|aio)\b"
LAPTOP = r"laptop|notebook|macbook|thinkpad|ultrabook|legion|nitro|tuf|rog|victus|omen|zenbook|yoga|xps"


def first(table, t):
    for rx, score, name in table:
        if re.search(rx, t):
            return score, name
    return None, None


def ram(t):
    best = None
    for m in re.finditer(r"(\d{1,2})\s?gb\s?(?:ddr\d\s?)?(?:ram|arbeitsspeicher|ddr|memory|unified)|(?:ram|arbeitsspeicher)\s?:?\s?(\d{1,2})\s?gb", t):
        v = int(m.group(1) or m.group(2))
        if v in (4, 8, 12, 16, 18, 24, 32, 36, 48, 64):
            best = max(best or 0, v)
    return best


def hz(t):
    m = re.search(r"(1[2-9]\d|2[0-4]\d|300|360)\s?hz", t)
    return int(m.group(1)) if m else None


out = []
for a in ads:
    t = (a["title"] + " " + a["body"]).lower().replace("–", "-")
    try:
        price = float(a["price"])
    except ValueError:
        continue
    gs, gn = first(GPU, t)
    cs, cn = first(CPU, t)
    a.update(price=price, gpu=gn, gpu_s=gs, cpu=cn, cpu_s=cs, ram=ram(t), hz=hz(t),
             bad=bool(re.search(BAD, t)),
             desktop=bool(re.search(DESKTOP, t)) and not re.search(LAPTOP, a["title"].lower()),
             apple="macbook" in t)
    if gs is not None and gs >= 3.5 and (cs is None or cs >= 2.7):
        a["esports"] = "yes" if cs is not None else "likely (cpu?)"
    elif gs is not None and gs >= 2.2 and (cs is None or cs >= 2):
        a["esports"] = "marginal"
    else:
        a["esports"] = "no/unknown"
    out.append(a)

json.dump(out, open(os.path.join(D, "parsed.json"), "w"), ensure_ascii=False, indent=1)
ok = [a for a in out if not a["bad"] and not a["desktop"]]
print("total", len(out), "clean", len(ok), "bad", sum(a["bad"] for a in out), "desktop", sum(a["desktop"] for a in out))
from collections import Counter
print(Counter(a["esports"] for a in ok))
print(Counter(a["gpu"] for a in ok).most_common(30))
print(Counter(a["state"] for a in ok).most_common())
