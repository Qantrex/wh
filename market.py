"""Market value: what an item sells for on willhaben, and which ads sit clearly below it.

A *kind* (ram, gpu, tv, phone …) knows its willhaben categories and turns an ad into specs plus a few *keys*, from
the most specific (same model and variant) to the loosest (same class of item). The market value of an ad is the
robust median price of the other ads with the same key (ads online now and those seen in the last VALUE_DAYS days),
taken at the most specific key that has enough ads from different sellers. A deal is an ad clearly below that value.

Everything here is pure Python on ad dicts (no network, no database): `wh` fetches, stores and calls it.
"""
import re
import statistics
from datetime import datetime, timezone

import profiles

VALUE_DAYS = 90            # ads seen within this many days count towards a market value
MIN_SELLERS = 3            # fewer sellers than this with the same key: no value at that key
TOO_GOOD = 0.55            # this far below value: flag it as "too good to be true?" instead of a plain deal
CONF_WEIGHT = {"high": 1.0, "medium": 0.8, "low": 0.5}
COND = {"22": "new", "2546": "like new", "23": "used", "24": "defect", "5013256": "refurbished", "2539": "display"}

# ---- willhaben's filter values ----------------------------------------------------------------------------------


def tattrs(ad):
    """'[21;23, 2535;2537]' (categorytreeattributeids) → {'21': {'23'}, '2535': {'2537'}}."""
    out = {}
    for g, v in re.findall(r"(\d+);(\d+)", ad.get("tattrs") or ""):
        out.setdefault(g, set()).add(v)
    return out


def condition(ad):
    """new, like new, used, refurbished, display or defect, from willhaben's Zustand field; None if not set."""
    for v in tattrs(ad).get("21", ()):
        return COND.get(v)
    return None


def ships(ad):
    """True if the seller offers shipping (Übergabe: Versand) or PayLivery."""
    return "2537" in tattrs(ad).get("2535", ()) or bool(ad.get("p2p"))


def in_cats(ad, ids):
    cats = re.findall(r"\d+", str(ad.get("cats") or ""))
    return any(i in cats for i in ids)


def low_title(ad):
    return profiles.strip_swap(str(ad.get("title", "")).lower().replace("–", "-"))


def full_text(ad):
    return profiles.strip_swap(profiles.text(ad))


def first(rx, *texts, group=1):
    for t in texts:
        m = re.search(rx, t)
        if m:
            return m.group(group) if group is not None else m
    return None


def head(title):
    """The title without what comes with the item: 'ps5 slim mit 2 controllern' → 'ps5 slim'. An accessory word in the
    head means the ad is for the accessory ('pro controller für switch'), in the tail it's an extra."""
    t = re.split(r"\s(?:\+|mit|inkl\.?|inklusive|samt|plus|und|&|incl\.?|sowie|zzgl\.?)\s|\s\+|\+\s|[,;|(!]|\s-\s|\s/\s",
                 title, maxsplit=1)[0]
    return re.sub(r"\b\d+\s*(?:x\s*)?(?:spiele|games|controller\w*|joy-?cons?)\b", " ", t)   # "ps4 2 controller"


URGENT = re.compile(r"notverkauf|muss\s+(?:schnell\s+|dringend\s+|bis\s+\S+\s+)?weg|schnell\s+weg|dringend|"
                    r"umzug\w*|übersiedl\w*|auswander\w*|wohnungsauflösung|haushaltsauflösung|räumungsverkauf|"
                    r"schnellentschlossen\w*|abholung\s+(?:nur\s+)?(?:heute|morgen)|nur\s+(?:noch\s+)?(?:heute|bis)")


def urgent(ad):
    """'Notverkauf', 'muss weg', 'Umzug' …: a seller who wants it gone soon. The word that says so, or None."""
    m = URGENT.search(full_text(ad))
    return m.group(0) if m else None


def inches(t, lo=10, hi=100):
    """Screen size in inches from '55 zoll', '55"', '139 cm', '55-zoll', '65inch'."""
    for m in re.finditer(r"(?<![\d.,])(\d{2,3}(?:[.,]\d)?)\s*(?:-\s*)?(zoll|\"|''|”|“|inch|in\b|'|cm\b)", t):
        v = float(m.group(1).replace(",", "."))
        if m.group(2) == "cm":
            v = v / 2.54
        if lo <= v <= hi:
            return round(v)
    return None


def norm(s):
    return re.sub(r"[^a-z0-9+]+", " ", s.lower()).strip()


KINDS = {}


def kind(name, about, cats, keys, fields, words, defaults=None):
    """Register an extractor: cats are willhaben category paths (the id at the end counts), keys the spec fields
    that make two ads the same item (most specific first), fields what to show, words a regex that recognises the
    kind in a query. The function returns a specs dict, or a reason string when the ad isn't this kind of item."""
    def reg(fn):
        KINDS[name] = dict(name=name, about=about, cats=cats, ids=[re.search(r"(\d+)$", c).group(1) for c in cats],
                           keys=keys, fields=fields, words=re.compile(words, re.I), extract=fn,
                           defaults=defaults or {})
        return fn
    return reg


# ---- PC parts ---------------------------------------------------------------------------------------------------

RAM_SIZES = {1, 2, 4, 8, 12, 16, 24, 32, 48, 64, 96, 128, 256}


def ram_kit(t):
    """(modules, GB per module) from '2x16gb', '16gb x 2', '32gb (2x16gb)', '4 stk 8gb', '2 x 8 gb'."""
    pats = [(r"(\d)\s*[x×*]\s*(\d{1,3})\s*gb", 1, 2), (r"(\d{1,3})\s*gb\s*[x×*]\s*(\d)\b", 2, 1),
            (r"(\d)\s*(?:stk\.?|stück|riegel|module?|sticks?)\s*(?:à|a|je|zu|mit|x)?\s*(\d{1,3})\s*gb", 1, 2),
            (r"(\d{1,3})\s*gb\s*(?:riegel|module?)?\s*\(?\s*(\d)\s*(?:stk|stück)", 2, 1)]
    for rx, ni, si in pats:
        for m in re.finditer(rx, t):
            n, s = int(m.group(ni)), int(m.group(si))
            if 1 <= n <= 8 and s in RAM_SIZES:
                return n, s
    return None


RAM_SPEEDS = (400, 533, 667, 800, 1066, 1333, 1600, 1866, 2133, 2400, 2666, 2933, 3000, 3200, 3466, 3600, 3733, 4000,
              4266, 4400, 4800, 5200, 5600, 6000, 6400, 6800, 7200, 8000)


def ram_form(t, strong_only=False):
    """sodimm, server (ECC/registered) or dimm, from what the text says; None if it doesn't say. A description is only
    trusted on strong words: "passt auch in Laptops" or "aus meinem Server" don't make a desktop kit something else."""
    if re.search(r"\b(?:ecc|registered|rdimm|lrdimm)\b|pc[2-5]l?-\d{4,5}[a-z]?-?[re]\b" + ("" if strong_only else
                 r"|\bserver|\breg\b"), t):
        return "server"
    if re.search(r"so[- ]?dimm|sodimm|\bsodim|260[- ]?pin|204[- ]?pin|pc[2-5]l?-\d{4,5}[a-z]?-?s\b" + ("" if strong_only
                 else r"|notebook|laptop|\bmac\s?book|\bimac\b"), t):
        return "sodimm"
    if re.search(r"\bu?dimm\b|desktop|pc[2-5]l?-\d{4,5}[a-z]?-?u\b", t):
        return "dimm"
    return None


@kind("ram", "RAM modules and kits", ["pc-komponenten/ram-speicher-arbeitsspeicher-5887"],
      keys=[("gen", "form", "kit", "speed"), ("gen", "form", "kit"), ("gen", "form", "total")],
      fields=["gen", "form", "kit", "speed"], words=r"\b(?:ddr[2-5]|ram|arbeitsspeicher|so-?dimm|dimm)\b",
      defaults={"form": "dimm"})
def ram(ad):
    title, t = low_title(ad), full_text(ad)
    if re.search(r"\b(?:mainboard|motherboard|cpu|prozessor|ryzen|core i[3579]|i[3579]-\d|laptop|notebook|"
                 r"gaming[- ]?pc|komplett|bundle|aufrüst\w*)\b", title):
        return "bundle or not RAM"
    gen = first(r"\b(ddr[2-5])l?\b", title, t)
    if not gen:
        pc = first(r"\bpc([2-5])l?-\d{4,5}", title, t)
        gen = "ddr%s" % pc if pc else None
    form = ram_form(title) or ram_form(t, strong_only=True) or "dimm"
    kit = ram_kit(title) or ram_kit(t)
    total = kit[0] * kit[1] if kit else None
    if not total:
        g = first(r"\b(\d{1,3})\s*gb\b", title)
        total = int(g) if g and int(g) in RAM_SIZES else None
    sp = first(r"\b(\d{4})\s*(?:mhz|mt/?s)\b", title, t) or first(r"ddr[2-5]l?[- ]?(\d{4})\b", title, t)
    if not sp:
        pc = first(r"\bpc[2-5]l?-(\d{4,5})", title, t)
        sp = str(min(RAM_SPEEDS, key=lambda v: abs(v - int(pc) / 8))) if pc else None
    speed = int(sp) if sp and 400 <= int(sp) <= 9000 else None
    return dict(gen=gen, form=form, kit="%dx%d" % kit if kit else None, total=total, speed=speed)


NV_MODELS = {"1030", "1050", "1060", "1070", "1080", "1630", "1650", "1660", "2060", "2070", "2080", "3050", "3060",
             "3070", "3080", "3090", "4060", "4070", "4080", "4090", "5050", "5060", "5070", "5080", "5090", "970",
             "980", "960", "950", "750", "titan"}
VRAM_SPLIT = {"rtx 3060": (8, 12), "gtx 1060": (3, 6), "rtx 4060 ti": (8, 16), "rtx 3080": (10, 12),
              "rtx 2060": (6, 12), "rx 580": (4, 8), "rx 570": (4, 8), "rx 480": (4, 8), "rx 470": (4, 8),
              "gtx 1050": (2, 3), "rx 6500 xt": (4, 8), "arc a770": (8, 16), "rtx 5060 ti": (8, 16),
              "rx 9060 xt": (8, 16), "rx 7600 xt": (8, 16)}


def gpu_model(t):
    m = re.search(r"\b(?:rtx|gtx|geforce)\s*-?\s*(\d{3,4})\s*(ti\s*super|ti|super)?\b", t)
    if m and (m.group(1) in NV_MODELS or re.fullmatch(r"[2-9][0-9]0|[1-9][0-9][1-9]0", m.group(1))):
        pre = "gtx" if int(m.group(1)) < 2000 and m.group(1) not in ("1630",) else "rtx"
        return " ".join(x for x in (pre, m.group(1), (m.group(2) or "").replace(" ", "")) if x).replace("tisuper", "ti super")
    m = re.search(r"\b(?:radeon\s*)?rx\s*-?\s*(\d{3,4})\s*(xtx|xt|gre)?\b", t)
    if m:
        return " ".join(x for x in ("rx", m.group(1), m.group(2)) if x)
    m = re.search(r"\b(?:radeon\s*)?rx\s*vega\s*(56|64)|\bvega\s*(56|64)\b", t)
    if m:
        return "rx vega " + (m.group(1) or m.group(2))
    m = re.search(r"\b(?:radeon\s*)?(r[579])\s*-?\s*(\d{3}x?)\b|\bradeon\s*(hd)\s*(\d{4})\b|\bhd\s*(\d{4})\b", t)
    if m:
        return ("radeon %s %s" % (m.group(1), m.group(2)) if m.group(1) else "radeon hd %s" % (m.group(4) or m.group(5)))
    m = re.search(r"\bquadro\s*([a-z]{0,3}\s?\d{3,4})\b|\brtx\s*(a\d{4})\b", t)
    if m:
        return "quadro " + (m.group(1) or m.group(2)).replace(" ", "")
    m = re.search(r"\barc\s*([ab]\d{3})\b", t)
    if m:
        return "arc " + m.group(1)
    m = re.search(r"\b(\d{4})\s*(ti|super)?\b", t)
    if m and m.group(1) in NV_MODELS and int(m.group(1)) >= 1050:
        pre = "gtx" if int(m.group(1)) < 2000 else "rtx"
        return " ".join(x for x in (pre, m.group(1), m.group(2)) if x)
    return None


@kind("gpu", "graphics cards", ["pc-komponenten/grafikkarten-5882"], keys=[("model", "vram"), ("model",)],
      fields=["model", "vram"], words=r"\b(?:rtx|gtx|rx\s*\d{3,4}|grafikkarte|gpu|radeon|geforce|arc\s*[ab]\d)")
def gpu(ad):
    title, t = low_title(ad), full_text(ad)
    if re.search(r"\b(?:laptop|notebook|gaming[- ]?pc|komplett[- ]?pc|desktop|tower|pc[- ]?system)\b", title):
        return "a computer, not a card"
    if re.search(r"^(?:neue?r?s?\s+)?(?:kühler|wasserkühler|waterblock|backplate|riser|halterung|lüfter|fan|kabel|"
                 r"stütze|support|block)\b", title):
        return "part, not a card"
    model = gpu_model(title) or gpu_model(t)
    vram = None
    if model in VRAM_SPLIT:
        v = first(r"\b(\d{1,2})\s*gb\b", title) or first(r"\b(\d{1,2})\s*gb\b", t)
        vram = int(v) if v and int(v) in VRAM_SPLIT[model] else None
    return dict(model=model, vram=vram if model in VRAM_SPLIT else "-")


def cpu_model(t):
    m = re.search(r"\bryzen\s*([3579])\s*[/-]?\s*(?:pro\s*)?(\d{4})\s*(x3d|xt|x|ge|g|f)?\b", t)
    if m:
        return "ryzen %s %s%s" % (m.group(1), m.group(2), m.group(3) or "")
    m = re.search(r"\b(?:core\s*)?ultra\s*([579])\s*-?\s*(\d{3})([a-z]{0,2})\b", t)
    if m:
        return "core ultra %s %s%s" % m.groups()
    m = re.search(r"\b(?:core\s*)?i([3579])\s*-?\s*(\d{4,5})([a-z]{0,2})\b", t)
    if m:
        return "i%s-%s%s" % m.groups()
    m = re.search(r"\bxeon\s*(?:silver|gold|bronze|platinum)?\s*([ew]?-?\d{4,5}[a-z]?(?:\s*v\d)?)\b", t)
    if m:
        return "xeon " + m.group(1).replace(" ", "")
    m = re.search(r"\b([3-9]\d{3})(x3d|x)\b", t)
    if m:
        return "ryzen ? %s%s" % m.groups()
    m = re.search(r"\bcore\s*2\s*(?:duo|quad|extreme)?\s*([qetx]\d{4})\b", t)
    if m:
        return "core2 " + m.group(1)
    m = re.search(r"\b(fx)\s*-?\s*(\d{4})\b|\b(phenom\s*ii\s*x\d|athlon\s*(?:ii\s*)?(?:x\d|64\s*x2)?)\s*(\d{3,4}e?)\b", t)
    if m:
        return ("amd fx-%s" % m.group(2)) if m.group(1) else norm("%s %s" % (m.group(3), m.group(4)))
    return None


@kind("cpu", "processors", ["pc-komponenten/cpus-prozessoren-5880"], keys=[("model",)], fields=["model"],
      words=r"\b(?:ryzen|core\s*i[3579]|i[3579]-\d|core\s*ultra|xeon|prozessor|cpu)\b")
def cpu(ad):
    title, t = low_title(ad), full_text(ad)
    if re.search(r"\b(?:mainboard|motherboard|board|bundle|aufrüst\w*|kombi|laptop|notebook|gaming[- ]?pc)\b", title):
        return "bundle or not a CPU"
    if re.search(r"^(?:neue?r?s?\s+)?(?:kühler|cooler|lüfter|wärmeleitpaste|halterung)\b", title):
        return "part, not a CPU"
    return dict(model=cpu_model(title) or cpu_model(t))


CHIPSETS = (r"970|990fx|990x|a75|a88x|a68h|h67|h77|q87|h55|p55|x58|p45|p43|g41|g31|x38|x48|a320|a520|a620|b350|b450|b550|b650e?|b850|x370|x470|x570|x670e?|x870e?|b760|b660|h610|h510|h470|h410|"
            r"z390|z370|b360|b365|h370|h310|z490|z590|z690|z790|z890|b460|b560|h570|h670|h770|b860|x99|x299|z97|z87|"
            r"h81|b85|h97|h87|b75|z77|z68|p67|h61|z170|z270|b150|b250|h110|h170|h270")


@kind("mainboard", "mainboards", ["pc-komponenten/mainboards-5885"], keys=[("chipset", "form"), ("chipset",)],
      fields=["chipset", "form"], words=r"\b(?:mainboard|motherboard)\b")
def mainboard(ad):
    title, t = low_title(ad), full_text(ad)
    if re.search(r"\b(?:ryzen|core\s*i[3579]|i[3579]-\d{4}|prozessor|cpu|bundle|aufrüst\w*|kombi|gaming[- ]?pc)\b",
                 title):
        return "bundle with a CPU"
    chip = first(r"(?:^|[^a-z0-9]|\bp\d|\bga-|\bma)(%s)(?![0-9])" % CHIPSETS, title, t)
    form = ("itx" if re.search(r"\bmini[- ]?itx|\bitx\b|-i\b", t) else
            "matx" if re.search(r"micro[- ]?atx|\bm-?atx|\bmatx|\bμatx|(?:%s)m\b|-m\b" % CHIPSETS, t) else
            "atx" if re.search(r"\b(?:e-?)?atx\b", t) else None)
    return dict(chipset=chip, form=form)


@kind("psu", "power supplies", ["pc-komponenten/netzteile-5886"], keys=[("watt", "rating"), ("watt",)],
      fields=["watt", "rating"], words=r"\b(?:netzteil|psu|power supply)\b")
def psu(ad):
    title, t = low_title(ad), full_text(ad)
    if re.search(r"\b(?:laptop|notebook|ladegerät|ladekabel|netzadapter|adapter|usb|monitor|drucker|dock\w*|thinkpad|"
                 r"ideapad|lenovo|braun|12v|19v|24v)\b", title):
        return "not a PC power supply"
    w = first(r"\b(\d{3,4})\s*(?:w|watt)\b", title, t)
    w = int(w) if w and 250 <= int(w) <= 2000 else None
    rating = first(r"80\s*\+?\s*(?:plus)?\s*(titanium|platinum|gold|silver|bronze)", t) or (
        "white" if re.search(r"80\s*\+|80\s*plus", t) else None)
    return dict(watt=int(round(w / 50.0) * 50) if w else None, rating=rating)


def capacity_gb(t):
    m = re.search(r"\b(\d{1,2}(?:[.,]\d{1,2})?)\s*tb\b|\b(\d{2,4})\s*gb\b", t)
    if not m:
        return None
    return int(float(m.group(1).replace(",", ".")) * 1000) if m.group(1) else int(m.group(2))


@kind("disk", "SSDs and hard drives", ["festplatten-speicherkarten/interne-festplatten-5869"],
      keys=[("type", "capacity", "model"), ("type", "capacity")], fields=["type", "capacity", "model"],
      words=r"\b(?:ssd|nvme|hdd|festplatte|m\.2)\b")
def disk(ad):
    title, t = low_title(ad), full_text(ad)
    if re.search(r"\b(\d{1,2})\s*(?:x|stk\.?|stück)\s*\d", title):
        return "several drives"
    if re.search(r"^(?:neue?r?s?\s+)?(?:gehäuse|adapter|kabel|einbaurahmen|caddy|kühler|heatsink)\b", title):
        return "accessory, not a drive"
    typ = ("nvme" if re.search(r"nvme|pcie|m\.2\s*2280\s*nvme", t) else
           "m.2 sata" if re.search(r"m\.2", t) and re.search(r"sata", t) else
           "ssd" if re.search(r"\bssd\b", t) else
           "hdd" if re.search(r"\bhdd\b|festplatte|rpm|u/min|7200|5400|3[.,]5\s*(?:zoll|\")", t) else None)
    cap = capacity_gb(title) or capacity_gb(t)
    model = first(r"\b(samsung\s*(?:9[89]0|8[67]0|970|860|870|990)\s*(?:evo\s*plus|evo|pro|qvo)?|wd\s*(?:black|blue|red|"
                  r"green)\s*(?:sn\d{3,4})?|crucial\s*(?:mx|bx|p|t)\d{3}|kingston\s*(?:kc|nv|a|fury)\d{0,4}|"
                  r"seagate\s*(?:ironwolf|barracuda|exos|firecuda)\w*|toshiba\s*(?:n300|x300|mg\d{2}))", title)
    return dict(type=typ, capacity=cap, model=norm(model) if model else None)


# ---- screens ----------------------------------------------------------------------------------------------------

# Parts sold in the TV and monitor categories, and screens sold for parts. Checked on the title and description.
SCREEN_PARTS = (r"ersatzteil|\bplatine|\bt-?con\b|netzkabel|rückwand|hintergrundbeleuchtung|\bbacklight\b|"
                r"led[- ]?(?:streifen|leiste|leisten|bord|board|strips?)|\btransceiver|\bmodul\b|komplettchassis|"
                r"display\s*-?\s*(?:bruch|riss|gebrochen|beschädigt|kaputt)|displaybruch|bildschirm\s*(?:gebrochen|kaputt)|"
                r"panel\s*(?:defekt|kaputt|gebrochen|bruch)|\bbn\d{2}-\d{4,}|\beax\d{6,}|\bebu\d{6,}|"
                r"^(?:original\s+)?(?:samsung|lg|sony|philips|panasonic)?\s*(?:netzteil|mainboard|board|fernbedienung|"
                r"standfu(?:ß|ss)|füße|wandhalterung)\b|\b(?:netzteil|mainboard|board|fernbedienung|standfu(?:ß|ss)|"
                r"füße)\s+(?:für|fuer|von|eines|aus)\b|\bohne\s+(?:display|panel|bildschirm)\b|fernsehtisch|tv-?(?:möbel|"
                r"schrank|tisch|board|halterung|wandhalterung)|lowboard|sideboard")


MONITOR_SIZE = {"5007342": 14, "5007343": 15, "5007344": 17, "5007345": 19, "5007346": 22, "5007347": 24,
                "5007348": 25, "5007349": 27, "5007350": 32}
TV_SIZE = {"7307": 28, "7308": 32, "7309": 38, "7310": 40, "7311": 43, "7312": 46, "7313": 48, "7314": 50,
           "7315": 52, "7316": 55, "7317": 60, "7318": 65}


def resolution(t):
    if re.search(r"\b8k\b|7680", t):
        return "8k"
    if re.search(r"\b4k\b|\buhd\b|ultra[- ]?hd|2160p?|3840", t):
        return "4k"
    if re.search(r"3440|uwqhd|ultra[- ]?wide\s*qhd", t):
        return "uwqhd"
    if re.search(r"\bw?qhd\b|1440p?|2560\s*x\s*1440|\b2k\b", t):
        return "1440p"
    if re.search(r"full[- ]?hd|\bfhd\b|1080p?|1920\s*x\s*1080", t):
        return "1080p"
    if re.search(r"hd[- ]?ready|720p|1366", t):
        return "720p"
    return None


def hz_bucket(t):
    hz = [int(x) for x in re.findall(r"\b(\d{2,3})\s*hz\b", t) if 50 <= int(x) <= 540]
    if not hz:
        return None
    h = max(hz)
    return 60 if h <= 75 else 120 if h <= 120 else 144 if h <= 170 else 180 if h <= 200 else 240 if h <= 280 else 360


BRANDS_SCREEN = (r"samsung|lg|sony|philips|panasonic|tcl|hisense|grundig|toshiba|sharp|loewe|xiaomi|medion|telefunken|"
                 r"thomson|metz|jvc|blaupunkt|hitachi|chiq|nokia|dell|asus|acer|aoc|benq|msi|iiyama|viewsonic|eizo|hp|"
                 r"lenovo|gigabyte|aorus|fujitsu|apple|alienware|huawei|nec")


@kind("monitor", "computer monitors", ["drucker-monitore-lautsprecher/monitore-5849"],
      keys=[("brand", "model"), ("size", "res", "hz", "panel"), ("size", "res", "hz"), ("size", "res")],
      fields=["brand", "model", "size", "res", "hz", "panel"], words=r"\b(?:monitor|bildschirm|display)\b")
def monitor(ad):
    title, t = low_title(ad), full_text(ad)
    if re.search(r"^(?:neue?r?s?\s+)?(?:halterung|arm|monitorarm|standfuß|kabel|netzteil|adapter)\b", title):
        return "accessory, not a monitor"
    if re.search(r"\b(?:\d)\s*(?:x|stk\.?|stück)\s*(?:monitor|bildschirm|\w+\s+\d{2})", title):
        return "several monitors"
    if re.search(SCREEN_PARTS, t):
        return "part, or a monitor sold for parts"
    size = inches(title, 13, 57) or inches(t, 13, 57)
    if not size:
        for v in tattrs(ad).get("5807", ()):
            size = MONITOR_SIZE.get(v)
    brand = first(r"\b(%s)\b" % BRANDS_SCREEN, title)
    model = None
    if brand:
        m = re.search(r"\b%s\b\s*(?:ultrasharp|odyssey|ultragear|predator|nitro|rog\s*(?:strix|swift)?|tuf|"
                      r"proart|optix|mag|mpg|zowie|gaming|curved|monitor)?\s*([a-z]{0,4}\s?-?\d{2,4}[a-z0-9-]{0,8})"
                      % re.escape(brand), title)
        model = norm(m.group(1)).replace(" ", "") if m else None
        if model and not (re.search(r"[a-z]", model) and re.search(r"\d", model) and len(model) >= 4):
            model = None
    panel = first(r"\b(oled|ips|va|tn|mini[- ]?led)\b", t)
    return dict(brand=brand, model=model, size=size, res=resolution(t), hz=hz_bucket(t),
                panel=panel.replace("-", "").replace(" ", "") if panel else None)


TV_YEAR_SAMSUNG = {"h": 2014, "j": 2015, "k": 2016, "m": 2017, "n": 2018, "r": 2019, "t": 2020, "a": 2021,
                   "b": 2022, "c": 2023, "d": 2024, "f": 2025}
TV_YEAR_SONY = {"c": 2015, "d": 2016, "e": 2017, "f": 2018, "g": 2019, "h": 2020, "j": 2021, "k": 2022, "l": 2023,
                "m": 2024}
TV_YEAR_LG_OLED = {"6": 2016, "7": 2017, "8": 2018, "9": 2019, "x": 2020, "1": 2021, "2": 2022, "3": 2023,
                   "4": 2024, "5": 2025}
TV_YEAR_LG_LED = {"uh": 2016, "uj": 2017, "uk": 2018, "um": 2019, "un": 2020, "up": 2021, "uq": 2022, "ur": 2023,
                  "ut": 2024, "ua": 2025, "lh": 2016, "lj": 2017, "lk": 2018, "lm": 2019}


def tv_code(t):
    """(brand, series, size, year, panel, res) from a TV model number, as far as it tells; None if none found."""
    m = re.search(r"\b(?:ue|gu|qe|gq|qn|un)\s*-?\s*(\d{2})\s*(q\d{2,3}[a-z]|qn\d{2,3}[a-z]|s9\d[a-z]|s8\d[a-z]|"
                  r"ls\d{2}[a-z]|[a-z]{2}\d{4})", t)
    if m:
        s = m.group(2)
        y = TV_YEAR_SAMSUNG.get(s[-1] if s[0] in "qs" or s.startswith("ls") else s[0])
        panel = "oled" if re.match(r"s9|s8", s) else "qled" if s[0] == "q" or s.startswith("ls") else "led"
        return "samsung", s, int(m.group(1)), y, panel, "4k"
    m = re.search(r"\boled\s*-?(\d{2})\s*([abcegwzr])([6-9x1-5])", t)
    if m:
        return "lg", "oled " + m.group(2) + m.group(3), int(m.group(1)), TV_YEAR_LG_OLED.get(m.group(3)), "oled", "4k"
    m = re.search(r"\b(\d{2})\s*(nano\d{2,3}|qned\d{2,3}|u[hjkmnpqrta]\d{3,4}|l[hjkm]\d{3,4})\b", t)
    if m and re.search(r"\blg\b", t):
        s = m.group(2)
        panel = "qled" if s.startswith(("nano", "qned")) else "led"
        return "lg", s, int(m.group(1)), TV_YEAR_LG_LED.get(s[:2]), panel, "4k" if not s.startswith("l") else None
    m = re.search(r"\b(?:kd|xr|ke|kdl|fwd)\s*-?\s*(\d{2})\s*([a-z]{1,2}\d{1,4}[a-z]?)\b", t)
    if m:
        s = m.group(2)
        y = TV_YEAR_SONY.get(s[-1]) if s[-1].isalpha() else TV_YEAR_SONY.get(s[1]) if s[0] in "xa" else None
        panel = "oled" if s.startswith("a") else "led"
        return "sony", s, int(m.group(1)), y, panel, None if t.find("kdl") >= 0 else "4k"
    m = re.search(r"\b(\d{2})\s*(pus|pud|pml|oled|pfs|pfk|pht|pug|pfh|phs)\s*(\d{4})", t)
    if m:
        panel = "oled" if m.group(2) == "oled" else "led"
        res = {"pus": "4k", "pud": "4k", "pml": "4k", "oled": "4k", "pug": "4k"}.get(m.group(2), "1080p")
        return "philips", m.group(2) + m.group(3), int(m.group(1)), 2015 + int(m.group(3)[-1]), panel, res
    m = re.search(r"\btx\s*-?\s*(\d{2})\s*([a-z]{2,3}\d{3,4})", t)
    if m:
        return "panasonic", m.group(2), int(m.group(1)), None, "oled" if "z" in m.group(2)[:3] else None, None
    return None


@kind("tv", "TVs", ["fernseher/lcd-fernseher-6887", "fernseher/led-backlight-fernseher-6888"],
      keys=[("brand", "series", "size"), ("brand", "panel", "res", "size", "year"), ("panel", "res", "size", "year"),
            ("brand", "panel", "res", "size"), ("tier", "panel", "res", "size")],
      fields=["brand", "series", "size", "panel", "res", "year"], words=r"\b(?:tv|fernseher|smart\s*tv|oled\d{2})\b")
def tv(ad):
    title, t = low_title(ad), full_text(ad)
    if re.search(r"^(?:neue?r?s?\s+)?(?:wandhalterung|halterung|fernbedienung|standfuß|füße|kabel|netzteil|"
                 r"mainboard|board|panel|t-?con|backlight|led[- ]?streifen|ersatz)", title):
        return "part or accessory, not a TV"
    if re.search(r"\b(?:\d)\s*(?:x|stk\.?|stück)\s*(?:tv|fernseher)", title):
        return "several TVs"
    if re.search(SCREEN_PARTS, t):
        return "part, or a TV sold for parts"
    code = tv_code(title) or tv_code(t)
    brand, series, size, year, panel, res = code or (None,) * 6
    size = inches(title, 17, 100) or size or inches(t, 17, 100)
    if not size:
        for v in tattrs(ad).get("5807", ()):
            size = TV_SIZE.get(v)
    brand = brand or first(r"\b(%s)\b" % BRANDS_SCREEN, title)
    p = first(r"\b(oled|qd-?oled|neo\s*qled|qled|mini[- ]?led|qned|nanocell|plasma)\b", title) or (None if code else first(
        r"(?<!kein )(?<!kein\s)\b(oled|qd-?oled|neo\s*qled|qled|mini[- ]?led|qned|nanocell|plasma)\b", t))
    if p:
        panel = "oled" if "oled" in p and "qled" not in p else "plasma" if p == "plasma" else "qled"
    panel = panel or "led"
    res = resolution(t) or res
    y = first(r"(?:baujahr|bj\.?|modell(?:jahr)?|jahrgang|aus dem jahr|gekauft(?:\s+\w+){0,2})\s*:?\s*(20[0-2]\d)\b", t)
    year = year or (int(y) if y else None)
    tier = "brand" if brand in ("samsung", "lg", "sony", "philips", "panasonic", "loewe", "metz") else "budget"
    return dict(brand=brand, series=series, size=size, panel=panel, res=res, tier=tier,
                year=(year // 2 * 2) if year else None)   # two-year steps: 2020-21, 2022-23 …


# ---- phones, tablets, consoles -------------------------------------------------------------------------------

PHONE_STORAGE = {"5007645": 512, "7216": 256, "7217": 128, "7218": 64, "7219": 32, "7220": 16, "7221": 8}


def storage(ad, t, field="7215", table=PHONE_STORAGE):
    for v in tattrs(ad).get(field, ()):
        if v in table:
            return table[v]
    m = re.search(r"\b(16|32|64|128|256|512)\s*gb\b(?!\s*(?:ram|arbeitsspeicher))|\b(1|2)\s*tb\b", t)
    if m:
        return int(m.group(1)) if m.group(1) else int(m.group(2)) * 1024
    return None


PHONE_BRANDS = (r"xiaomi|redmi|poco|oneplus|honor|huawei|motorola|moto|nothing\s*phone|oppo|realme|sony\s*xperia|xperia|"
                r"nokia|fairphone|doro|emporia|vivo|zte|asus\s*zenfone|zenfone|cat|blackview|ulefone|lenovo\s*tab|"
                r"lenovo|huawei\s*mediapad|mediapad|microsoft\s*surface|surface|xiaomi\s*pad|redmi\s*pad|amazon\s*fire|"
                r"fire\s*hd")


def brand_model(t, brands):
    """'xiaomi 13 pro', 'surface go 2': a brand and the words after it up to the first one with a digit."""
    m = re.search(r"\b(%s)\b" % brands, t)
    if not m:
        return None
    words = re.findall(r"[a-z0-9][a-z0-9+-]*", t[m.end():])[:4]
    out = []
    for i, w in enumerate(words):
        if re.fullmatch(r"handy|smartphone|tablet|telefon|mit|und|in|der|farbe|neu|neuwertig|gb|tb|zoll|wifi|wlan|"
                        r"lte|5g|4g|dual|sim", w):
            break
        out.append(w)
        if re.search(r"\d", w):
            if i + 1 < len(words) and re.fullmatch(r"pro|ultra|plus|lite|max|mini|neo|fe|t|s|5g", words[i + 1]):
                out.append(words[i + 1])
            break
    if not out or not any(re.search(r"\d", w) for w in out):
        return None
    return norm("%s %s" % (m.group(1), " ".join(out)))


def phone_model(t):
    m = re.search(r"\biphone\s*(\d{1,2}|xs|xr|x|se)\s*(pro\s*max|pro|plus|max|mini|e\b)?", t)
    if m:
        gen, var = m.group(1), re.sub(r"\s+", " ", m.group(2) or "").strip()
        if gen == "se":
            gen = "se3" if re.search(r"se\s*(?:\(?\s*2022|3\.?\s*gen|3rd)", t) else (
                "se2" if re.search(r"se\s*(?:\(?\s*2020|2\.?\s*gen|2nd)", t) else "se")
        return "iphone %s%s" % (gen, " " + var if var else "")
    m = re.search(r"\b(?:galaxy\s*)?(s|a|m|note|z\s*fold|z\s*flip)\s*(\d{1,2})\s*(ultra|plus|\+|fe|lite|edge)?\b", t)
    if m and (re.search(r"galaxy|samsung", t) or m.group(1) in ("s", "note")):
        if m.group(1) in ("a", "m") and not re.search(r"galaxy|samsung", t):
            return None
        var = {"+": "plus"}.get(m.group(3), m.group(3))
        return "galaxy %s%s%s" % (m.group(1).replace(" ", ""), m.group(2), " " + var if var else "")
    m = re.search(r"\bpixel\s*(\d{1,2})\s*(pro\s*xl|pro\s*fold|pro|xl|a)?\b", t)
    if m:
        return "pixel %s%s" % (m.group(1), " " + m.group(2).replace(" ", "") if m.group(2) else "")
    return None


@kind("phone", "smartphones", ["smartphones-handys-2722"], keys=[("model", "storage"), ("model",)],
      fields=["model", "storage"], words=r"\b(?:iphone|galaxy\s*[saz]|pixel\s*\d|smartphone|handy)\b")
def phone(ad):
    title, t = low_title(ad), full_text(ad)
    if re.search(r"^(?:neue?r?s?\s+)?(?:hülle|case|cover|schutz\w*|panzerglas|display|akku|ladekabel|ladegerät|"
                 r"attrappe|dummy|rückseite|kamera|platine|tasche)\b", title):
        return "accessory or part, not a phone"
    if re.search(r"\b(?:\d)\s*(?:x|stk\.?|stück)\s*(?:iphone|handy|smartphone|galaxy)", title):
        return "several phones"
    if re.search(r"reparatur|austausch|\blcd\b|display\s*(?:tausch|wechsel|service)|akkutausch|\bservice\b|"
                 r"ankauf|wir\s+kaufen|handyshop|werkstatt", title):
        return "a repair service or buyer, not a phone"
    if re.search(r"hülle|\bcase\b|(?<!x )(?<!x)\bcover\b|panzerglas|schutzglas|schutzfolie|\bfolie|ladekabel|ladegerät|adapter|"
                 r"halterung|tasche|armband|magsafe|kameraschutz|ersatzteil|platine|backcover|attrappe|dummy|"
                 r"für\s+(?:das\s+|ein\s+)?(?:iphone|samsung|galaxy|pixel)|^(?:neue?r?s?\s+)?(?:akku|display|kabel)\b",
                 head(title)):
        return "accessory or part, not a phone"
    model = phone_model(title) or brand_model(title, PHONE_BRANDS) or phone_model(t)
    return dict(model=model, storage=storage(ad, title) or storage(ad, t))


@kind("tablet", "tablets", ["computer-tablets/tablets-5834"], keys=[("model", "storage"), ("model",)],
      fields=["model", "storage"], words=r"\b(?:ipad|tablet|galaxy\s*tab)\b")
def tablet(ad):
    title, t = low_title(ad), full_text(ad)
    if re.search(r"hülle|\bcase\b|cover|tastatur|keyboard|pencil|stift|schutz\w*|\bdisplay\b|ladekabel|"
                 r"ladegerät|halterung|tasche|für\s+(?:das\s+|ein\s+)?(?:ipad|galaxy\s*tab|tablet)", head(title)):
        return "accessory, not a tablet"
    model = None
    m = re.search(r"\bipad\s*(pro|air|mini)?\s*(?:(\d{1,2}(?:[.,]\d)?)\s*(?:zoll|\"|''|”))?\s*\(?\s*"
                  r"(?:(\d{1,2})\s*\.?\s*(?:gen|generation)|(20[12]\d)|(m[1-5]))?", title)
    if m:
        fam = m.group(1) or ""
        gen = ("gen%s" % m.group(3)) if m.group(3) else m.group(4) or m.group(5) or ""
        size = m.group(2).replace(",", ".") if m.group(2) and fam == "pro" else ""
        model = norm(" ".join(x for x in ("ipad", fam, size, gen) if x))
    m = re.search(r"\bgalaxy\s*tab\s*(s\d{1,2}|a\d{0,2})\s*(ultra|\+|plus|fe|lite)?", title)
    if m:
        model = "galaxy tab %s%s" % (m.group(1), " " + {"+": "plus"}.get(m.group(2), m.group(2)) if m.group(2) else "")
    model = model or brand_model(title, PHONE_BRANDS)
    return dict(model=model, storage=storage(ad, title, "-") or storage(ad, t, "-"))


CONSOLES = [
    (r"\bps5\s*pro|playstation\s*5\s*pro", "ps5 pro"),
    (r"\b(?:ps5|playstation\s*5)\b.*\bslim\b.*\bdigital|\b(?:ps5|playstation\s*5)\b.*\bdigital.*\bslim", "ps5 slim digital"),
    (r"\b(?:ps5|playstation\s*5)\b.*\bslim\b", "ps5 slim"),
    (r"\b(?:ps5|playstation\s*5)\b.*\bdigital", "ps5 digital"),
    (r"\b(?:ps5|playstation\s*5)\b", "ps5"),
    (r"\b(?:ps4|playstation\s*4)\s*pro\b", "ps4 pro"),
    (r"\b(?:ps4|playstation\s*4)\b.*\bslim\b", "ps4 slim"),
    (r"\b(?:ps4|playstation\s*4)\b", "ps4"),
    (r"\b(?:ps3|playstation\s*3)\b", "ps3"),
    (r"\bps\s*vita\b|playstation\s*vita", "ps vita"),
    (r"\bxbox\s*series\s*x\b", "xbox series x"),
    (r"\bxbox\s*series\s*s\b", "xbox series s"),
    (r"\bxbox\s*one\s*x\b", "xbox one x"),
    (r"\bxbox\s*one\s*s\b", "xbox one s"),
    (r"\bxbox\s*one\b", "xbox one"),
    (r"\bxbox\s*360\b", "xbox 360"),
    (r"\bswitch\s*2\b", "switch 2"),
    (r"\bswitch\b.*\boled\b|\boled\b.*\bswitch\b", "switch oled"),
    (r"\bswitch\s*lite\b", "switch lite"),
    (r"\bnintendo\s*switch\b|\bswitch\s*(?:v2|konsole)\b", "switch"),
    (r"\bsteam\s*deck\b.*\boled\b|\boled\b.*\bsteam\s*deck\b", "steam deck oled"),
    (r"\bsteam\s*deck\b", "steam deck"),
    (r"\bnew\s*(?:nintendo\s*)?3ds\s*xl\b", "new 3ds xl"),
    (r"\bnew\s*(?:nintendo\s*)?2ds\s*xl\b", "new 2ds xl"),
    (r"\b3ds\s*xl\b", "3ds xl"), (r"\b3ds\b", "3ds"), (r"\b2ds\b", "2ds"), (r"\bnintendo\s*ds\s*lite|\bds\s*lite\b", "ds lite"),
    (r"\bwii\s*u\b", "wii u"), (r"\bwii\b", "wii"), (r"\bgame\s*cube\b|\bgamecube\b", "gamecube"),
    (r"\bn64\b|nintendo\s*64", "n64"), (r"\bsnes\b|super\s*nintendo", "snes"), (r"\bnes\b", "nes"),
    (r"\bgame\s*boy\s*advance\s*sp|\bgba\s*sp\b", "gba sp"), (r"\bgame\s*boy\s*advance|\bgba\b", "gba"),
    (r"\bgame\s*boy\s*colou?r", "game boy color"), (r"\bgame\s*boy\b", "game boy"),
    (r"\bmega\s*drive\b|\bgenesis\b", "mega drive"), (r"\bdreamcast\b", "dreamcast"),
    (r"\b(?:ps2|playstation\s*2)\b", "ps2"), (r"\b(?:ps1|psx|psone|playstation\s*1)\b", "ps1"),
    (r"\brog\s*ally\s*x\b", "rog ally x"), (r"\brog\s*ally\b", "rog ally"), (r"\blegion\s*go\b", "legion go"),
]


CONSOLE_EXTRAS = (r"controller|joy-?cons?\b|gamepad|lenkrad|wheel|\bcase\b|schale|hülle|tasche|zubehör|modchip|kabel|"
                  r"\bstick\b|ladestation|charging|\bdock\b|headset|kamera|camera|\bvr\b|spiel\b|spiele\b|\bgame\b|"
                  r"\bgames\b|amiibo|figur|skin|aufkleber|cover|faceplate|lüfter|netzteil|festplatte|ssd|speicherkarte|"
                  r"tastatur|maus|fernbedienung|halterung|ständer|\bstand\b|\(ps[1-5]\)|\(switch\)|für\s+(?:die\s+)?"
                  r"(?:ps[1-5]|playstation|xbox|switch|nintendo)")


RETRO_HANDHELD_GAMES = {"gba", "gba sp", "game boy", "game boy color", "ds lite", "3ds", "3ds xl", "2ds", "new 3ds xl",
                        "new 2ds xl", "n64", "snes", "nes", "mega drive", "gamecube", "wii", "wii u", "ps1", "ps2"}


@kind("console", "game consoles", ["konsolen-2786"], keys=[("model", "edition", "bundle"), ("model", "edition"), ("model",)],
      fields=["model", "edition", "bundle"],
      words=r"\b(?:ps[1-5]|playstation|xbox|switch|steam\s*deck|konsole|wii|gameboy|game\s*boy|3ds|rog\s*ally)\b")
def console(ad):
    title, t = low_title(ad), full_text(ad)
    if re.search(r"^(?:neue?r?s?\s+)?(?:controller|joy-?con|gamepad|spiel|spiele|game|games|hülle|tasche|case|"
                 r"ladestation|dock|kabel|netzteil|lüfter|skin|headset|lenkrad|vr|camera|kamera|fernbedienung)\b", title):
        return "accessory or game, not a console"
    if re.search(r"\b(?:defekt|reparatur|ersatzteil)", title):
        return "defect"
    if re.search(r"\((?:ps[1-5]|ps\s*vita|switch|xbox[^)]{0,12}|wii\s*u?|3ds|nintendo[^)]{0,12})\)\s*$|^\s*spiele?\b", title):
        return "accessory or game, not a console"
    if re.search(CONSOLE_EXTRAS, head(title)) and not re.search(r"\bkonsole|\bconsole\b|\bsystem\b|\bhandheld\b",
                                                                 head(title)):
        return "accessory or game, not a console"
    model = next((name for rx, name in CONSOLES if re.search(rx, title)), None)
    if model in RETRO_HANDHELD_GAMES and re.search(r"\bpal\b|\bmodul\b|cartridge|\bcart\b|\bspiel|\bgame\b", title) \
            and not re.search(r"konsole|console|handheld|system|\bgerät", title):
        return "a game, not a console"
    edition = None
    if model in ("steam deck", "steam deck oled"):
        s = storage(ad, title, "-") or storage(ad, t, "-")
        edition = str(s) if s else None
    elif model and model.startswith(("ps5", "xbox series")):
        edition = "-"
    bundle = bool(re.search(r"(?:\+|inkl\.?|inklusive|mit|plus|samt)\s*(?:\d+\s*|vielen\s*|einigen\s*|mehreren\s*)?"
                            r"(?:spiele|games|spielen)\b|\b\d+\s*(?:spiele|games)\b", t))
    return dict(model=model, edition=edition or "-", bundle="with games" if bundle else "console only")


# ---- audio ---------------------------------------------------------------------------------------------------

AUDIO_BRANDS = (r"sony|bose|sennheiser|apple|beats|jbl|beyerdynamic|akg|audio[- ]?technica|shure|marshall|"
                r"bang\s*&\s*olufsen|b\s*&\s*o|b&o|bowers\s*&\s*wilkins|b&w|teufel|sonos|yamaha|denon|marantz|pioneer|"
                r"onkyo|technics|harman\s*kardon|canton|magnat|klipsch|kef|dali|nubert|elac|heco|jamo|polk|wharfedale|"
                r"q\s*acoustics|nad|cambridge\s*audio|rega|pro-?ject|thorens|dual|lenco|audio\s*pro|ultimate\s*ears|"
                r"soundcore|anker|samsung|huawei|xiaomi|hifiman|focal|grado|koss|philips|panasonic|kenwood|nubert|"
                r"bluesound|arcam|rotel|naim|quad|tannoy|monitor\s*audio|mackie|krk|adam|genelec|edifier|nothing|"
                r"jabra|steelseries|razer|logitech|hyperx|corsair|creative|stanton|reloop|numark|akai|audioengine")
GENERIC_AUDIO = (r"kopfhörer|headphones?|headset|in-?ear|over-?ear|on-?ear|lautsprecher|boxen|box|speaker|"
                 r"verstärker|receiver|plattenspieler|turntable|bluetooth|wireless|kabellos|schwarz|weiß|weiss|silber|"
                 r"neu|neuwertig|set|paar|stück|original|ovp|mit|und|inkl|top|zustand|noise|cancelling|anc|true|"
                 r"hifi|hi-fi|stereo|aktiv|passiv|regal|stand|standlautsprecher|regallautsprecher|subwoofer|"
                 r"vollverstärker|av|surround|tragbar|portable|mini|white|black|sport|gaming|studio|monitor|edition")


def audio_model(t):
    """'sony wh1000xm4', 'airpods pro 2', 'technics sl1210 mk2' from a title; None without brand and model."""
    m = re.search(r"\bairpods\s*(pro|max)?\s*(?:\(?\s*(\d)\s*\.?\s*(?:gen|generation)?\)?)?", t)
    if m:
        return norm("airpods %s %s" % (m.group(1) or "", m.group(2) or ""))
    m = re.search(r"\b(%s)\b" % AUDIO_BRANDS, t)
    if not m:
        return None
    brand = norm(m.group(1)).replace(" ", "")
    words = re.findall(r"[a-z0-9][a-z0-9.+/-]*", t[m.end():])[:4]
    model = []
    for w in words:
        if re.fullmatch(GENERIC_AUDIO, w) and not model:
            continue
        if re.fullmatch(GENERIC_AUDIO, w):
            break
        model.append(w)
        if re.search(r"\d", w):
            nxt = words[words.index(w) + 1] if words.index(w) + 1 < len(words) else ""
            if re.fullmatch(r"mk\s*\d|mk[ivx]+|ii|iii|iv|pro|max|plus|se|gen\d?|\d", nxt):
                model.append(nxt)
            break
    if not model or not any(re.search(r"\d", w) for w in model):
        if brand == "sonos" and model and model[0] in ("one", "beam", "arc", "move", "roam", "sub", "five", "ace", "era"):
            return "sonos " + model[0]
        return None
    name = re.sub(r"[.\-/]", "", " ".join(model))
    name = name.replace("quietcomfort", "qc")
    return "%s %s" % (brand, name)


AUDIO_PARTS = (r"ladecase|ladebox|lade-?case|charging\s*case|\bcase\b|hülle|ersatz|\beinzeln|\blinks\b|\brechts\b|"
               r"ohrpolster|polster|kabel|ständer|halterung|fernbedienung|netzteil|nadel|tonabnehmer|riemen")


def audio_kind(name, about, cats, words, not_this):
    @kind(name, about, cats, keys=[("model",)], fields=["model"], words=words)
    def fn(ad):
        title = low_title(ad)
        if re.search(not_this, title) or re.search(AUDIO_PARTS, head(title)):
            return "accessory or part"
        return dict(model=audio_model(title))
    return fn


audio_kind("headphones", "headphones and earbuds", ["audio-hifi/kopfhoerer-6813"],
           r"\b(?:kopfhörer|headphones?|airpods|earbuds|in-?ear|wh-?1000|buds)\b",
           r"^(?:neue?r?s?\s+)?(?:ersatz|ohrpolster|polster|kabel|case|hülle|ladecase|ladekabel|tasche|ständer|stand)\b")
audio_kind("speakers", "loudspeakers", ["audio-hifi/lautsprecher-boxen-6816"],
           r"\b(?:lautsprecher|boxen|speaker|sonos|subwoofer)\b",
           r"^(?:neue?r?s?\s+)?(?:ständer|stand|halterung|kabel|bespannung|chassis|hochtöner|tieftöner|frequenzweiche)\b")
audio_kind("hifi", "amplifiers and receivers", ["audio-hifi/stereoanlagen-verstaerker-6836"],
           r"\b(?:verstärker|receiver|avr|amplifier|vollverstärker)\b",
           r"^(?:neue?r?s?\s+)?(?:fernbedienung|kabel|netzteil|ersatz)\b")
audio_kind("turntable", "turntables", ["audio-hifi/plattenspieler-turntables-6829"],
           r"\b(?:plattenspieler|turntable|tonarm)\b",
           r"^(?:neue?r?s?\s+)?(?:nadel|tonabnehmer|system|riemen|haube|plattenteller|slipmat|ersatz|headshell)\b")


# ---- computers (on top of the built-in profiles) ----------------------------------------------------------------

def laptop_model(t):
    m = re.search(r"\bmac\s?book\s*(air|pro)?\s*(?:(1[3-6])\s*(?:zoll|\"|''|”|-inch|inch)?)?.*?\b(m[1-5])\s*(pro|max)?\b", t)
    if m:
        return norm("macbook %s %s %s %s" % (m.group(1) or "", m.group(2) or "", m.group(3), m.group(4) or ""))
    m = re.search(r"\b(thinkpad|latitude|elitebook|probook|xps|zenbook|vivobook|ideapad|yoga|thinkbook|legion|"
                  r"surface\s*(?:laptop|pro)|precision|zbook|swift|aspire|spectre|envy|pavilion|omen|victus|rog|tuf|"
                  r"predator|nitro|galaxy\s*book|matebook|framework)\s*([a-z]{0,3}\s?\d{1,4}[a-z]{0,2}"
                  r"(?:\s*(?:gen|g)\s*\d{1,2})?|carbon(?:\s*gen\s*\d{1,2})?)?", t)
    if m:
        return norm("%s %s" % (m.group(1), m.group(2) or ""))
    return None


@kind("laptop", "laptops", ["computer-tablets/notebooks-5831"],
      keys=[("model", "cpu", "ram"), ("cpu", "gpu", "ram"), ("cpu", "gpu")], fields=["model", "cpu", "gpu", "ram"],
      words=r"\b(?:laptop|notebook|macbook|thinkpad|elitebook|latitude|ultrabook)\b")
def laptop(ad):
    a = dict(ad)
    reason = profiles.laptop(a)
    if reason:
        return reason
    gpu = a.get("gpu") or ("igpu" if a.get("cpu") else None)   # no dGPU named: integrated, if we know the CPU
    return dict(model=laptop_model(low_title(ad)), cpu=a.get("cpu"), gpu=gpu, ram=a.get("ram"))


@kind("pc", "desktop PCs", ["computer-tablets/pcs-5833"], keys=[("gpu", "cpu", "ram"), ("gpu", "cpu")],
      fields=["gpu", "cpu", "ram"], words=r"\b(?:gaming[- ]?pc|desktop|tower|pc)\b")
def pc(ad):
    a = dict(ad)
    reason = profiles.pc(a)
    if reason:
        return reason
    gpu = a.get("gpu") or ("none" if profiles.NO_GPU.search(full_text(ad)) else None)   # unknown is not "none"
    return dict(gpu=gpu, cpu=a.get("cpu"), ram=a.get("ram"))


@kind("server", "servers, mini PCs for a homelab and NAS", ["netzwerke/server-5875", "netzwerke/nas-systeme-5873"],
      keys=[("form", "cpu", "ram"), ("form", "cpu")], fields=["form", "cpu", "ram", "bays"],
      words=r"\b(?:server|nas|microserver|synology|qnap|proliant)\b")
def server(ad):
    a = dict(ad)
    reason = profiles.server(a)
    if reason:
        return reason
    return dict(form=a.get("form"), cpu=a.get("cpu"), ram=a.get("ram"), bays=a.get("bays"))


# ---- specs, keys, value ---------------------------------------------------------------------------------------

def kind_of(ad):
    """The kind whose willhaben category the ad is in, or None."""
    for k in KINDS.values():
        if in_cats(ad, k["ids"]):
            return k["name"]
    return None


def specs(ad, name):
    """Annotate an ad: `junk` (a reason or None) and `specs` (this kind's fields) as `wh` shows them."""
    k = KINDS[name]
    reason = profiles.generic_junk(ad)
    cond = condition(ad)
    if not reason and cond == "defect":
        reason = "marked defect"
    out = k["extract"](ad) if not reason else None
    if isinstance(out, str):
        reason, out = out, None
    ad["junk"] = reason
    ad["specs"] = out or {}
    ad["cond"] = cond
    return ad


def keys(name, sp):
    """[(level, key tuple)] for every key level whose fields are all known."""
    out = []
    for i, fields in enumerate(KINDS[name]["keys"]):
        vals = tuple(sp.get(f) for f in fields)
        if all(v is not None for v in vals):
            out.append((i, vals))
    return out


def label(name, sp, fields=None):
    parts = []
    for f in fields or (KINDS[name]["fields"] if name in KINDS else list(sp)):
        v = sp.get(f)
        if v in (None, "-", ""):
            continue
        parts.append("%s%s" % (v, {"ram": " GB RAM", "size": "\"", "storage": " GB", "capacity": " GB", "watt": " W",
                                  "speed": " MHz", "hz": " Hz", "vram": " GB"}.get(f, "")))
    return " · ".join(str(p) for p in parts)


def parse_time(s):
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def wmedian(pairs):
    """Weighted median of [(value, weight)]."""
    pairs = sorted(pairs)
    total = sum(w for _, w in pairs)
    acc = 0
    for v, w in pairs:
        acc += w
        if acc >= total / 2:
            return v
    return pairs[-1][0]


def build_index(ads, name, now=None):
    """{(level, key): [sample]} over annotated ads that count for a market value: not junk, priced, not a dealer's
    new stock. One sample per ad: price, weight (older or long-unsold asking prices count less), seller, id."""
    now = now or datetime.now(timezone.utc)
    newest = max((parse_time(a.get("last_seen")) for a in ads if a.get("last_seen")), default=None)
    idx = {}
    for a in ads:
        if a.get("junk") or not a.get("price") or a["price"] < 1:
            continue
        if a.get("cond") == "new" and not a.get("private"):
            continue
        w = 1.0
        last, first_ = parse_time(a.get("last_seen")), parse_time(a.get("first_seen"))
        if newest and last and (newest - last).days > 2:
            w *= 0.8                                          # gone since: maybe sold at that price, maybe expired
        if first_ and last and (last - first_).days > 45:
            w *= 0.6                                          # on sale for weeks: the asking price is too high
        for lvl, key in keys(name, a["specs"]):
            idx.setdefault((lvl, key), []).append((a["price"], w, a.get("seller") or "id%s" % a["id"], a["id"]))
    return idx


def estimate(samples, exclude=None):
    """Market value from samples [(price, weight, seller, id)]: one value per seller (their median), outliers
    dropped, weighted median. None with fewer than MIN_SELLERS sellers."""
    per = {}
    for p, w, s, i in samples:
        if i == exclude:
            continue
        per.setdefault(s, []).append((p, w))
    pts = [(statistics.median(p for p, _ in v), max(w for _, w in v)) for v in per.values()]
    if len(pts) < MIN_SELLERS:
        return None
    m = wmedian(pts)
    pts = [(p, w) for p, w in pts if m / 3 <= p <= m * 3]
    if len(pts) < MIN_SELLERS:
        return None
    m = wmedian(pts)
    ps = sorted(p for p, _ in pts)
    q = statistics.quantiles(ps, n=4) if len(ps) >= 4 else [ps[0], m, ps[-1]]
    spread = (q[2] - q[0]) / m if m else 9
    n = len(pts)
    conf = ("high" if n >= 10 and spread <= 0.5 else "medium" if n >= 5 and spread <= 0.8 else "low")
    return dict(value=round(m, 2), p25=round(q[0], 2), p75=round(q[2], 2), n=n, spread=round(spread, 2), conf=conf)


def value_of(idx, name, sp, exclude=None):
    """The market value for these specs: the most specific key with a medium or high confidence, else the most
    specific one with any value. Adds `level` (the key's fields) and `key`."""
    best = None
    for lvl, key in keys(name, sp):
        est = estimate(idx.get((lvl, key), []), exclude)
        if not est:
            continue
        est.update(level=KINDS[name]["keys"][lvl], key=key)
        if est["conf"] in ("high", "medium"):
            return est
        best = best or est
    return best


def deal(ad, est):
    """Discount against the market value, a score that weighs it by confidence, and warning flags."""
    if not est or not ad.get("price"):
        return dict(value=None, discount=None, score=None, flags=[])
    disc = 1 - ad["price"] / est["value"]
    flags = []
    hurry = urgent(ad)
    if hurry:
        flags.append("urgent sale (%s)" % hurry)
    if disc >= TOO_GOOD:
        flags.append("far below value: maybe a %s, or a defect, the wrong model or a scam; read the ad"
                     % ("real urgent sale" if hurry else "real bargain"))
    if ad.get("cond") in ("new", "like new", "refurbished"):
        flags.append(ad["cond"])
    if not ad.get("private"):
        flags.append("dealer")
    return dict(value=est["value"], discount=round(disc, 3), score=round(disc * CONF_WEIGHT[est["conf"]], 3),
                flags=flags, urgent=hurry)


def odd(r):
    """Far below value without a reason the seller gives (no urgent-sale words): listed after the plain deals."""
    return (r.get("discount") or 0) >= TOO_GOOD and not r.get("urgent")


# ---- queries --------------------------------------------------------------------------------------------------

def guess_kind(q):
    """The kind a query is about, from its words: 'ddr4 2x16' → ram. None when nothing fits."""
    hits = [k["name"] for k in KINDS.values() if k["words"].search(q)]
    if not hits:
        pseudo = dict(title=q, body="", price=1)
        for name in ("gpu", "cpu", "phone", "console", "tv"):
            sp = KINDS[name]["extract"](dict(pseudo))
            if isinstance(sp, dict) and (sp.get("model") or sp.get("series")):
                return name
        return None
    order = ["ram", "gpu", "cpu", "mainboard", "psu", "disk", "phone", "tablet", "console", "headphones", "turntable",
             "hifi", "speakers", "monitor", "tv", "laptop", "server", "pc"]
    return sorted(hits, key=order.index)[0]


def size_range(q):
    """'45-55', '45 bis 55 zoll', '55"' → (lo, hi) in inches, or None."""
    m = re.search(r"\b(\d{2})\s*(?:-|–|bis|to)\s*(\d{2})\s*(?:zoll|\"|''|”|inch)?", q)
    if m:
        lo, hi = sorted((int(m.group(1)), int(m.group(2))))
        return lo, hi
    s = inches(q.lower(), 13, 100)
    return (s, s) if s else None


def query_specs(q, name):
    """What a query asks for, as specs of the kind (only the fields it names) plus a size range."""
    sp = KINDS[name]["extract"](dict(title=q, body="", price=1))
    sp = {k: v for k, v in sp.items() if v not in (None, "-")} if isinstance(sp, dict) else {}
    for k, v in KINDS[name]["defaults"].items():
        if k not in sp or (name == "ram" and k == "form" and not re.search(r"so-?dimm|laptop|notebook|ecc|server|"
                                                                         r"registered", q.lower())):
            sp[k] = v
    if name == "ram":                                       # "32gb ddr4" means the total, not the kit layout
        if "kit" in sp:
            sp.pop("total", None)
    if name in ("tv", "monitor"):
        if not sp.get("series"):
            sp.pop("year", None)
        if not re.search(r"oled|qled|mini|plasma|ips|va\b|tn\b|\b[a-z]{1,2}\d{2,4}|\d{2}[a-z]{2,4}\d", q.lower()):
            sp.pop("panel", None)
        if sp.get("panel") == "led" and not re.search(r"\bled\b", q.lower()) and not sp.get("series"):
            sp.pop("panel")
    if name == "console":
        sp.pop("bundle", None)
        if sp.get("edition") == "-":
            sp.pop("edition")
    return sp


AT_LEAST = {"speed", "storage", "capacity", "ram", "hz", "watt"}   # a query's number is the minimum for these


def matches(ad_specs, want, size=None):
    for k, v in want.items():
        have = ad_specs.get(k)
        if have is None:
            return False
        if k in AT_LEAST and isinstance(v, (int, float)) and isinstance(have, (int, float)):
            if have < v:
                return False
        elif have != v:
            return False
    if size:
        s = ad_specs.get("size")
        if s is None or not size[0] <= s <= size[1]:
            return False
    return True
