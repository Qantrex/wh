import json, re, sys, time, urllib.parse, urllib.request, os

OUT = sys.argv[1]  # output dir
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"
BASE = "https://www.willhaben.at/iad/kaufen-und-verkaufen/marktplatz/laptops-notebooks-5824"

# keyword -> price cap
GAMING = 800
BEST = 1150
KW = {}
for k in [
    # generic, german + english
    "gaming laptop", "gaming notebook", "gamer laptop", "gamer notebook", "spiele laptop",
    "laptop gaming", "esports laptop", "144hz", "165hz", "120hz", "rtx", "gtx", "geforce", "nvidia",
    # GPUs
    "gtx 1650", "gtx 1650 ti", "gtx 1660", "gtx 1660 ti", "gtx 1070", "gtx 1080", "rtx 2050", "rtx 2060",
    "rtx 2070", "rtx 2080", "rtx 3050", "rtx 3050 ti", "rtx 3060", "rtx 3070", "rtx 4050", "rtx 4060",
    "rtx 5050", "rx 5500m", "rx 5600m", "rx 6600m", "rx 6500m", "radeon",
    # CPUs
    "ryzen 5 4600h", "ryzen 5 5600h", "ryzen 7 4800h", "ryzen 7 5800h", "ryzen 5 6600h", "ryzen 7 6800h",
    "ryzen 5 7535hs", "ryzen 7 7735hs", "ryzen 5 7640hs", "i5-10300h", "i5-11400h", "i7-10750h",
    "i7-11800h", "i5-12450h", "i5-12500h", "i7-12700h", "i5-13420h", "i7-13620h",
    # gaming lines
    "legion", "legion 5", "legion 5 pro", "ideapad gaming", "lenovo loq", "nitro 5", "nitro v",
    "acer predator", "predator helios", "asus tuf", "tuf gaming", "rog strix", "rog zephyrus",
    "hp victus", "hp omen", "pavilion gaming", "msi gf63", "msi katana", "msi thin", "msi cyborg",
    "msi bravo", "msi sword", "msi gl65", "msi gp66", "dell g15", "dell g5", "alienware", "gigabyte g5",
    "gigabyte aorus", "medion erazer", "xmg", "schenker", "clevo", "razer blade", "thunderobot",
]:
    KW[k] = GAMING
for k in [
    # premium/all-round lines for the ~1000 € pick
    "macbook air", "macbook air m1", "macbook air m2", "macbook air m3", "macbook air m4", "macbook pro m1",
    "macbook pro m2", "macbook pro m3", "macbook pro 14", "macbook neo", "thinkpad", "thinkpad t14",
    "thinkpad x1 carbon", "thinkpad t14s", "thinkpad x13", "thinkpad p14s", "thinkpad z13", "lenovo yoga",
    "yoga slim 7", "yoga pro", "yoga 7", "zenbook", "zenbook 14 oled", "asus vivobook pro", "dell xps",
    "xps 13", "xps 15", "framework laptop", "hp omnibook", "hp elitebook", "hp spectre", "hp envy",
    "surface laptop", "lg gram", "samsung galaxy book", "acer swift", "swift go", "huawei matebook",
    "tuxedo", "ryzen ai", "core ultra", "snapdragon x", "oled laptop", "ultrabook",
    # strong gaming that can be the 1000 € pick
    "rtx 4060 laptop", "rtx 4070", "rtx 3070 ti", "rtx 3080", "legion pro", "legion slim",
    "zephyrus g14", "zephyrus g16", "rog flow",
]:
    KW[k] = max(KW.get(k, 0), BEST)


def fetch(params):
    url = BASE + "?" + urllib.parse.urlencode(params)
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "de-AT,de;q=0.9"})
            h = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S)
            return json.loads(m.group(1))["props"]["pageProps"]["searchResult"]
        except Exception as e:
            print("  retry", attempt, e, file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    return None


ads, hits = {}, {}
for kw, cap in KW.items():
    page, got = 1, 0
    while True:
        sr = fetch({"keyword": kw, "rows": 200, "page": page, "PRICE_FROM": 80, "PRICE_TO": cap})
        if not sr:
            break
        lst = sr["advertSummaryList"]["advertSummary"]
        for a in lst:
            at = {x["name"]: x["values"] for x in a["attributes"]["attribute"]}
            g = lambda n: (at.get(n) or [""])[0]
            ad = {
                "id": a["id"], "title": g("HEADING"), "body": g("BODY_DYN"), "price": g("PRICE"),
                "loc": g("LOCATION"), "state": g("STATE"), "postcode": g("POSTCODE"),
                "private": g("ISPRIVATE") == "1", "published": g("PUBLISHED_String"),
                "url": "https://www.willhaben.at/iad/" + g("SEO_URL"), "cats": g("categorytreeids"),
            }
            ads[a["id"]] = ad
            hits.setdefault(a["id"], []).append(kw)
        got += len(lst)
        print(f"{kw!r} cap {cap}: page {page} -> {len(lst)} (found {sr['rowsFound']})", file=sys.stderr)
        if got >= sr["rowsFound"] or not lst or page >= 5:
            break
        page += 1
        time.sleep(1.2)
    time.sleep(1.2)

for i in ads:
    ads[i]["keywords"] = hits[i]
json.dump(list(ads.values()), open(os.path.join(OUT, "ads.json"), "w"), ensure_ascii=False, indent=1)
print("unique ads:", len(ads), file=sys.stderr)
