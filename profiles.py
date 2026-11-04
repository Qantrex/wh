"""Profiles: what wh knows about a kind of item, so only a shortlist reaches Claude.

annotate(ads, name) sets `junk` on every ad (a reason, or None) and adds the profile's own fields.
shortlist(ads, name, n) picks the ads worth a closer look. FIELDS[name] are the extra columns to show.

Two kinds: built-in profiles (Python, below) for items that need real parsing, and templates (TOML files in
~/.config/wh/templates, templates/ or a WH_TEMPLATES directory) for everything else: junk rules, columns, scores and new prices as data.
"""
import glob
import os
import re
import tomllib

BAD = (r"\bdefekt(?:e|er|es|em|en)?\b|\bbastler(?:gerät|geraet|stück|stueck|ware|fahrzeug|objekt)?\b"
       r"|(?:als |für |fuer )?ersatzteil(?:spender|träger|traeger|lager|gerät|geraet)\b|(?:als |für |fuer )ersatzteile?\b"
       r"|\bfür teile\b|\bfuer teile\b|\bkaputt\w*\b|\bgebrochen\w*\b|bootet nicht|startet nicht|\bwasserschaden\b"
       r"|display[- ]?riss|funktioniert nicht|nicht funktions|\bdefects?\b|\bbroken\b|not working|\bgesperrt\b"
       r"|\baktivierungssperre\b|icloud[- ]?(?:sperre|gesperrt|lock)|\bmdm\b|bios[- ]?passwort")
NEG_BEFORE = re.compile(r"\b(?:kein(?:e|er|es|em|en|erlei)?|ohne|nichts|frei von|weder|no)\s+(?:[\w-]+\s+){0,2}$"
                        r"|\bnicht\s+$")
NEG_AFTER = re.compile(r"^[^\n.;!]{0,50}\b(?:deaktiviert|entfernt|aufgehoben|abgemeldet|frei)\b")
WANTED = r"^\s*(suche|kaufe|ankauf|wir kaufen)\b"
SWAP_PHRASE = re.compile(r"\b(?:tausch\w*|tasch)\s+(?:auch\s+)?(?:gegen|mit)\b[^\n.!?;)]{0,90}\)?")


def text(ad):
    info = " ".join(ad.get("info") or []) if isinstance(ad.get("info"), list) else str(ad.get("info") or "")
    s = " ".join((ad.get("title", ""), ad.get("body", ""), ad.get("descr", ""), info))
    return s.lower().replace("–", "-").replace("—", "-")


def strip_swap(t):
    return SWAP_PHRASE.sub(" ", t)


def bad_match(t):
    for m in re.finditer(BAD, t):
        before = t[max(0, m.start() - 40):m.start()]
        after = t[m.end():m.end() + 60]
        if not NEG_BEFORE.search(before) and not NEG_AFTER.search(after):
            return m.group(0)
    return None


def generic_junk(ad):
    if re.search(WANTED, ad.get("title", "").lower()):
        return "wanted ad"
    if not ad.get("price"):                                    # None, or €0 (giveaway / price on request)
        return "no price"
    hit = bad_match(text(ad))
    return "says '%s'" % hit if hit else None


def interleave_buckets(buckets, full_lists, n):
    interleaved = [b[i] for i in range(max((len(b) for b in buckets), default=0)) for b in buckets if i < len(b)]
    out, seen, seen_sig = [], set(), set()
    for a in interleaved + [x for lst in full_lists for x in lst]:
        t_sig = re.sub(r"\s*\|\s*0\d{2,3}\s*$", "", re.sub(r"\s+", " ", a.get("title", "").lower()).strip())
        sig = (t_sig, a.get("price"), a.get("loc"))
        if a["id"] not in seen and sig not in seen_sig and len(out) < n:
            seen.add(a["id"])
            seen_sig.add(sig)
            out.append(a)
    return out


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
    (r"rtx\s?3000\s?ada", 6.5, "RTX 3000 Ada"), (r"rtx\s?2000\s?ada", 5.5, "RTX 2000 Ada"),
    (r"rtx\s?a4[05]00", 5.8, "RTX A4000"), (r"rtx\s?a3000", 5, "RTX A3000"), (r"rtx\s?a2000", 4, "RTX A2000"),
    (r"rtx\s?a1000", 3, "RTX A1000"), (r"rtx\s?a500", 2.2, "RTX A500"),
    (r"(?:quadro\s+)?rtx\s?4000\b", 5.2, "Quadro RTX 4000"), (r"(?:quadro\s+)?rtx\s?3000\b", 4.5, "Quadro RTX 3000"),
    (r"quadro\s?t2000", 3, "Quadro T2000"), (r"quadro\s?t1000", 2.5, "Quadro T1000"),
    (r"quadro\s?t[56][05]0", 1.8, "Quadro T500/T600"), (r"quadro\s?p\d{3,4}", 1.5, "Quadro P-series"),
    (r"gtx\s?-?10\s?80", 5, "GTX 1080"), (r"gtx\s?-?10\s?70", 4, "GTX 1070"), (r"gtx\s?-?16\s?60\s?ti", 3.5, "GTX 1660 Ti"),
    (r"gtx\s?-?16\s?60", 3.3, "GTX 1660"), (r"gtx\s?-?16\s?50\s?ti", 2.5, "GTX 1650 Ti"), (r"gtx\s?-?16\s?50", 2.2, "GTX 1650"),
    (r"gtx\s?-?10\s?60", 3, "GTX 1060"), (r"gtx\s?-?10\s?50\s?ti", 1.5, "GTX 1050 Ti"), (r"gtx\s?-?10\s?50", 1, "GTX 1050"),
    (r"gtx\s?-?[89][5-8]0m?", 0.8, "GTX 8xx/9xx"),
    (r"rx\s?-?7700s", 6.5, "RX 7700S"), (r"rx\s?-?7600[ms]", 6, "RX 7600M/S"),
    (r"rx\s?-?6[78]00[ms]", 6.5, "RX 6700M/6800M"), (r"rx\s?-?6[56]50m", 5.7, "RX 6650M"),
    (r"rx\s?-?6600m", 5.5, "RX 6600M"), (r"rx\s?-?6500m", 3, "RX 6500M"), (r"rx\s?-?5600m", 4, "RX 5600M"),
    (r"rx\s?-?5500m", 3, "RX 5500M"), (r"arc\s+a7\d0m", 5, "Arc A700M"), (r"arc\s+a[35]\d0m", 3, "Arc A300M/A500M"),
    (r"\bmx\s?\d{3}", 0.5, "MX"),
]
CPU = [
    (r"ultra\s?[579]\s?2\d{2}[hvx]?", 5.5, "Core Ultra 200"),
    (r"ultra\s?[579]\s?1\d{2}h", 5, "Core Ultra 1xxH"),
    (r"ultra\s?[579]\s?1\d{2}u?", 4.2, "Core Ultra 1xxU"),
    (r"(?:core\s+)?ultra\s?[579]\b", 4.2, "Core Ultra"),
    (r"(?:core\s+|i)[579]\s?-?\s?2\d0h\b", 5, "Intel Core 200H"),
    (r"(?:core\s+|i)[357]\s?-?\s?1[025]0u\b", 3.8, "Intel Core 100U"),
    (r"i[3579]\s?-?\s?14\d{3}(?:hx?)?\b", 5.5, "Intel 14th H"),
    (r"i[3579]\s?-?\s?13\d{3}(?:hx?)?\b", 5, "Intel 13th H"),
    (r"i[3579]\s?-?\s?12\d{3}(?:hx?)?\b", 4.5, "Intel 12th H"),
    (r"i[3579]\s?-?\s?11\d{3}h", 3.5, "Intel 11th H"),
    (r"i[3579]\s?-?\s?10\d{3}h", 2.5, "Intel 10th H"),
    (r"i[3579]\s?-?\s?9\d{3}h", 2, "Intel 9th H"),
    (r"i[3579]\s?-?\s?8\d{3}[hk]?", 1.5, "Intel 8th H"),
    (r"i[3579]\s?-?\s?1[23]\d{2}[up]", 3.8, "Intel 12/13th U/P"),
    (r"i[3579]\s?-?\s?11\d{2}g\d", 2.5, "Intel 11th U"),
    (r"i[3579]\s?-?\s?10\d{2,3}[ug]\d?", 1.5, "Intel 10th U"),
    (r"i[3579]\s?-?\s?[78]\d{3}u", 1, "Intel 7/8th U"),
    (r"i[357]\s?-?\s?6\d{3}u", 0.8, "Intel 6th U"),
    (r"i[357]\s?-?\s?[67]\d{3}(?:h[qk])?\b", 1.2, "Intel 6/7th HQ"),
    (r"i[57]\s?-?\s?4\d{3}[hm]q?", 1, "Intel 4th H"),
    (r"i[579][-\s]+1[34](?:\.\s?|th\s+)gen", 4, "Intel 13/14th"),
    (r"i[579][-\s]+12(?:\.\s?|th\s+)gen", 3.8, "Intel 12th"),
    (r"i[579][-\s]+11(?:\.\s?|th\s+)gen", 3, "Intel 11th"),
    (r"i[579][-\s]+10(?:\.\s?|th\s+)gen", 2.2, "Intel 10th"),
    (r"ryzen\s?(?:ai)?\s?[579]?\s?(?:pro\s?)?(?:hx\s?)?3[4-9]\d\b", 6, "Ryzen AI 300"),
    (r"\b8[6-9]4[05]hs?\b", 5, "Ryzen 8000H"),
    (r"\b8[4-8]40u\b", 4.5, "Ryzen 8040U"),
    (r"\b(?:7[4-9][45]\dhs?|7[89]45hx)\b", 5, "Ryzen 7040/7045"),
    (r"\b7[4-8]4[05]u\b", 4.5, "Ryzen 7040U"),
    (r"\b7[2-7]35hs?\b", 4, "Ryzen 7x35"),
    (r"\b6[6-9]00hs?\b", 4.2, "Ryzen 6000H"),
    (r"\b6[68][05]0u\b", 4, "Ryzen 6000U"),
    (r"\b5[6-9]00h[sx]?\b", 3.5, "Ryzen 5000H"),
    (r"\b(?:5[5-8][0257][05]u|7[357]30u)\b", 3, "Ryzen 5000U"),
    (r"\b4[6-9]00hs?\b", 2.7, "Ryzen 4000H"),
    (r"\b4[4-8][05]0u\b", 2.2, "Ryzen 4000U"),
    (r"\b3[5-7]50h\b", 1.3, "Ryzen 3000H"),
    (r"\bm5\s?(pro|max)\b", 9.5, "Apple M5 Pro/Max"),
    (r"\bm5\b", 8.5, "Apple M5"),
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
PART_HEAD = (r"^(neue?r?s? )?(kühlung|kühler|lüfter|akku|tastatur|display|bildschirm|netzteil|ladegerät|mainboard"
             r"|motherboard|gehäuse|scharnier|grafikkarte|mxm)\b")
PART_FOR = (r"\b(für|fuer|passend für) (clevo|lenovo|asus|acer|hp|dell|msi|mac\s?book|legion|thinkpad)\b")
DESKTOP = r"\b(tower|gaming[- ]?pc|desktop|komplett[- ]?pc|pc[- ]?system|midi|aio|mac ?mini|imac|mac studio)\b"
LAPTOP_CAT = "5831"                                           # Notebooks (5824 is all of Computer / Software)
LAPTOP = (r"laptop|notebook|mac\s?book|thinkpad|thinkbook|ideapad|ultrabook|legion|loq|nitro|predator|swift|aspire"
          r"|tuf|rog|zephyrus|zenbook|vivobook|victus|omen|elitebook|probook|zbook|omnibook|spectre|envy|pavilion"
          r"|yoga|xps|inspiron|latitude|precision|alienware|katana|cyborg|razer|blade|erazer|xmg|schenker|clevo|tulpar"
          r"|surface|matebook|gram|galaxy book|framework|tuxedo")
WIN_BRAND = (r"\b(asus|acer|lenovo|thinkpad|thinkbook|ideapad|yoga|legion|loq|hp|elitebook|probook|zbook|omen|victus"
             r"|pavilion|omnibook|spectre|dell|xps|inspiron|latitude|precision|alienware|msi|katana|cyborg|medion"
             r"|erazer|razer|gigabyte|aorus|tuxedo|schenker|xmg|clevo|huawei|matebook|samsung|surface|gram|framework"
             r"|tulpar)\b")
PREMIUM = (r"thinkpad (x1|t14s|z13|p14s|t14)|xps|zenbook|yoga (slim|pro|7)|framework|spectre|omnibook|elitebook 8"
           r"|surface laptop|gram|swift (go|16|ai)|galaxy book\s?[345]")
VALID_RAM = (4, 8, 12, 16, 18, 24, 32, 36, 48, 64, 96, 128, 256)
GPU_PREFIX = re.compile(r"(?:rtx|gtx|rx|quadro|nvidia|geforce|radeon|grafik\w*)"
                        r"(?:\s+(?:a?\d{3,4}|ti|super|ada|pro|max-q|[ms]))*\s*[-/|,:\s]*$")


def first(table, t):
    for row in table:
        if re.search(row[0], t):
            return row[1], row[2]
    return None, None


def is_mac(ad):
    ti = strip_swap(ad.get("title", "").lower())
    if re.search(WIN_BRAND, ti):
        return False
    return bool(re.search(r"mac\s?book", ti)
                or ("apple" in ti and not re.search(r"\b(ipad|iphone|watch|imac|mac\s?mini|mac\s?studio)\b", ti)))


def ram(t):
    best = None
    for m in re.finditer(r"\b([24])\s?[x×]\s?(\d{1,2})\s?gb\b(?!\s*(?:ssd|hdd|nvme|sata|sas|vram|gddr))", t):
        prod = int(m.group(1)) * int(m.group(2))
        if prod in VALID_RAM:
            best = max(best or 0, prod)
    for m in re.finditer(r"(?<![x×])\b(\d{1,3})\s?(?:gb\s?)?(?:ecc\s?)?(?:ddr\d\w*\s?)?(?:ram\b|arbeits?speicher|hauptspeicher|memory|unified)"
                         r"|(?<![x×]\s)(?<![x×])\b(\d{1,3})\s?(?:gb\s?)?(?:ecc\s?)?ddr[345]l?\b"
                         r"|(?:ram|arbeits?speicher|hauptspeicher|memory)\s*(?:\([^)]{1,20}\))?\s*:?\s*(\d{1,3})\s?gb"
                         r"|(?<![x×])\b(\d{1,2})\s?gb\s+(?:corsair|kingston|g\.?skill|crucial|hyperx)\b", t):
        v = int(m.group(1) or m.group(2) or m.group(3) or m.group(4))
        if v in VALID_RAM:
            best = max(best or 0, v)
    if best is not None:
        return best
    for m in re.finditer(r"\b(\d{1,2})\s?(?:gb)?\s*[/|]\s*(?:128|256|512|1000|1024|[124]\s?tb)\s?(?:gb|tb|ssd|nvme)?\b"
                         r"|\b(\d{1,2})\s?gb\s*[-,]?\s+(?:128|256|512|1000|1024|[124]\s?tb)\s?(?:gb|tb|ssd|nvme)\b", t):
        v = int(m.group(1) or m.group(2))
        if v in VALID_RAM and v <= 64 and not GPU_PREFIX.search(t[max(0, m.start() - 35):m.start()]):
            best = max(best or 0, v)
    return best


def hz(t):
    m = re.search(r"(1[2-9]\d|2[0-4]\d|300|360)\s?hz", t)
    return int(m.group(1)) if m else None


APPLE_CHIP = r"m[1-5](?:\s*(?:pro|max|ultra))?"
APPLE_CHIP_LIST = re.compile(r"\b%s(?:\s*(?:,|/|&|\boder\b|\bbzw\.?|\bund\b)\s*%s)+\b" % (APPLE_CHIP, APPLE_CHIP))
APPLE_COMPARE = re.compile(r"\b(?:gleichwertig|vergleichbar|ähnlich|equal|comparable)\s+(?:wie|mit|zu|to|with)?\s*"
                           r"(?:ein(?:em|en)?\s+|an?\s+)?%s\b" % APPLE_CHIP)


def first_cpu(t, apple=False, table=CPU):
    """Like first(table, t), but Apple chip names (M1-M5) only count in an ad about a Mac: "M.2 SSD", an "M3" mouse, or
    "Tausch gegen MacBook M4" in a Windows ad isn't an Apple chip."""
    t_norm = re.sub(r"\b(1?\d)\.(\d{3}[a-z]?)", r"\1\2", t)   # German dot separator, e.g. "i7 12.700h"
    if apple:                                                 # "gleichwertig wie ein M1, M2, M3, M4" names no chip
        t_norm = APPLE_COMPARE.sub(" ", APPLE_CHIP_LIST.sub(" ", t_norm))
    for rx, score, name in table:
        if (apple or not name.startswith("Apple")) and re.search(rx, t_norm):
            return score, name
    return None, None


def laptop(ad):
    raw_t = text(ad)
    t = strip_swap(raw_t)
    mac = is_mac(ad)
    gs, gn = first(GPU, t)
    cs, cn = first_cpu(t, apple=mac)
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
    if mac:
        s += 1.5 + (0.5 if re.search(r"mac\s?book\s+pro", t) else 0)    # build, battery, screen
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
    title = strip_swap(ad.get("title", "").lower())
    in_cat = bool(ad.get("cats") and re.search(r"\b%s\b" % LAPTOP_CAT, ad["cats"]))
    if ad.get("cats") and not in_cat:                         # cats look like "5824;5828;5831"
        return "not in the laptop category"
    if re.search(PART_HEAD, title) or re.search(PART_FOR, title):
        return "part, not a laptop"
    if re.search(r"^(neue?r?s? )?(ram|ssd)\b", title) and not re.search(LAPTOP, title):
        return "part, not a laptop"
    if re.search(DESKTOP, title if in_cat else t) and not re.search(LAPTOP, title):
        return "desktop"
    return None


def laptop_shortlist(ads, n):
    """Slots for each goal, interleaved so one kind can't crowd out the rest (and top picks of every goal get details):
    cheapest esports laptops, best iGPU Linux/Windows ultrabooks, best dGPU all-rounders, best MacBooks, and `cpu?`."""
    ok = [a for a in ads if not a.get("junk")]
    esports = sorted((a for a in ok if a["esports"] == "yes"), key=lambda a: a["price"])
    ultrabook = sorted((a for a in ok if not is_mac(a) and not a.get("gpu") and (a.get("cpu_s") or 0) >= 3.8),
                       key=lambda a: -a["best"])
    power = sorted((a for a in ok if not is_mac(a) and a.get("gpu") and (a.get("cpu_s") or 0) >= 4),
                   key=lambda a: -a["best"])
    macs = sorted((a for a in ok if is_mac(a) and (a.get("cpu_s") or 0) >= 5), key=lambda a: -a["best"])
    unsure = sorted((a for a in ok if a["esports"] == "cpu?"), key=lambda a: a["price"])
    k = max(n // 8, 1)
    full = [esports, ultrabook, power, macs, unsure]
    return interleave_buckets([esports[:3 * k], ultrabook[:2 * k], power[:k], macs[:k], unsure[:k]], full, n)


# ---- pc (desktops, gaming PCs, local-AI VRAM rigs, Mac Mini/Studio) -------------------------------------------

PC_CAT = "5833"                                               # Stand-PCs subcategory (inside 5824;5828)
NO_GPU = re.compile(r"\bohne\s+(?:grafikkarte|gpu|graka|dedizierte\s+grafik)\b"
                    r"|\bexkl(?:usive|\.)\s*(?:grafikkarte|gpu|graka)\b"
                    r"|\b(?:grafikkarte|gpu|graka)\s+(?:nicht\s+dabei|nicht\s+enthalten|wurde\s+ausgebaut|bereits\s+verkauft|fehlt)\b")
PC_PART_HEAD = re.compile(r"^(?:neue?r?s?\s+|gaming[- ]?)?(?:monitor|bildschirm|display|fernseher|tv|tastatur|maus"
                          r"|headset|stuhl|gaming[- ]?stuhl|tisch|schreibtisch|gehäuse|leergehäuse|pc[- ]?gehäuse"
                          r"|grafikkarte|mainboard|motherboard|netzteil|arbeitsspeicher|wasserkühlung|kühler|lüfter"
                          r"|festplatte|ssd|ram)\b")
PC_LAPTOP_ONLY = re.compile(r"\b(?:laptop|notebook|mac\s?book|ultrabook|thinkpad|elitebook|zenbook|vivobook|ideapad)\b")

# (regex, score, label, default_vram_gb_if_unambiguous)
PC_GPU = [
    (r"rtx\s?-?50\s?90", 10.5, "RTX 5090", 32), (r"rtx\s?-?40\s?90", 10.0, "RTX 4090", 24),
    (r"rtx\s?-?50\s?80", 9.3, "RTX 5080", 16), (r"rtx\s?-?40\s?80(?:\s?super)?", 8.8, "RTX 4080", 16),
    (r"rtx\s?-?50\s?70\s?ti", 8.5, "RTX 5070 Ti", 16),
    (r"rtx\s?-?40\s?70\s?ti\s?super", 8.3, "RTX 4070 Ti Super", 16),
    (r"rtx\s?-?30\s?90(?:\s?ti)?", 8.0, "RTX 3090", 24),
    (r"rtx\s?-?40\s?70\s?ti", 7.8, "RTX 4070 Ti", 12),
    (r"rtx\s?-?50\s?70", 7.6, "RTX 5070", 12),
    (r"rtx\s?-?40\s?70\s?super", 7.5, "RTX 4070 Super", 12),
    (r"rtx\s?-?30\s?80\s?ti", 7.4, "RTX 3080 Ti", 12),
    (r"rtx\s?-?40\s?70", 7.0, "RTX 4070", 12),
    (r"rtx\s?-?30\s?80", 6.8, "RTX 3080", 10),
    (r"rtx\s?-?50\s?60\s?ti", 6.3, "RTX 5060 Ti", None),
    (r"rtx\s?-?30\s?70\s?ti", 6.2, "RTX 3070 Ti", 8),
    (r"rtx\s?-?40\s?60\s?ti", 6.0, "RTX 4060 Ti", None),
    (r"rtx\s?-?30\s?70", 6.0, "RTX 3070", 8),
    (r"rtx\s?-?20\s?80\s?ti", 5.8, "RTX 2080 Ti", 11),
    (r"rtx\s?-?50\s?60", 5.8, "RTX 5060", 8),
    (r"rtx\s?-?30\s?60\s?ti", 5.6, "RTX 3060 Ti", 8),
    (r"rtx\s?-?40\s?60", 5.5, "RTX 4060", 8),
    (r"rtx\s?-?20\s?80(?:\s?super)?", 5.2, "RTX 2080", 8),
    (r"rtx\s?-?30\s?60", 4.8, "RTX 3060", 12),
    (r"rtx\s?-?20\s?70(?:\s?super)?", 4.6, "RTX 2070", 8),
    (r"rtx\s?-?20\s?60\s?super", 4.3, "RTX 2060 Super", 8),
    (r"rtx\s?-?20\s?60", 3.8, "RTX 2060", None),
    (r"rtx\s?-?30\s?50", 3.5, "RTX 3050", None),
    (r"rtx\s?a6000", 8.5, "RTX A6000", 48), (r"rtx\s?a5000", 7.5, "RTX A5000", 24),
    (r"rtx\s?(?:a4500|4000\s?ada)", 7.0, "RTX A4500/4000 Ada", 20),
    (r"rtx\s?a4000", 6.0, "RTX A4000", 16), (r"rtx\s?a2000", 4.0, "RTX A2000", None),
    (r"gtx\s?-?10\s?80\s?ti", 4.6, "GTX 1080 Ti", 11), (r"gtx\s?-?10\s?80", 3.8, "GTX 1080", 8),
    (r"gtx\s?-?10\s?70(?:\s?ti)?", 3.5, "GTX 1070", 8),
    (r"gtx\s?-?16\s?60\s?(?:super|ti)", 3.5, "GTX 1660 Super/Ti", 6),
    (r"gtx\s?-?16\s?60", 3.2, "GTX 1660", 6), (r"gtx\s?-?16\s?50\s?super", 2.6, "GTX 1650 Super", 4),
    (r"gtx\s?-?10\s?60", 2.5, "GTX 1060", None), (r"gtx\s?-?16\s?50", 2.0, "GTX 1650", 4),
    (r"gtx\s?-?10\s?50\s?ti", 1.5, "GTX 1050 Ti", 4), (r"gtx\s?-?9[78]0(?:\s?ti)?", 2.0, "GTX 970/980", None),
    (r"rx\s?-?9070\s?xt", 8.3, "RX 9070 XT", 16), (r"rx\s?-?9070\b", 7.6, "RX 9070", 16),
    (r"rx\s?-?7900\s?xtx", 8.8, "RX 7900 XTX", 24), (r"rx\s?-?7900\s?xt\b", 8.0, "RX 7900 XT", 20),
    (r"rx\s?-?7900\s?gre", 7.4, "RX 7900 GRE", 16), (r"rx\s?-?7800\s?xt", 7.0, "RX 7800 XT", 16),
    (r"rx\s?-?69[05]0\s?xt", 7.3, "RX 6900/6950 XT", 16), (r"rx\s?-?6800\s?xt", 6.8, "RX 6800 XT", 16),
    (r"rx\s?-?6800\b", 6.3, "RX 6800", 16), (r"rx\s?-?7700\s?xt", 6.3, "RX 7700 XT", 12),
    (r"rx\s?-?67[05]0\s?xt", 5.6, "RX 6700/6750 XT", 12), (r"rx\s?-?6700\b", 5.0, "RX 6700", 10),
    (r"rx\s?-?7600\s?xt", 5.3, "RX 7600 XT", 16), (r"rx\s?-?7600\b", 5.0, "RX 7600", 8),
    (r"rx\s?-?66[05]0\s?xt", 4.8, "RX 6600/6650 XT", 8), (r"rx\s?-?6600\b", 4.4, "RX 6600", 8),
    (r"rx\s?-?5700\s?xt", 4.5, "RX 5700 XT", 8), (r"rx\s?-?5700\b", 4.0, "RX 5700", 8),
    (r"rx\s?-?5600\s?xt", 3.8, "RX 5600 XT", 6), (r"rx\s?-?[45][78]0\b", 2.2, "RX 470-580", None),
    (r"arc\s+b580", 5.5, "Arc B580", 12), (r"arc\s+b570", 4.8, "Arc B570", 10),
    (r"arc\s+a770", 5.0, "Arc A770", 16), (r"arc\s+a750", 4.5, "Arc A750", 8),
]
PC_CPU = [
    (r"\b(?:9800x3d|9950x3d|7800x3d|7950x3d)\b", 7.5, "Ryzen 7/9 X3D"),
    (r"\b99[05]0x\b", 7.0, "Ryzen 9 9900X/9950X"), (r"\b9[67]00x\b", 6.4, "Ryzen 5/7 9000"),
    (r"\b79[05]0x\b", 6.6, "Ryzen 9 7900X/7950X"),
    (r"\b(?:5800x3d|5700x3d|5600x3d)\b", 6.0, "Ryzen 5000X3D"),
    (r"\b(?:7[5678]00x|7500f|8[47]00f|8[67]00g)\b|(?:ryzen(?:\s+[579])?|r[579])[-\s]+7[56789]00\b", 5.7, "Ryzen 7000/8000"),
    (r"\b59[05]0x\b", 5.4, "Ryzen 9 5900X/5950X"),
    (r"\b5[78]00x\b|(?:ryzen(?:\s+7)?|r7)[-\s]+5[78]00g?\b", 4.8, "Ryzen 7 5700/5800"),
    (r"\b5600[xt]\b|(?:ryzen(?:\s+5)?|r5)[-\s]+5600\b", 4.3, "Ryzen 5 5600"),
    (r"\b5[67]00g\b|(?:ryzen(?:\s+5)?|r5)[-\s]+5500\b", 3.7, "Ryzen 5500/5600G"),
    (r"\b39[05]0x\b", 4.2, "Ryzen 9 3900X"),
    (r"\b3[78]00x\b|(?:ryzen(?:\s+7)?|r7)[-\s]+3[78]00\b", 3.7, "Ryzen 7 3700X/3800X"),
    (r"\b3600x(?:t)?\b|(?:ryzen(?:\s+5)?|r5)[-\s]+3600\b", 3.3, "Ryzen 5 3600"),
    (r"\b(?:4600g|3400g|3300x|2400g)\b|(?:ryzen(?:\s+[35])?|r[35])[-\s]+(?:4500|3100)\b", 2.4, "Ryzen 2400G-4600G"),
    (r"\b2[67]00x\b|(?:ryzen(?:\s+[57])?|r[57])[-\s]+2[67]00\b", 2.2, "Ryzen 5/7 2000"),
    (r"\b1[678]00x\b|(?:ryzen(?:\s+[57])?|r[57])[-\s]+1[67]00\b", 1.6, "Ryzen 1000"),
    (r"ultra\s?[579]\s?2\d{2}k?f?\b", 6.4, "Core Ultra 200S"),
    (r"i[79]\s?-?\s?1[34]\d{3}k?f?\b", 6.2, "Intel i7/i9 13/14th"),
    (r"i5\s?-?\s?1[34][456]\d0k?f?\b", 5.4, "Intel i5 13/14th"),
    (r"i[79]\s?-?\s?12\d{3}k?f?\b", 5.4, "Intel i7/i9 12th"),
    (r"i5\s?-?\s?12[46]\d0k?f?\b", 4.5, "Intel i5 12th"),
    (r"i3\s?-?\s?1[234]100f?\b", 3.5, "Intel i3 12-14th"),
    (r"i[579]\s?-?\s?11\d{3}k?f?\b", 3.8, "Intel 11th"),
    (r"i[579]\s?-?\s?10\d{3}k?f?\b", 3.3, "Intel 10th"),
    (r"i[79]\s?-?\s?9[79]00k?f?\b", 3.0, "Intel i7/i9 9th"),
    (r"i[57]\s?-?\s?[89][467]00k?f?\b", 2.5, "Intel 8/9th"),
    (r"i[57]\s?-?\s?[67]\d{3}k?\b", 1.5, "Intel 6/7th"),
    (r"i[57]\s?-?\s?[234]\d{3}k?\b", 0.8, "Intel 2nd-4th"),
    (r"\bfx[-\s]?[468]\d{3}\b", 0.5, "AMD FX"),
    (r"\bm4\s?(pro|max)\b", 8.5, "Apple M4 Pro/Max"), (r"\bm4\b", 7.2, "Apple M4"),
    (r"\bm2\s?(pro|max|ultra)\b", 7.0, "Apple M2 Pro/Max"), (r"\bm2\b", 5.8, "Apple M2"),
    (r"\bm1\s?(max|ultra)\b", 6.5, "Apple M1 Max/Ultra"), (r"\bm1\b", 4.8, "Apple M1"),
]
VALID_VRAM = (4, 6, 8, 10, 11, 12, 16, 20, 24, 32, 48)
LOOSE_GPU_TITLE = re.compile(
    r"^(?:verkaufe\s+)?(?:nvidia\s+|amd\s+|asus\s+|msi\s+|gigabyte\s+|zotac\s+|palit\s+|gainward\s+|sapphire\s+"
    r"|xfx\s+|inno3d\s+|pny\s+|evga\s+|kfa2\s+|geforce\s+|radeon\s+)*(?:rtx|gtx|rx)\s?-?\d{3,4}"
)


def pc_gpu_vram(t):
    if NO_GPU.search(t):
        return None, None, None
    for rx, score, name, def_vram in PC_GPU:
        for m in re.finditer(rx, t):
            tail = t[m.end():m.end() + 42]
            vm = re.match(r"^(?:[\s(-]|ti\b|super\b|oc\b|gaming\b|ventus\b|tuf\b|strix\b|windforce\b|pulse\b"
                          r"|ghost\b|amp\b|holo\b|eagle\b|dual\b|trio\b|lhr\b|mit\b|o?\d+g\b)*?"
                          r"(\d{1,2})\s?gb\b(?!\s*(?:ram\b|ddr|ssd|nvme|arbeitsspeicher|corsair|kingston|g\.?skill|crucial))",
                          tail)
            if vm and int(vm.group(1)) in VALID_VRAM:
                return score, name, int(vm.group(1))
        if re.search(rx, t):
            vm2 = re.search(r"\b(\d{1,2})\s?gb\s*(?:gddr\d\w*|vram|grafikspeicher)\b"
                            r"|(?:vram|grafikspeicher)\s*:?\s*(\d{1,2})\s?gb\b", t)
            if vm2:
                v = int(vm2.group(1) or vm2.group(2))
                if v in VALID_VRAM:
                    return score, name, v
            return score, name, def_vram
    return None, None, None


def is_mac_desktop(ad):
    ti = strip_swap(ad.get("title", "").lower())
    return bool(re.search(r"\b(?:mac\s?mini|mac\s?studio|imac)\b", ti))


def pc(ad):
    t = strip_swap(text(ad))
    title = strip_swap(ad.get("title", "").lower())
    mac = is_mac_desktop(ad)
    gs, gn, vr = pc_gpu_vram(t)
    cs, cn = first_cpu(t, apple=mac, table=PC_CPU)
    r = ram(t)
    is_nvidia = bool(gn and gn.startswith(("RTX", "GTX")))
    ad.update(gpu=gn, cpu=cn, ram=r, vram=("%d GB VRAM" % vr) if vr else None,
              vram_gb=vr, gpu_s=gs, cpu_s=cs, nvidia=is_nvidia)
    s = (cs or 0) * 0.8 + (gs or 0) * 1.1
    if is_nvidia and (vr or 0) >= 12:
        s += 1.0 + (0.6 if vr >= 16 else 0) + (0.8 if vr >= 24 else 0)  # local AI / CUDA bonus
    if (r or 0) >= 32:
        s += 0.8
    elif (r or 0) >= 16:
        s += 0.3
    elif r and r <= 8:
        s -= 0.8
    if mac and (cs or 0) >= 5.5:
        s += 1.5
    if re.search(r"garantie|gewährleistung bis|rechnung vorhanden|mit rechnung", t):
        s += 0.4
    ad["best"] = round(s - (ad.get("price") or 0) / 800, 2)
    cats = ad.get("cats") or ""
    if cats:
        if re.search(r"\b5831\b", cats):
            return "laptop"
        if not re.search(r"\b%s\b" % PC_CAT, cats):
            return "not in the desktop PC category"
    if PC_PART_HEAD.search(title):
        return "monitor/peripheral/part, not a PC"
    if (LOOSE_GPU_TITLE.search(title)
            and not re.search(r"\b(?:pc|computer|rechner|system|tower|itx|ryzen|intel|core\s+i[3579]|i[3579][-\s]\d)\b", title)):
        return "loose GPU in PC category"
    if re.search(r"\bmonitor\b", title) and not re.search(r"\b(?:pc|computer|rechner|tower|setup|komplett)\b", title):
        return "monitor, not a PC"
    if PC_LAPTOP_ONLY.search(title) and not re.search(r"\b(?:desktop|tower|stand[- ]?pc|gaming[- ]?pc)\b", title):
        return "laptop"
    return None


def pc_shortlist(ads, n):
    """Interleave: cheapest 1080p/esports PCs, best >=12 GB VRAM NVIDIA rigs (local AI + 1440p), best high-end builds,
    compact/Mac Mini desktops, and cheap dGPU PCs missing CPU in snippet (`cpu?`)."""
    ok = [a for a in ads if not a.get("junk")]
    esports = sorted((a for a in ok if (a.get("gpu_s") or 0) >= 3.4 and (a.get("cpu_s") or 0) >= 3.0),
                     key=lambda a: a["price"])
    ai_vram = sorted((a for a in ok if a.get("nvidia") and (a.get("vram_gb") or 0) >= 12 and (a.get("cpu_s") or 0) >= 3.0),
                     key=lambda a: -a["best"])
    power = sorted((a for a in ok if (a.get("gpu_s") or 0) >= 5.5 and (a.get("cpu_s") or 0) >= 4.3),
                   key=lambda a: -a["best"])
    compact = sorted((a for a in ok if (is_mac_desktop(a) and (a.get("cpu_s") or 0) >= 4.8)
                      or (re.search(r"\b(?:itx|mini[- ]?itx|sff|nr200|dan\s?a4|terra|lian\s?li\s?a[34])\b", text(a))
                          and (a.get("gpu_s") or 0) >= 4.4)),
                     key=lambda a: -a["best"])
    unsure = sorted((a for a in ok if (a.get("gpu_s") or 0) >= 3.5 and a.get("cpu_s") is None),
                    key=lambda a: a["price"])
    k = max(n // 8, 1)
    full = [esports, ai_vram, power, compact, unsure]
    return interleave_buckets([esports[:2 * k], ai_vram[:3 * k], power[:k], compact[:k], unsure[:k]], full, n)


# ---- server (TinyMiniMicro nodes, NAS, MicroServers, quiet tower/home servers) --------------------------------

SERVER_OK_CATS = re.compile(r"\b(?:5833|5875|5873|5868)\b")   # Stand-PCs/Mini-PCs, Server, NAS, external storage
SERVER_BAD_CATS = re.compile(r"\b(?:5878|5831|5834|5874|5836|2691|387|5387)\b")
SERVER_PART = re.compile(
    r"^(?:konvolut\s+)?(?:\d+\s?x\s*)?(?:original\w*\s+)?"
    r"(?:hp|hpe|dell|ibm|lenovo|synology|qnap|supermicro|intel|micron|hynix|samsung|wd|seagate|toshiba|hgst)?\s*"
    r"(?:\d+(?:[.,]\d+)?\s?(?:gb|tb)\s+)?(?:ddr[2345]l?\b|ecc\b|server[- ]?ram|ram[- ]?modul|speicherram|arbeitsspeicher"
    r"|sas\b|sata\b|festplatte\w*|hdd\w*|ssd\w*|nvme\b)"
    r"|\b(?:frontblende|front\s?bezel|slotblende|blank\s?cover|blindblende|einbauschienen|rack\s?rails?|gleitschienen"
    r"|kabelhalter\w*|festplattenrahmen|caddy|drive\s?tray|backplane|power\s?cable|stromkabel|patchpanel|pdu\b"
    r"|serverschrank|netzwerkschrank|wandverteiler|19\s?(?:zoll|\")\s*(?:schrank|rack|gehäuse)|print\s?server"
    r"|video\s?station|surveillance|poe[- ]?kamera|ip[- ]?kamera|\busv\b|\bups\b|ersatz[- ]?netzteil|server[- ]?netzteil)\b"
    r"|ohne\s+cpu\s+und\s+ohne\s+netz"
)
SERVER_CPU = [
    (r"\b(?:i3[-\s]?)?n30[05]\b", 4.6, "Core i3-N305"),
    (r"\bn(?:100|150|97|95)\b", 4.0, "Intel N100/N95"),
    (r"\b(?:j4125|j4105|j5005|j5040|n5105|n5095|n6005)\b", 2.8, "Celeron J4xxx/N5xxx"),
    (r"\b(?:j3[34]55|j1900|n3[01]\d0|n40[02]0)\b", 1.5, "Celeron J3xxx/N3xxx"),
    (r"i[579]\s?-?\s?1[234]\d{3}t?\b", 5.6, "Intel i5/i7 12-14th"),
    (r"i3\s?-?\s?1[234]\d{3}t?\b", 4.6, "Intel i3 12-14th"),
    (r"i[579]\s?-?\s?1[01]\d{3}t?\b", 4.6, "Intel i5/i7 10/11th"),
    (r"i3\s?-?\s?1[01]\d{3}t?\b", 3.8, "Intel i3 10/11th"),
    (r"i[579]\s?-?\s?[89]\d{3}t?\b", 4.2, "Intel i5/i7 8/9th"),
    (r"i3\s?-?\s?[89]\d{3}t?\b", 3.5, "Intel i3 8/9th"),
    (r"pentium\s+gold\s+g[56]\d{3}t?\b", 2.8, "Pentium Gold"),
    (r"i[57]\s?-?\s?[67]\d{3}t?\b", 2.5, "Intel i5/i7 6/7th"),
    (r"i3\s?-?\s?[67]\d{3}t?\b", 2.0, "Intel i3 6/7th"),
    (r"i[357]\s?-?\s?[45]\d{3}t?\b", 1.2, "Intel 4/5th"),
    (r"\b(?:r1600|v1500b|v1780b)\b", 3.2, "Ryzen Embedded"),
    (r"ryzen\s?[579]\s?(?:pro\s?)?[56789]\d{3}[guxts]?\b", 5.0, "Ryzen 5000-9000"),
    (r"ryzen\s?[357]\s?(?:pro\s?)?[234]\d{3}[guxts]?\b", 3.5, "Ryzen 2000-4000"),
    (r"\bepyc\s?\d{4}\w*\b", 5.5, "AMD EPYC"),
    (r"xeon\s+(?:gold|silver)\s+\d{4}\w*", 4.6, "Xeon Scalable"),
    (r"xeon\s+e-2[1234]\d{2}g?\b", 4.5, "Xeon E-2xxx"),
    (r"xeon\s+w-\d{4}\w*\b", 4.2, "Xeon W"),
    (r"xeon\s+e3-12\d{2}\s?v[56]\b", 3.4, "Xeon E3 v5/v6"),
    (r"xeon\s+e3-12\d{2}\s?v[34]\b", 2.2, "Xeon E3 v3/v4"),
    (r"xeon\s+e5-26\d{2}\s?v[34]\b", 2.4, "Xeon E5 v3/v4"),
    (r"xeon\s+(?:e5-26\d{2}(?:\s?v[12])?|[xel]5[56]\d{2})\b", 0.8, "Xeon DDR3"),
]


def server_form(t):
    if re.search(r"\bmicroserver\b", t):
        return "MicroServer"
    if re.search(r"\b[124]\s?(?:u|he)\b|rack\s?server|rackmount|dl\s?3[68]0|dl\s?1[68]0|dl\s?20\b|poweredge\s*r\d{3}"
                 r"|primergy\s*rx\d+|(?:thinksystem\s*)?sr\d{3}\b|superchassis", t):
        return "Rack"
    if re.search(r"\b(?:thinkcentre\s*)?m(?:70|80|90|600|700|710|715|720|75|900|910|920)[qx]\b"
                 r"|(?:elitedesk|prodesk)\s*\d+\s*g\d+\s*(?:mini|dm\b)|hp\s+(?:pro|elite)\s+mini"
                 r"|optiplex\s*\d+\s*(?:micro|mff)|esprimo\s*[qg]\d+|futro\s*s\d+"
                 r"|\bnuc\d*\b|minisforum|beelink|gmktec|deskmini|\b(?:tiny|usff|mini[- ]?pc|desktop[- ]?mini)\b"
                 r"|\bn(?:100|95|97|150|305)\b", t):
        return "Tiny/Mini"
    if re.search(r"\bsynology\b|\bdiskstation\b|\bds\d{3,4}[+j]?\b|\brs(?!232\b|485\b)\d{3,4}\+?\b|\bqnap\b|\bts-\d{3}\w*\b"
                 r"|\bugreen\s*nasync|\bdxp\d{4}\b|\bterramaster\b|\basustor\b|nas[- ]?basis|\btruenas\b|\bunraid\b", t):
        return "NAS"
    if re.search(r"proliant\s*ml\d+|poweredge\s*t\d+|primergy\s*tx\d+|thinksystem\s*st\d+|precision\s*(?:t?\d{4}|36\d0)"
                 r"|z[24]\s*g\d|thinkstation\s*p\d+|thinkcentre\s*m\d+[st]?\b|(?:elitedesk|prodesk)\s*\d+\s*g\d+"
                 r"|optiplex\s*\d+|\bsff\b|\btwr\b|home\s?server|proxmox|tower\s?server", t):
        return "Tower"
    if re.search(r"\bnas\b", t):
        return "NAS"
    return None


def server_bays(t):
    m = re.search(r"\b([2-9]|1[26])\s?-?\s?bay\b", t)
    if m:
        return "%s-bay" % m.group(1)
    m = re.search(r"\bds(18|16|15|[12479])\d{2}[+j]?\b", t)
    if m:
        mp = {"1": 1, "2": 2, "7": 2, "4": 4, "9": 4, "15": 5, "16": 6, "18": 8}
        return "%d-bay" % mp[m.group(1)]
    m = re.search(r"\bdxp([2468])\d00\b", t)
    if m:
        return "%s-bay" % m.group(1)
    if re.search(r"\bmicroserver\s+gen\s?(?:8|10)\b", t):
        return "4-bay"
    return None


def server(ad):
    t = strip_swap(text(ad))
    title = strip_swap(ad.get("title", "").lower())
    form = server_form(t)
    cs, cn = first_cpu(t, apple=False, table=SERVER_CPU)
    # Infer known Synology CPU families when seller only writes the DiskStation model
    if not cn:
        if re.search(r"\bds(?:220|224|420|423|720|920)\+", t):
            cs, cn = 2.8, "Celeron J4xxx (x86)"
        elif re.search(r"\bds(?:723|923|1522|1621|1821)\+", t):
            cs, cn = 3.2, "Ryzen Embedded"
        elif re.search(r"\bds(?:218|718|918|1019)\+", t):
            cs, cn = 2.2, "Celeron J3xxx (x86)"
        elif re.search(r"\bds\d{3,4}(?:j|play|se)?\b", t):
            cs, cn = 0.8, "ARM/Marvell NAS"
    r = ram(t)
    bays = server_bays(t)
    ad.update(form=form, cpu=cn, ram=r, bays=bays, cpu_s=cs)
    s = cs or 1.5
    if form == "Tiny/Mini":
        s += 2.0 + (0.6 if re.search(r"m720q|m920[qx]|m90q", t) else 0)  # quiet ~7W + PCIe riser models
    elif form in ("NAS", "MicroServer"):
        s += 1.8 + (0.6 if re.search(r"\bds\d+\+|\bdxp\d+|gen10\s*plus", t) else 0)
        if cn == "ARM/Marvell NAS":
            s -= 2.2
    elif form == "Tower":
        s += 0.8
    elif form == "Rack":
        s -= 2.5                                              # loud & 80-180W idle (€190-430/yr in Wien)
    if (r or 0) >= 32:
        s += 1.0
    elif (r or 0) >= 16:
        s += 0.6
    elif (r or 0) >= 8:
        s += 0.2
    if re.search(r"\bbarebone\b|ohne\s+(?:ssd|festplatte|hdd|ram|netzteil)", t):
        s -= 0.7
    ad["best"] = round(s - (ad.get("price") or 0) / 250, 2)
    cats = ad.get("cats") or ""
    if cats:
        if SERVER_BAD_CATS.search(cats) and not SERVER_OK_CATS.search(cats):
            return "component/non-server category"
    if SERVER_PART.search(title) or re.search(r"\bohne cpu und ohne netz", t):
        return "server part/accessory, not a machine"
    if PC_LAPTOP_ONLY.search(title):
        return "laptop"
    if re.search(r"\ball[- ]?in[- ]?one\b|thinkcentre\s*m\d+z\b|\bimac\b", t):
        return "All-in-One desktop, not a server"
    if not form and not cn:
        return "not recognisably a server/mini-PC/NAS"
    return None


def server_shortlist(ads, n):
    """Interleave: <=€100 budget TinyMiniMicro (home-server replacement), QuickSync 8th-gen+/N100 Tiny nodes,
    x86 NAS & MicroServers, and quiet Tower servers."""
    ok = [a for a in ads if not a.get("junk")]
    tiny_budget = sorted((a for a in ok if a.get("form") == "Tiny/Mini" and a["price"] <= 110
                          and (a.get("cpu_s") or 0) >= 1.5),
                         key=lambda a: (a["price"], -a["best"]))
    tiny_modern = sorted((a for a in ok if a.get("form") == "Tiny/Mini" and (a.get("cpu_s") or 0) >= 3.5),
                         key=lambda a: -a["best"])
    nas_micro = sorted((a for a in ok if a.get("form") in ("NAS", "MicroServer")
                        and a.get("cpu") != "ARM/Marvell NAS"),
                       key=lambda a: -a["best"])
    towers = sorted((a for a in ok if a.get("form") == "Tower" and (a.get("cpu_s") or 0) >= 2.2),
                    key=lambda a: -a["best"])
    rest = sorted(ok, key=lambda a: -a["best"])
    k = max(n // 8, 1)
    full = [tiny_budget, tiny_modern, nas_micro, towers, rest]
    return interleave_buckets([tiny_budget[:2 * k], tiny_modern[:3 * k], nas_micro[:2 * k], towers[:k]], full, n)


# ---- hue (genuine Philips Hue controls, colour bulbs, lamps, strips & sets) -----------------------------------

HUE_NON_LIGHT = re.compile(r"luftbefeuchter|air\s?washer|nanocloud|\bhu\d{4}\b|\bfy\d{4}\b|avent|sonicare|oneblade"
                           r"|rasierer|shaver|airfryer|epilierer|staubsauger|kaffeemaschine|espressomaschine"
                           r"|ambilight\s*tv|\bfernseher\b|\buhd\s*tv\b|\boled\s*tv\b")
HUE_3RDPARTY = re.compile(r"\b(?:aqara|innr|gledopto|paulmann|müller[- ]?licht|tint|tuya|sonoff|livarno|osram"
                          r"|ledvance|wiz|shelly|meross|govee|nanoleaf|homematic|tapo|kasa|avatar|yeelight)\b")
HUE_CLONE_TEXT = re.compile(r"(?:ähnlich(?:\s+wie)?|kompatibel\s+mit|alternative\s+zu|wie)\s+(?:philips\s+)?hue\b")
HUE_PART_ONLY = re.compile(
    r"^(?:\d+\s?x\s*)?(?:unbenutztes\s+|original\w*\s+|philips\s+hue\s+)*(?:v[12]\s+)?(?:dimmer\s+|schalter\s+|outdoor\s+|perifo\s+)*"
    r"(?:abdeckung|wandhalterung|halterung(?:en)?|halter|montageplatte|uk[- ]?adapter|adapter|t-stück|t-stecker"
    r"|verlängerung\w*|cable\s+extension|netzteil|aluminium\s+profile?|alu[- ]?profil\w*|zubehör|leerkarton|leere?\s+ovp)\b"
    r"|\b(?:t-stück|t-stecker|aluminium\s+profile?|alu[- ]?profil\w*|uk[- ]?adapter|leerkarton|leere?\s+ovp"
    r"|nur\s+verpackung|ohne\s+leuchtmittel)\b"
    r"|(?:dimmer|schalter)\s+abdeckung\b"
)
HUE_PER_UNIT = re.compile(r"preis\s+(?:ist\s+)?pro\s+st(?:ück|k)\b|\bje\s+st(?:ück|k)\b|\d+\s*€\s*pro\s+st(?:ück|k)\b"
                          r"|pro\s+st(?:ück|k)\s*\d|\bnur\s+ein\s+stück\b")
HUE_V1_BRIDGE = re.compile(r"bridge[^\n]{0,40}(?:1\.\s?gen|\bi\s+gen|erste\s+gen|gen\s?1\b|\bv1\b|\brund\w*\b)"
                           r"|\brunde\s+(?:philips\s+)?hue\s+bridge\b")


def hue_qty(title, t):
    m_pack = re.search(r"\b(\d{1,2})\s?er[- ]?(?:pack\w*|set|paket)\b", title)
    if m_pack and 2 <= int(m_pack.group(1)) <= 20:
        return int(m_pack.group(1))
    if re.search(r"\bdoppelpack|\b2[- ]?pack|\btwin[- ]?pack", title):
        return 2
    if re.search(r"\b3[- ]?pack|\bdreierpack", title):
        return 3
    if re.search(r"\b4[- ]?pack|\bviererpack", title):
        return 4
    if HUE_PER_UNIT.search(t):
        return 1
    for src in (title, t):
        for m in re.finditer(r"\b(\d{1,2})\s?(?:er[- ]?(?:pack\w*|set|paket)|x\b|stk\.?\b|stück\b)", src):
            after = src[m.end():m.end() + 22]
            if re.match(r"^\s*(?:m\b|cm\b|mm\b|w\b|watt\b|lm\b|aaa?\b|cr\d|vorhanden|verfügbar|lagernd)", after):
                continue
            q = int(m.group(1))
            if 2 <= q <= 20:
                return q
    return 1


HUE_BRIDGE = r"\b(?:bridge|gateway|base\s?station|basisstation)\b"
HUE_EXTRAS = re.compile(r"\s(?:inkl\.?|inklusive|incl\.?|mit|samt|plus|\+)\s")  # what follows is an add-on


def _match_hue_kind(s):
    if re.search(r"dimm(?:er|schalter)[^\n]{0,25}(?:v2|rwl022|2\.\s?gen|neues\s+modell)|rwl022|\bv2\s+dimm", s):
        return "Dimmer V2"
    if re.search(r"dimm(?:er|schalter)|\bremote\b|rwl02[01]", s):
        return "Dimmer"
    if re.search(r"tap\s?dial|wandschalter[- ]?modul|wall\s?switch|smart\s?button|\bhue\s+tap\b|friends\s+of\s+hue", s):
        return "Switch"
    if re.search(r"bewegungsmelder|bewegungssensor|motion\s?sensor|outdoor\s?sensor|tür[- ]?(?:und\s+fenster)?kontakt|contact\s?sensor", s):
        return "Sensor"
    if re.search(r"sync\s?box|hdmi\s+sync|play\s+(?:light)?bar|play\s+gradient", s):
        return "Play/Sync"
    if re.search(r"gradient\s+lightstrip|lightstrip|led[- ]?strip|omniglow|\bflux\b", s):
        return "Strip"
    if re.search(r"\bhue\s+(?:go|iris|signe|bloom|flourish|wellness|explore|ensis|infuse|centris|aurelle|surimu"
                 r"|datura|enrave|still|being|adore|perifo|appear|resonate|lily|calla|fuzo|turaco|impress)\b"
                 r"|\b(?:runner|buckram|fugato|argenta|pillar)\b|tischleuchte|tisch\s?lampe|stimmungsleuchte"
                 r"|stehleuchte|stehlampe|deckenleuchte|deckenlampe|pendelleuchte|hängelampe|wandleuchte|wandlampe"
                 r"|außenleuchte|sockelleuchte|\b\d\s?-?\s?fl(?:g\b|ammig)", s):  # "Runner Spot 3 flg." is a fixture
        return "Lamp"
    if re.search(r"smart\s?plug|steckdose|zwischenstecker", s):
        return "Plug"
    if re.search(r"\b(?:e27|e14|gu10)\b|leuchtmittel|glühbirne\w*|\bbirne(?:n)?\b|\blampe(?:n)?\b|filament|\bspot(?:s)?\b|kerze", s):
        return "Bulb"
    if re.search(HUE_BRIDGE + r"|\bhub\b", s):
        return "Bridge"
    return None


def hue_kind_spec(title, t, q):
    is_bundle = bool(re.search(r"starter[- ]?(?:set|kit)|startpaket|konvolut|\bpaket\b|\bhue\s+set\b", title)
                     or (re.search(HUE_BRIDGE, title)
                         and re.search(r"lampe|birne|dimm|sensor|e27|gu10|lichtband|lightstrip", title)))
    if is_bundle:
        kind = "Bundle"
    else:
        head, extras = (HUE_EXTRAS.split(title, 1) + [""])[:2]
        kind = _match_hue_kind(head) or _match_hue_kind(title) or _match_hue_kind(t) or "Hue"
        if kind in ("Dimmer", "Switch", "Sensor") and _match_hue_kind(extras) in ("Bulb", "Lamp", "Strip"):
            kind = "Bundle"                                   # "Dimmschalter mit Glühbirnen"; a lamp "inkl. Dimmer" stays a lamp
        if kind == "Dimmer" and re.search(r"rwl022|\bv2\b|2\.\s?gen|neues\s+modell", t):
            kind = "Dimmer V2"

    spec_src = title if kind == "Bridge" else t
    bits = []
    sock = re.search(r"\b(e27|gu10|e14)\b", spec_src)
    if sock:
        bits.append(sock.group(1).upper())
    if kind != "Bridge":
        if re.search(r"colou?r|farb\w*|rgb|16\s?mio", spec_src):
            bits.append("Color")
        elif re.search(r"white\s+ambiance", spec_src):
            bits.append("White Ambiance")
        elif re.search(r"filament", spec_src):
            bits.append("Filament")
        elif kind in ("Bulb", "Bundle") and re.search(r"warmwei(?:ß|ss)|\bhue\s+white\b", spec_src):
            bits.append("White")
    lm = re.search(r"\b(800|806|1055|1100|1600)\s?(?:lm|lumen)\b", spec_src)
    if lm:
        bits.append(lm.group(1) + "lm")
    if kind == "Strip" and re.search(r"\berweiterung\b|\bextension\b|\b1\s?m\b", title) and not re.search(r"basis|2\s?m\b|\+", title):
        bits.append("Extension only")
    if kind == "Bridge" and re.search(r"bridge\s+pro", t):
        bits.append("Pro")
    if re.search(r"\bneu\b|\bovp\b|ungeöffnet|originalverpackt", title):
        bits.append("OVP/new")
    return kind, " ".join(bits) or None


# Rough fair unit value in € (used) so `best` surfaces genuinely underpriced packs, switches, and lamps
HUE_UNIT_REF = {
    "Dimmer V2": 16, "Dimmer": 11, "Switch": 26, "Sensor": 22, "Play/Sync": 45,
    "Strip": 35, "Lamp": 45, "Bulb": 14, "Bundle": 32, "Plug": 14, "Bridge": 8, "Hue": 15,
}


def hue(ad):
    t = strip_swap(text(ad))
    title = strip_swap(ad.get("title", "").lower())
    q = hue_qty(title, t)
    kind, spec = hue_kind_spec(title, t, q)
    ad.update(kind=kind, spec=spec, qty=("%d×" % q) if q > 1 else None, qty_n=q)
    unit_ref = HUE_UNIT_REF.get(kind, 15)
    if spec and "Color" in spec and kind == "Bulb":
        unit_ref = 20
    elif spec and "White" in spec and "Ambiance" not in spec and kind == "Bulb":
        unit_ref = 7
    if spec and "Extension only" in spec:
        unit_ref = 10
    est_val = unit_ref * (1 + 0.75 * (q - 1))                 # multi-packs scale sub-linearly
    price = ad.get("price") or 999
    ad["best"] = round((est_val - price) / max(est_val, 10) * 5 + (0.8 if kind == "Dimmer V2" else 0), 2)
    if HUE_NON_LIGHT.search(t) or not re.search(r"\bhue\b", t):
        return "not Philips Hue lighting"
    if not re.search(r"\bhue\b", title):
        return "Hue only mentioned in body (not title)"
    if HUE_3RDPARTY.search(title) and not re.search(r"\bphilips\s+hue\b", title):
        return "third-party brand, not Hue"
    if HUE_CLONE_TEXT.search(t) and not re.search(r"\bphilips\s+hue\b", title):
        return "Hue-compatible clone, not genuine Hue"
    if HUE_PART_ONLY.search(title) or re.search(r"\b(?:leerkarton|leere?\s+ovp|nur\s+verpackung)\b", t):
        return "accessory/mount/PSU/empty box only"
    if (re.search(r"\bnetz(?:teil|gerät)\w*|\btrafo\b|transformator|power\s?supply", title)
            and not re.search(r"\b(?:mit|inkl\.?|inklusive|samt|\+)\s*(?:original[- ]?)?netz(?:teil|gerät)\w*", title)):
        return "power supply only"
    if kind == "Bridge" and HUE_V1_BRIDGE.search(t):
        return "Hue Bridge v1 (EOL)"
    return None


def hue_shortlist(ads, n):
    """Interleave: switches/dimmers/sensors (Dimmer V2 first!), colour bulb deals, lamps/strips/Play, and bundles.
    Standalone Bridges stay out unless needed to fill n (most setups already have one)."""
    ok = [a for a in ads if not a.get("junk")]
    controls = sorted((a for a in ok if a.get("kind") in ("Dimmer V2", "Switch", "Sensor", "Dimmer")),
                      key=lambda a: (0 if a["kind"] == "Dimmer V2" else 1, -a["best"], a["price"]))
    color_bulbs = sorted((a for a in ok if a.get("kind") == "Bulb" and "Color" in (a.get("spec") or "")),
                         key=lambda a: (a["price"] / max(a.get("qty_n", 1), 1), a["price"]))
    lamps_strips = sorted((a for a in ok if a.get("kind") in ("Lamp", "Strip", "Play/Sync")
                           and "Extension only" not in (a.get("spec") or "")),
                          key=lambda a: -a["best"])
    bundles = sorted((a for a in ok if a.get("kind") == "Bundle" or (a.get("qty_n", 1) >= 3 and a.get("kind") != "Bridge")),
                     key=lambda a: -a["best"])
    other_no_bridge = sorted((a for a in ok if a.get("kind") != "Bridge"), key=lambda a: -a["best"])
    bridges = sorted((a for a in ok if a.get("kind") == "Bridge"), key=lambda a: a["price"])
    k = max(n // 8, 1)
    full = [controls, color_bulbs, lamps_strips, bundles, other_no_bridge, bridges]
    return interleave_buckets([controls[:3 * k], color_bulbs[:2 * k], lamps_strips[:2 * k], bundles[:k]], full, n)


CATEGORY = {                                                  # willhaben category a profile's ads belong in: id, URL path
    "laptop": (LAPTOP_CAT, "computer-tablets/notebooks-5831"),
    "pc": (PC_CAT, "computer-tablets/pcs-5833"),
}
PROFILES = {
    "laptop": (laptop, laptop_shortlist),
    "pc": (pc, pc_shortlist),
    "server": (server, server_shortlist),
    "hue": (hue, hue_shortlist),
}
FIELDS = {
    "laptop": ["gpu", "cpu", "ram", "hz"],
    "pc": ["gpu", "cpu", "ram", "vram"],
    "server": ["form", "cpu", "ram", "bays"],
    "hue": ["kind", "spec", "qty"],
}


BUILTIN = frozenset(PROFILES)


# ---- templates: profiles as data -----------------------------------------------------------------------------

TEMPLATE_DIRS = ([os.path.join(os.path.dirname(os.path.realpath(__file__)), "templates"),
                  os.path.join(os.path.expanduser(os.environ.get("WH_CONFIG", "~/.config/wh")), "templates")]
                 + [os.path.expanduser(d) for d in os.environ.get("WH_TEMPLATES", "").split(os.pathsep) if d])
TEMPLATES = {}                                                # name -> parsed template
TEMPLATE_ERRORS = {}                                          # path -> what's wrong (the template is skipped)
SORT_KEYS = ("score", "below_new", "price", "published")
DEFAULT_SORT = ["-score", "-below_new", "price"]


def _rx(where, pattern):
    try:
        return re.compile(pattern, re.I)
    except (re.error, TypeError) as e:
        raise ValueError("%s: bad pattern %r (%s)" % (where, pattern, e))


def parse_template(name, data):
    """Check a template's TOML data and compile its patterns; raises ValueError saying what's wrong."""
    unknown = set(data) - {"about", "category", "junk", "require", "field", "shortlist"}
    if unknown:
        raise ValueError("unknown keys: %s" % ", ".join(sorted(unknown)))
    rules = []
    for kind in ("junk", "require"):
        for i, r in enumerate(data.get(kind, []), 1):
            where = "[[%s]] #%d" % (kind, i)
            if set(r) - {"reason", "title", "text", "unless"} or not r.get("reason") \
                    or not (r.get("title") or r.get("text")) or (kind == "require" and r.get("unless")):
                raise ValueError("%s: needs `reason` and `title` and/or `text`%s" % (
                    where, ", optional `unless`" if kind == "junk" else " (no `unless`)"))
            rules.append(dict(kind=kind, reason=r["reason"],
                              **{k: _rx(where, r[k]) if r.get(k) else None for k in ("title", "text", "unless")}))
    fields = []
    for i, f in enumerate(data.get("field", []), 1):
        where = "[[field]] %s" % f.get("name", "#%d" % i)
        if not f.get("name") or not f.get("values") or f.get("in", "text") not in ("title", "text") \
                or set(f) - {"name", "in", "values"}:
            raise ValueError("%s: needs `name` and `values`, optional `in` (title or text)" % where)
        values = []
        for v in f["values"]:
            if not isinstance(v, dict) or "match" not in v or set(v) - {"match", "value", "score", "new"}:
                raise ValueError("%s: each value is { match = '…', value = '…', score = N, new = €N }" % where)
            values.append(dict(match=_rx(where, v["match"]), value=v.get("value"),
                               score=float(v.get("score", 0)), new=float(v["new"]) if v.get("new") else None))
        fields.append(dict(name=f["name"], where=f.get("in", "text"), values=values))
    sl = data.get("shortlist", {})
    sort = sl.get("sort", DEFAULT_SORT)
    if set(sl) - {"min_score", "sort"} or any(k.lstrip("-") not in SORT_KEYS for k in sort):
        raise ValueError("[shortlist]: `min_score = N` and `sort` from %s (`-` = highest first)" % ", ".join(SORT_KEYS))
    category = None
    if data.get("category"):
        m = re.search(r"-(\d+)$", data["category"].strip("/"))
        if not m:
            raise ValueError("category must end in willhaben's id, e.g. motorradbekleidung/handschuhe-6363")
        category = (m.group(1), data["category"].strip("/"))
    columns = [f["name"] for f in fields] + (["vs_new"] if any(v["new"] for f in fields for v in f["values"]) else [])
    return dict(name=name, about=data.get("about", ""), category=category, rules=rules, fields=fields,
                columns=columns, min_score=sl.get("min_score"), sort=sort)


def template_annotate(tpl, ad):
    """Fill the template's fields, `score`, `below_new`, `vs_new`; return a junk reason or None."""
    title = strip_swap(ad.get("title", "").lower())
    t = strip_swap(text(ad))
    score, new = 0.0, None
    for f in tpl["fields"]:
        ad[f["name"]] = None
        for v in f["values"]:
            m = v["match"].search(title if f["where"] == "title" else t)
            if m:
                ad[f["name"]] = m.expand(v["value"]) if v["value"] else m.group(0)
                score += v["score"]
                new = new or v["new"]
                break
    price = ad.get("price")
    ad["score"] = score
    ad["below_new"] = round((new - price) / new, 3) if new and price else None
    ad["vs_new"] = "new €%g (%+d %%)" % (new, round(-100 * ad["below_new"])) if ad["below_new"] is not None else None
    for r in tpl["rules"]:
        hit = all(rx.search(s) for rx, s in ((r["title"], title), (r["text"], t)) if rx)
        if r["kind"] == "junk" and hit and not (r["unless"] and r["unless"].search(t)):
            return r["reason"]
        if r["kind"] == "require" and not hit:
            return r["reason"]
    return None


def template_shortlist(tpl, ads, n):
    ranked = [a for a in ads if not a.get("junk")
              and (tpl["min_score"] is None or a.get("score", 0) >= tpl["min_score"])]
    for k in reversed(tpl["sort"]):                           # stable sorts, last key first; missing values go last
        f, desc = k.lstrip("-"), k.startswith("-")
        ranked.sort(key=lambda a: ((a.get(f) is not None) if desc else (a.get(f) is None),
                                   a.get(f) if a.get(f) is not None else 0), reverse=desc)
    return interleave_buckets([ranked], [ranked], n)          # same ranking, minus reposts of one ad


def load_templates(dirs=None):
    """(Re)load every *.toml in the template dirs into PROFILES, FIELDS and CATEGORY. A later dir overrides an
    earlier one; a broken template is skipped and listed in TEMPLATE_ERRORS."""
    for name in TEMPLATES:
        for table in (PROFILES, FIELDS, CATEGORY):
            table.pop(name, None)
    TEMPLATES.clear()
    TEMPLATE_ERRORS.clear()
    for d in TEMPLATE_DIRS if dirs is None else dirs:
        for path in sorted(glob.glob(os.path.join(d, "*.toml"))):
            name = os.path.basename(path)[:-5]
            try:
                if name in BUILTIN:
                    raise ValueError("'%s' is a built-in profile; pick another file name" % name)
                with open(path, "rb") as fh:
                    tpl = parse_template(name, tomllib.load(fh))
            except (ValueError, tomllib.TOMLDecodeError, OSError) as e:
                TEMPLATE_ERRORS[path] = str(e)
                continue
            tpl["path"] = path
            TEMPLATES[name] = tpl
            PROFILES[name] = (lambda ad, tpl=tpl: template_annotate(tpl, ad),
                              lambda ads, n, tpl=tpl: template_shortlist(tpl, ads, n))
            FIELDS[name] = tpl["columns"]
            if tpl["category"]:
                CATEGORY[name] = tpl["category"]
            else:
                CATEGORY.pop(name, None)


load_templates()


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
