"""Profiles: what wh knows about a kind of item, so only a shortlist reaches Claude.

annotate(ads, name) sets `junk` on every ad (a reason, or None) and adds the profile's own fields.
shortlist(ads, name, n) picks the ads worth a closer look. FIELDS[name] are the extra columns to show.
The laptop tables come from the 2026-10-25 laptop hunt (seed/analyze.py, seed/rank.py).
"""
import re

BAD = (r"defekt|bastler|ersatzteil|für teile|fuer teile|kaputt|gebrochen|bootet nicht|startet nicht|wasserschaden"
       r"|display riss|funktioniert nicht|nicht funktions|defect|broken|not working|gesperrt|aktivierungssperre"
       r"|icloud[- ]?(sperre|gesperrt|lock)|\bmdm\b|bios[- ]?passwort")
WANTED = r"^\s*(suche|kaufe|ankauf|wir kaufen)\b"


def text(ad):
    return (ad.get("title", "") + " " + ad.get("body", "") + " " + ad.get("descr", "")).lower().replace("–", "-")


def generic_junk(ad):
    if re.search(WANTED, ad.get("title", "").lower()):
        return "wanted ad"
    if not ad.get("price"):                                    # None, or €0 (giveaway / price on request)
        return "no price"
    m = re.search(BAD, text(ad))
    return "says '%s'" % m.group(0) if m else None


# ---- laptop ---------------------------------------------------------------------------------------------------

# rough laptop-GPU tiers (higher = faster); >= 3.5 holds 90+ fps in CS2 at 1080p low with a decent CPU
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
    (r"ultra\s?[579]\s?2\d{2}[hvx]?", 5.5, "Core Ultra 200"),
    (r"ultra\s?[579]\s?1\d{2}h", 5, "Core Ultra 1xxH"),
    (r"ultra\s?[579]\s?1\d{2}u?", 4, "Core Ultra 1xxU"),
    (r"i[3579]\s?-?\s?14\d{3}hx?", 5.5, "Intel 14th H"),
    (r"i[3579]\s?-?\s?13\d{3}hx?", 5, "Intel 13th H"),
    (r"i[3579]\s?-?\s?12\d{3}hx?", 4.5, "Intel 12th H"),
    (r"i[3579]\s?-?\s?11\d{3}h", 3.5, "Intel 11th H"),
    (r"i[3579]\s?-?\s?10\d{3}h", 2.5, "Intel 10th H"),
    (r"i[3579]\s?-?\s?9\d{3}h", 2, "Intel 9th H"),
    (r"i[3579]\s?-?\s?8\d{3}h", 1.5, "Intel 8th H"),
    (r"i[357]\s?-?\s?[67]\d{3}h[qk]", 1.2, "Intel 6/7th HQ"),
    (r"i[3579]\s?-?\s?1[23]\d{2}[up]", 3, "Intel 12/13th U/P"),
    (r"i[3579]\s?-?\s?11\d{2}g\d", 2.5, "Intel 11th U"),
    (r"i[3579]\s?-?\s?10\d{2,3}u", 1.5, "Intel 10th U"),
    (r"i[3579]\s?-?\s?[78]\d{3}u", 1, "Intel 7/8th U"),
    (r"ryzen\s?(ai)?\s?[579]?\s?(hx\s?)?3[67]\d\b", 6, "Ryzen AI 300"),
    (r"\b(8[4-9]\d{2}hs?)\b", 5, "Ryzen 8000"),
    (r"\b(7[4-9][4-5]\dhs|7[4-9][4-5]\dh|7945hx|7845hx)\b", 5, "Ryzen 7040/7045"),
    (r"\b(7[3-7]35hs?|7[3-7]35h)\b", 4, "Ryzen 7x35"),
    (r"\b(6[6-9]00hs?|6[6-9]00h)\b", 4, "Ryzen 6000H"),
    (r"\b(5[6-9]00hs?|5[6-9]00hx|5[6-9]00h)\b", 3.5, "Ryzen 5000H"),
    (r"\b(4[6-9]00hs?|4[6-9]00h)\b", 2.7, "Ryzen 4000H"),
    (r"\b(3[5-7]50h)\b", 1.3, "Ryzen 3000H"),
    (r"\b(5[5-9]00u|5[5-8]25u|7[5-7]30u)\b", 2, "Ryzen U"),
    (r"\b(7[3-8]40u|8[6-8]40u)\b", 3, "Ryzen 7040U"),
    (r"\bm4\s?(pro|max)\b", 9, "Apple M4 Pro/Max"),
    (r"\bm4\b", 8, "Apple M4"),
    (r"\bm3\s?(pro|max)\b", 8, "Apple M3 Pro/Max"),
    (r"\bm3\b", 7, "Apple M3"),
    (r"\bm2\s?(pro|max)\b", 7, "Apple M2 Pro/Max"),
    (r"\bm2\b", 6, "Apple M2"),
    (r"\bm1\s?(pro|max)\b", 6, "Apple M1 Pro/Max"),
    (r"\bm1\b", 5, "Apple M1"),
    (r"snapdragon\s?x", 5, "Snapdragon X"),
]
PART = (r"^(neue?r?s? )?(kühlung|kühler|lüfter|akku|tastatur|display|bildschirm|netzteil|ladegerät|mainboard|motherboard"
        r"|gehäuse|scharnier|ram|ssd|grafikkarte|mxm)\b|\b(für|fuer|passend für) (clevo|lenovo|asus|acer|hp|dell|msi|macbook|legion|thinkpad)")
DESKTOP = r"\b(tower|gaming[- ]?pc|desktop|komplett[- ]?pc|pc[- ]?system|midi|aio|mac ?mini|imac|mac studio)\b"
LAPTOP_CAT = "5831"                                           # willhaben's Laptops subcategory (inside laptops-notebooks-5824)
LAPTOP = r"laptop|notebook|macbook|thinkpad|ultrabook|legion|nitro|tuf|rog|victus|omen|zenbook|yoga|xps"
PREMIUM = (r"thinkpad (x1|t14s|z13|p14s|t14)|xps|zenbook|yoga (slim|pro|7)|framework|spectre|omnibook|elitebook 8"
           r"|surface laptop|gram|swift (go|16|ai)|galaxy book\s?[345]")


def first(table, t):
    for rx, score, name in table:
        if re.search(rx, t):
            return score, name
    return None, None


def ram(t):
    best = None
    for m in re.finditer(r"(\d{1,2})\s?gb\s?(?:ddr\d\s?)?(?:ram|arbeitsspeicher|ddr|memory|unified)"
                         r"|(?:ram|arbeitsspeicher)\s?:?\s?(\d{1,2})\s?gb", t):
        v = int(m.group(1) or m.group(2))
        if v in (4, 8, 12, 16, 18, 24, 32, 36, 48, 64):
            best = max(best or 0, v)
    return best


def hz(t):
    m = re.search(r"(1[2-9]\d|2[0-4]\d|300|360)\s?hz", t)
    return int(m.group(1)) if m else None


def first_cpu(t):
    """Like first(CPU, t), but Apple chip names (M1-M4) only count in an ad about a Mac: "M.2 SSD" or an "M3" mouse
    in a Windows laptop ad isn't an Apple chip."""
    apple = re.search(r"macbook|apple|\bmac\b", t)
    for rx, score, name in CPU:
        if (apple or not name.startswith("Apple")) and re.search(rx, t):
            return score, name
    return None, None


def laptop(ad):
    t = text(ad)
    gs, gn = first(GPU, t)
    cs, cn = first_cpu(t)
    ad.update(gpu=gn, cpu=cn, ram=ram(t), hz=hz(t), gpu_s=gs, cpu_s=cs)
    if gs is not None and gs >= 3.5 and (cs or 0) >= 2.7:
        ad["esports"] = "yes"
    elif gs is not None and gs >= 3.5 and cs is None:
        ad["esports"] = "cpu?"
    elif gs is not None and gs >= 2.2 and (cs or 0) >= 2.5:
        ad["esports"] = "marginal"
    else:
        ad["esports"] = None
    s = cs or 0
    if "macbook" in t:
        s += 1.5 + (0.5 if "macbook pro" in t else 0)          # build, battery, screen
    if re.search(PREMIUM, t):
        s += 1
    if re.search(r"oled|mini[- ]?led|liquid retina|2\.8k|3k|2880", t):
        s += 0.5
    if gs:
        s += min(gs, 7) * 0.4
    if (ad["ram"] or 0) >= 16:
        s += 0.7
    elif ad["ram"] and ad["ram"] <= 8:
        s -= 1
    if re.search(r"garantie|gewährleistung bis|rechnung vorhanden|mit rechnung", t):
        s += 0.4
    ad["best"] = round(s - (ad.get("price") or 0) / 1000, 2)
    title = ad.get("title", "").lower()
    if ad.get("cats") and not re.search(r"\b%s\b" % LAPTOP_CAT, ad["cats"]):      # cats look like "5824;5828;5831"
        return "not in the laptop category"
    if re.search(PART, title):
        return "part, not a laptop"
    if re.search(DESKTOP, t) and not re.search(LAPTOP, title):
        return "desktop"
    return None


def laptop_shortlist(ads, n):
    """Slots for each goal, so one kind can't crowd out the rest: cheapest esports-capable laptops, the best
    Windows/Linux all-rounders, the best MacBooks, and cheap ones whose CPU the ad doesn't name."""
    ok = [a for a in ads if not a.get("junk")]
    mac = lambda a: "macbook" in text(a)  # noqa: E731
    esports = sorted((a for a in ok if a["esports"] == "yes"), key=lambda a: a["price"])
    allround = sorted((a for a in ok if (a.get("cpu_s") or 0) >= 4 and not mac(a)), key=lambda a: -a["best"])
    macs = sorted((a for a in ok if (a.get("cpu_s") or 0) >= 4 and mac(a)), key=lambda a: -a["best"])
    unsure = sorted((a for a in ok if a["esports"] == "cpu?"), key=lambda a: a["price"])
    k = max(n // 8, 1)
    out, seen = [], set()
    for a in esports[:3 * k] + allround[:3 * k] + macs[:k] + unsure[:k] + esports + allround:
        if a["id"] not in seen and len(out) < n:
            seen.add(a["id"])
            out.append(a)
    return out


PROFILES = {"laptop": (laptop, laptop_shortlist)}
FIELDS = {"laptop": ["gpu", "cpu", "ram", "hz"]}


def annotate(ads, name=None):
    extra = PROFILES[name][0] if name else None
    for a in ads:
        reason = generic_junk(a)
        own = extra(a) if extra else None
        a["junk"] = reason or own
    return ads


def shortlist(ads, name, n):
    if name:
        return PROFILES[name][1](ads, n)
    return sorted((a for a in ads if not a.get("junk")), key=lambda a: a["price"])[:n]
