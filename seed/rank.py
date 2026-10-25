import json, re, sys, os, csv

D = sys.argv[1]
src = open(os.path.join(os.path.dirname(__file__), "analyze.py")).read()
exec(src[src.index("# rough"):src.index("out = []")])  # GPU/CPU tables + parsers
# MacBook ads often say "iCloud abgemeldet" - only an actual lock is a problem
BAD = BAD.replace("|icloud", "") + r"|icloud[- ]?(sperre|gesperrt|lock)|aktivierungssperre|mdm|defect|broken|not working|funktioniert nicht|nicht funktions"
PART = r"^(neue?r?s? )?(kühlung|kühler|lüfter|akku|tastatur|display|bildschirm|netzteil|ladegerät|mainboard|motherboard|gehäuse|scharnier|ram|ssd|grafikkarte|mxm)\b|\b(für|fuer|passend für) (clevo|lenovo|asus|acer|hp|dell|msi|macbook|legion|thinkpad)"
CPU = CPU + [(r"i[357]\s?-?\s?[67]\d{3}h[qk]", 1.2, "Intel 6/7th HQ")]

ads = [a for a in json.load(open(os.path.join(D, "parsed.json"))) if "5831" in a["cats"]]
det = json.load(open(os.path.join(D, "details.json"))) if os.path.exists(os.path.join(D, "details.json")) else {}

rows = []
for a in ads:
    d = det.get(a["id"], {})
    if d.get("status") and d["status"] != "active":
        continue
    full = (a["title"] + " " + a["body"] + " " + d.get("desc", "")).lower().replace("–", "-")
    if re.search(BAD, full) or re.search(PART, a["title"].lower()):
        continue
    gs, gn = first(GPU, full)
    cs, cn = first(CPU, full)
    r = dict(a, gpu=gn, gpu_s=gs, cpu=cn, cpu_s=cs, ram=ram(full), hz=hz(full), desc=d.get("desc", ""),
             detail=bool(d), first_published=d.get("first_published") or a["published"],
             warranty=bool(re.search(r"garantie|gewährleistung bis|rechnung vorhanden|mit rechnung", full)),
             new=bool(re.search(r"\bneu\b|\bovp\b|unbenutzt|originalverpackt|neuwertig|wie neu", full)),
             singlech=bool(re.search(r"\b8\s?gb\b", full)) and not re.search(r"16\s?gb|32\s?gb", full),
             gen=(re.search(r"gen\.?\s?(\d{1,2})\b", full) or [None, None])[1])
    rows.append(r)

# --- esports pick: GPU >= GTX 1660 Ti / RTX 3050 class, H-series CPU >= Ryzen 4000H / Intel 10th H
def es(r):
    if r["gpu_s"] is None:
        return None
    if r["gpu_s"] >= 3.5 and (r["cpu_s"] or 0) >= 2.7:
        return "yes"
    if r["gpu_s"] >= 3.5 and r["cpu_s"] is None:
        return "cpu?"
    if r["gpu_s"] >= 2.2 and (r["cpu_s"] or 0) >= 2.5:
        return "marginal"
    return None

for r in rows:
    r["esports"] = es(r)

game = sorted([r for r in rows if r["esports"] and r["price"] <= 800], key=lambda r: r["price"])

# --- best ~1000 €: strong all-rounders 450-1150 €
def best_score(r):
    t = (r["title"] + " " + r["desc"] + " " + r["body"]).lower()
    s = (r["cpu_s"] or 0)
    if r["apple"]:
        s += 1.5  # build/battery/screen
        if re.search(r"macbook pro", t): s += 0.5
    if re.search(r"thinkpad (x1|t14s|z13|p14s|t14)|xps|zenbook|yoga (slim|pro|7)|framework|spectre|omnibook|elitebook 8|surface laptop|gram|swift (go|16|ai)|galaxy book\s?[345]", t):
        s += 1
    if re.search(r"oled|mini[- ]?led|liquid retina|2\.8k|3k|2880", t): s += 0.5
    if r["gpu_s"]: s += min(r["gpu_s"], 7) * 0.4
    if (r["ram"] or 0) >= 16: s += 0.7
    elif r["ram"] and r["ram"] <= 8: s -= 1
    if r["warranty"]: s += 0.4
    return round(s - r["price"] / 1000, 2)

best = [r for r in rows if 450 <= r["price"] <= 1150 and (r["cpu_s"] or 0) >= 4]
for r in best:
    r["best_s"] = best_score(r)
best.sort(key=lambda r: -r["best_s"])

cols = ["price", "title", "gpu", "cpu", "ram", "hz", "esports", "state", "loc", "private", "warranty", "new", "first_published", "url"]
for name, lst in [("esports.csv", game), ("best1000.csv", best)]:
    with open(os.path.join(D, name), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols + (["best_s"] if name == "best1000.csv" else []), extrasaction="ignore")
        w.writeheader(); w.writerows(lst)

def show(lst, n, extra=""):
    for r in lst[:n]:
        print(f"{r['price']:>6.0f} | {r['esports'] or '':8} | {(r['gpu'] or '-'):11} | {(r['cpu'] or '-'):16} | {str(r['ram'] or '-'):>3}GB | {str(r['hz'] or ''):>3} | {r['state'][:10]:10} | {'P' if r['private'] else 'H'} | {r.get('best_s', '')} | {r['title'][:60]} | {r['url']}")

print("rows", len(rows), "esports cands", len(game), {k: sum(1 for r in game if r['esports'] == k) for k in ('yes', 'cpu?', 'marginal')})
print("\n=== ESPORTS yes (cheapest) ==="); show([r for r in game if r["esports"] == "yes"], int(sys.argv[2]) if len(sys.argv) > 2 else 40)
print("\n=== ESPORTS cpu? ==="); show([r for r in game if r["esports"] == "cpu?"], 20)
print("\n=== ESPORTS marginal ==="); show([r for r in game if r["esports"] == "marginal"], 15)
print("\n=== BEST ~1000 ==="); show(best, 50)
