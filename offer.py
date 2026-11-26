"""How far an ad's price can probably drop: the signals, a plan to haggle (an opening offer, one or two counter
steps and the last offer, all round prices with rough odds) and short German messages. Pure Python: wh gathers the
facts (ad page, database, market value, backtest) and passes them in as one dict, so everything here is testable
offline.

Nobody ever sees the price a used item is finally sold for. The range is a rule of thumb (private sellers usually come
down 10–25 %) shifted by the ad's signals, and wh says which of them are measured and which are rules of thumb.
"""
import re
from datetime import date

import market

RUN_DAYS = 45                 # a private willhaben ad runs this long from its last publishing, then expires
MAX_ROOM = 45                 # never expect more than this (in % off the asking price)
PRIVATE = (10.0, 25.0)        # how far a usual private seller comes down, in % off the ask (a rule of thumb)
DEALER = (0.0, 5.0)
OPEN_ODDS = 0.25              # the first offer: about one seller in four says yes right away
STEP_SHARE = 0.6              # a counter step gives up this share of the way from the first to the last offer
LOWBALL = 0.65                # never open below this share of the ask (0.8 with a fixed price): it ends the chat


def band_text(private=True):
    return "%g–%g %%" % (PRIVATE if private else DEALER)

VB = re.compile(r"\b(?:vb|vhb|verhandlungsbasis|(?<!nicht\s)verhandelbar|preisvorschl\w*\s+(?:willkommen|erwünscht)|"
                r"mach\w*\s+(?:mir\s+)?(?:ein\s+)?angebot|(?:für\s+)?angebote\s+offen|offen\s+für\s+angebote)\b", re.I)
FIX = re.compile(r"\b(?:fix\s*preis|festpreis|preis\s+(?:ist\s+)?fix|fix(?=\s*(?:€|eur|euro|\.|,|!|$))|"
                 r"nicht\s+verhandelbar|keine\s+(?:preis)?verhandlung\w*|letzter\s+preis|"
                 r"keine\s+(?:preis)?(?:vorschläge|angebote|lowball\w*)|\d+\s*(?:€|eur|euro)?\s*fix)\b", re.I)
LOWERED = re.compile(r"\b(?:preis\s+(?:reduziert|gesenkt|herabgesetzt)|(?:jetzt|nun)\s+(?:nur\s+)?(?:noch\s+)?\d+|"
                     r"reduziert|preissenkung|stark\s+reduziert)\b", re.I)
PICKUP_ONLY = re.compile(r"\b(?:nur|ausschließlich|ausschliesslich)\s+(?:selbst)?abholung|kein\s+versand|"
                         r"versand\s+nicht\s+möglich|abholung\s+only\b", re.I)
STATED = re.compile(r"(?:preis\s*:?\s*|vb\s*|fix\s*preis\s*:?\s*)(?:€\s*)?(\d[\d.]*)\s*(?:€|eur\w*)?\s*(fix|vb)?|"
                    r"(\d[\d.]*)\s*(?:€|eur\w*)?\s*(fix|vb)\b", re.I)


def nice(p, down=True):
    """A round price, easy to pay in cash at a pickup: whole euros under €20, multiples of €5 up to €200 and of €10
    above. Rounds down unless down=False."""
    step = 1 if p < 20 else 5 if p < 200 else 10
    n = int(p // step) if down else -int(-p // step)
    return max(step, n * step)


def is_round(x):
    """True for a price nice() can give: what every price wh offer suggests must be."""
    return x == int(x) and (x < 20 or x % 5 == 0 and (x <= 200 or x % 10 == 0))


def text_flags(text, price=None):
    """What the seller's text says about the price: [(key, the words, note)]. key: vb, fix, stale_fix (the text names
    a higher fixed price than the ad has now: the seller cut it anyway), urgent, lowered, pickup_only."""
    t = " ".join((text or "").split())
    out = []
    stated = []
    for m in STATED.finditer(t):
        n, how = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        v = market.first(r"(\d+)", n.replace(".", ""))
        if v and 2 <= int(v) <= 100000:
            stated.append((int(v), (how or "").lower()))
    fix = FIX.search(t)
    if fix:
        higher = [v for v, _ in stated if price and v > price * 1.02]
        if higher:
            at = "" if str(higher[0]) in fix.group(0) else " at €%d" % higher[0]
            out.append(("stale_fix", fix.group(0), "the text still says \"%s\"%s, the ad now asks €%s: the 'fixed' "
                        "price is gone" % (fix.group(0), at, fmt(price))))
        else:
            out.append(("fix", fix.group(0), "fixed price in the text"))
    vb = VB.search(t)
    if vb and not fix:
        out.append(("vb", vb.group(0), "open to offers"))
    m = market.URGENT.search(t)
    if m:
        out.append(("urgent", m.group(0), "wants it gone soon"))
    m = LOWERED.search(t)
    if m:
        out.append(("lowered", m.group(0), "says the price was lowered"))
    m = PICKUP_ONLY.search(t)
    if m:
        out.append(("pickup_only", m.group(0), "pickup only: fewer buyers"))
    return out


def fmt(p):
    return ("%.2f" % p).rstrip("0").rstrip(".") if p is not None else "?"


def days(a, b):
    try:
        return (date.fromisoformat(str(b)[:10]) - date.fromisoformat(str(a)[:10])).days
    except (TypeError, ValueError):
        return None


def cuts_of(history, old_price=None, cut_on=None, price=None):
    """Price changes as [(day, from, to)], from wh's history [(from day, until day, price)] plus willhaben's own record
    of the last cut (old_price, cut_on) when wh didn't see the price before it."""
    out = []
    for (_, _, a), (t, _, b) in zip(history, history[1:]):
        if a and b and a != b:
            out.append((t, a, b))
    if not (old_price and price and old_price > price):
        return out
    last = out[-1] if out and abs(out[-1][2] - price) < 0.5 else None
    if last and abs(last[1] - old_price) < 0.5:             # the same cut: willhaben knows the day, wh when it saw it
        out[-1] = (cut_on or last[0], last[1], last[2])
    elif last and last[1] > old_price:                      # wh saw one step where there were two
        out[-1:] = [("before %s" % cut_on if cut_on else last[0], last[1], old_price), (cut_on or last[0], old_price, price)]
    elif not last:
        out.append((cut_on or "?", old_price, price))
    return out


def estimate(f, today=None):
    """f: the facts about one ad (see wh's offer_facts()). Returns a dict: ask; floor (the lowest price the seller will
    probably still accept) and floor_odds; over (that floor is above the walk-away price: don't offer); ladder [(price, rough odds)]; low, high (one in five sellers go down to low,
    four in five take high); conf; open (a lowball to try first); walk (walk-away price); reasons [(sign, text,
    source)], cuts, flags, days_online, at_least (days_online is only a lower bound), days_left, warnings."""
    today = today or date.today()
    p = f.get("price")
    if not p:
        return dict(ask=p, error="the ad has no price (0 or 'zu verschenken'): nothing to estimate")
    reasons, warnings = [], []
    lo, hi = (PRIVATE if f.get("private", True) else DEALER)
    reasons.append(("", "%s seller: a usual private seller comes down %s" % (
        "private" if f.get("private", True) else "dealer",
        band_text(f.get("private", True)) + ("" if f.get("private", True) else
                                              " (a dealer prices to sell, warranty counts)")), "rule"))

    def add(dlo, dhi, text, source="ad"):
        nonlocal lo, hi
        lo += dlo
        hi += dhi
        sign = "+" if dhi > 0 or dlo > 0 else "-" if dhi < 0 or dlo < 0 else ""
        reasons.append((sign, text, source))

    # time online: the earliest date anyone has for this ad
    starts = [(d, src) for d, src in ((f.get("first_published"), "willhaben"), (f.get("published"), "willhaben"),
                                      (f.get("first_seen"), "wh")) if d]
    start, src = min(starts) if starts else (None, None)
    online = days(start, today) if start else None
    at_least = bool(start and src == "wh" and f.get("first_crawl") and str(f["first_seen"])[:10] <= str(f["first_crawl"])[:10])
    relisted = bool(f.get("first_seen") and f.get("first_published") and
                    str(f["first_seen"])[:10] < str(f["first_published"])[:10])
    if relisted:
        warnings.append("wh saw this ad on %s, before willhaben's online-since date %s: it was bumped or relisted"
                        % (str(f["first_seen"])[:10], f["first_published"]))
    if online is not None:
        what = "%s%d days online" % ("at least " if at_least else "", online)
        if online < 3:
            add(-2, -3, "%s: the seller still hopes for the asking price" % what)
        elif online < 14:
            reasons.append(("", what, "ad"))
        elif online < 30:
            add(2, 3, "%s: nobody took it at this price in two weeks" % what)
        elif online < 60:
            add(3, 6, "%s: a month without a buyer at this price" % what)
        else:
            add(5, 10, "%s: renewed at least once, nobody bought at the asking price" % what)
    if f.get("bumped"):
        add(0, 2, "paid to push the ad to the top: wants to sell")
    left = days(today, f["ends"]) if f.get("ends") and f.get("private", True) else None
    if left is not None and 0 <= left <= 7:
        add(1, 3, "expires in %d day%s (%s): a good moment, the seller has to renew or let it go"
            % (left, "" if left == 1 else "s", f["ends"]))

    # the ad's own price history
    cuts = cuts_of(f.get("history") or [], f.get("old_price"), f.get("cut_on"), p)
    down = [c for c in cuts if c[2] < c[1]]
    up = [c for c in cuts if c[2] > c[1]]
    if down:
        first, total = down[0][1], (1 - p / down[0][1]) * 100
        last_day = down[-1][0]
        since = days(last_day, today)
        txt = "%d price cut%s, %s → %s (−%.0f %%), last on %s" % (
            len(down), "" if len(down) == 1 else "s", fmt(first), fmt(p), total, last_day)
        if len(down) >= 2:
            add(4, 7, txt + ": the seller keeps moving")
        else:
            add(2, 4, txt + ": the seller is moving" + (" (just now: a second cut right away is less likely, an offer "
                                                       "close to it isn't)" if since is not None and since <= 3 else ""))
    if up:
        add(-2, -3, "price raised on %s: the seller thinks it's worth more" % up[-1][0])

    # the seller's text
    flags = text_flags(" ".join(x for x in (f.get("title"), f.get("descr")) if x), p)
    keys = {k for k, _, _ in flags}
    for k, words, note in flags:
        if k == "vb":
            add(2, 5, "\"%s\": %s" % (words, note), "rule")
        elif k == "urgent":
            add(3, 8, "\"%s\": %s" % (words, note), "rule")
        elif k == "lowered" and not down:
            add(1, 3, "\"%s\": %s" % (words, note), "rule")
        elif k == "pickup_only":
            add(0, 3, "\"%s\": %s" % (words, note), "rule")
        elif k == "stale_fix":
            reasons.append(("", note + (" (counted with the cut above)" if down else ""), "ad"))
        elif k == "fix":
            reasons.append(("-", "\"%s\": %s; such ads still cut their price as often as others (median about "
                            "−9 %%), so a modest offer is worth trying" % (words, note), "db"))

    # the seller
    n_ads = f.get("seller_ads") or 0
    if f.get("private", True) and n_ads > 40:
        reasons.append(("", "the seller has %d ads online: a trader in practice, who prices to sell and haggles "
                        "less than someone clearing out" % n_ads, "ad"))
    elif f.get("private", True) and n_ads >= 15:
        add(2, 4, "the seller has %d ads online: clearing out, likely to take a fair offer to get rid of things"
            % n_ads)
    sr = f.get("seller_record")
    if sr and sr.get("n", 0) >= 3:
        share = sr["n_cut"] / sr["n"]
        txt = "the seller cut the price on %d of %d other ads wh saw%s" % (
            sr["n_cut"], sr["n"], " (median −%.0f %%)" % (sr["median"] * 100) if sr.get("median") else "")
        if share >= 0.3 and (sr.get("median") or 0) >= 0.08:
            add(2, 5, txt + ": comes down when nothing moves", "db")
        elif share >= 0.15:
            add(1, 2, txt, "db")
        elif sr["n"] >= 5 and not sr["n_cut"]:
            add(-1, -2, txt + ": holds prices", "db")
        else:
            reasons.append(("", txt, "db"))
    since = f.get("seller_since") or ""
    if re.fullmatch(r"\d{4}-\d{2}", since):
        months = (today.year - int(since[:4])) * 12 + today.month - int(since[5:])
        if months <= 2:
            warnings.append("the account is from %s: check the scam signs before paying anything" % since)

    # the market
    v = f.get("value")
    ratio = p / v["value"] if v and v.get("value") else None
    if ratio:
        trust = v.get("conf") in ("high", "medium") and v.get("close", True)
        what = "asks %.0f %% of the market value %s (%s confidence, %d %s%s)" % (
            ratio * 100, fmt(v["value"]), v.get("conf", "low"), v.get("n", 0), v.get("unit", "sellers"),
            "" if v.get("close", True) else "; a loose match by %s, not this exact model" % v.get("match", "?"))
        src = "db"
        if not trust:
            what += ": a rough value"
        if ratio <= 0.8:
            add(-5 if trust else -2, -7 if trust else -3, what + ": already cheap, it will go fast; don't lose it over a "
                "lowball", src)
        elif ratio <= 0.95:
            add(-2 if trust else -1, -4 if trust else -2, what + ": a fair price already", src)
        elif ratio <= 1.1:
            reasons.append(("", what, src))
        elif ratio <= 1.3:
            add(2, 6 if trust else 4, what + ": above the market", src)
        else:
            add(4, 12 if trust else 6, what + ": well above the market", src)
    b = f.get("base")
    if b and b.get("n", 0) >= 30:
        txt = ("what %d %s did (%s) in %s days: %.0f %% cut their price%s, %.0f %% were taken down "
               "before they expired" % (b["n"], b.get("noun", "comparable ads"), b["label"], b["days"],
                                        b["cut_share"] * 100,
                                        " (median −%.0f %%)" % (b["cut_median"] * 100) if b.get("cut_median") else "",
                                        b["early_share"] * 100))
        if b["cut_share"] >= 0.1 and b.get("n_cut", 0) >= 10 and b["cut_median"] * 100 > hi:
            hi = (hi + b["cut_median"] * 100) / 2
            reasons.append(("+", txt, "db"))
        else:
            reasons.append(("", txt, "db"))

    # limits
    if "fix" in keys:       # a backtest over 14 nightly crawls: Fixpreis ads cut as often as others (median −8 to −10 %)
        lo, hi = min(lo, 3), min(hi, 12 if online and online >= 30 else 10)
    lo = max(0.0, min(lo, 30))
    hi = max(lo + 3, min(hi, MAX_ROOM))
    low, high = p * (1 - hi / 100), p * (1 - lo / 100)
    trusted = bool(ratio and v.get("conf") in ("high", "medium") and v.get("close", True))

    def odds(x):
        return odds_at(x, p, lo, hi)

    top = nice(p)                                          # the ask, as a round price

    def at(t, near=False):
        """The lowest round price with odds of at least t, never above the ask; near=True: the round price whose odds
        are closest to t (the lower one on a tie), so a small ad with €5 steps still leaves room for a counter step."""
        x = p * (1 - (lo + (0.8 - t) * (hi - lo) / 0.6) / 100)
        up = min(nice(x, down=False), top)
        if not near:
            return up
        return min((nice(x), up), key=lambda y: (abs(odds(y) - t), y))

    floor = at(0.5)                                        # the lowest price the seller will probably still accept
    low_r = min(nice(low, down=False), top)
    cheap = trusted and ratio <= 0.9
    over = bool(trusted and ratio > 1.0 and floor > nice(v["value"]))
    if trusted and ratio > 1.0 and low > v["value"]:
        warnings.append("even the low end (%s) is above the market value %s: walk away unless it's something special"
                        % (fmt(low_r), fmt(v["value"])))
    if over:
        walk = nice(v["value"])                            # the seller's likely floor is more than it's worth
    elif cheap:
        walk = top                                         # below the market: paying the ask is still a good buy
    else:
        walk = floor                                       # the last step, not a margin above the likely deal
    no_lower = min(nice(p * (0.8 if "fix" in keys else LOWBALL), down=False), floor)
    opening = min(max(at(0.4 if cheap else OPEN_ODDS, near=True), no_lower), walk)
    mid = floor if cheap else nice(opening + STEP_SHARE * (walk - opening))
    plan = sorted({opening, walk} | ({mid} if opening < mid < walk else set()))
    deal = odds(walk)
    paid = sum(x * (odds(x) - (odds(y) if y else 0)) for x, y in zip(plan, [None] + plan[:-1])) / deal
    conf = "low"
    if trusted and b and b.get("n", 0) >= 30 and online is not None and not at_least:
        conf = "medium"
    return dict(ask=p, floor=floor, floor_odds=round(odds(floor), 2), over=over,
                plan=[(x, round(odds(x), 2)) for x in plan], ladder=[(x, round(odds(x), 2)) for x in plan],
                deal_odds=round(deal, 2), expected=round(paid, 2), cheap=cheap, band=(lo, hi),
                low=low_r, high=nice(high) if high < p else top, conf=conf,
                open=opening, walk=walk, reasons=reasons, cuts=cuts, flags=flags, days_online=online, at_least=at_least,
                days_left=left, warnings=warnings, relisted=relisted)


def odds_at(x, ask, lo, hi):
    """Rough odds the seller accepts x: the band lo..hi (in % off the ask) is read as 'four in five sellers take the
    price at lo, one in five go down to hi', straight in between. A guess: no negotiated price is ever seen."""
    r = (1 - x / ask) * 100
    return max(0.05, min(0.95, 0.8 - 0.6 * (r - lo) / (hi - lo)))


def next_step(est, offered=None, counter=None):
    """Where the haggling stands after the seller answered: (what to do, the price to offer or None, which message).
    offered: your last offer; counter: the seller's price, or None for a plain no."""
    plan = [x for x, _ in est["plan"]]
    last = est["walk"]
    if offered is None:
        return "open with %s (step 1 of %d)" % (euro(plan[0]), len(plan)), plan[0], "first"
    if counter is not None and counter <= offered:
        return "the seller asks %s, no more than you offered: take it" % euro(counter), None, None
    later = [x for x in plan if x > offered]
    if counter is not None and later and counter <= later[0]:
        return ("take the seller's %s: it's no more than your next step (%s)" % (euro(counter), euro(later[0])),
                counter, "counter")
    if not later or offered >= last:
        return ("you're at your last offer (%s): say once that it's your limit, then walk away%s"
                % (euro(last), " (the seller wants %s)" % euro(counter) if counter else "")), last, "last"
    k = plan.index(later[0]) + 1
    return ("concede to %s (step %d of %d)%s%s" % (
        euro(later[0]), k, len(plan), ", not to the seller's %s" % euro(counter) if counter else "",
        ": your last offer, walk away above it" if later[0] == last else ""),
        later[0], "last" if later[0] == last else "counter")


def euro(x):
    return "€%s" % fmt(x)


def message(est, f, name=None, home=None, template=None, price=None, kind="first"):
    """The short German reply with an offer. kind "first": the opening offer, sent after the seller answered the
    opening questions, with how I'd pick it up; "counter": a step up after a no; "last": the last offer. `home`: the
    user's place (the `location` in the config) to say whether it's a trip; `template`: the user's own wording for the
    first offer with {offer} {pickup} {name}."""
    offer = "%s €" % fmt(est["open"] if price is None else price)
    if kind == "counter":
        text = "Danke dir! Treffen wir uns bei %s?" % offer
    elif kind == "last":
        text = "Danke dir! %s wäre mein letztes Angebot, mehr geht für mich leider nicht." % offer
    else:
        state = (f.get("state") or "").lower()
        near = bool(home and state and state.split()[0] in home.lower())
        town = (f.get("town") or "").strip()
        if near or not home:
            pickup = "Ich könnte diese Woche abholen."
        elif f.get("pickup_only") or not f.get("p2p"):
            pickup = "Ich würde zum Abholen nach %s kommen." % town if town else "Ich würde zum Abholen vorbeikommen."
        else:
            pickup = "Versand mit PayLivery wäre für mich ok, Abholung auch."
        if template:
            try:
                return template.replace("\\n", "\n").format(offer=offer, pickup=pickup, name=name or "")
            except (KeyError, IndexError, ValueError):
                pass                                       # a brace the template didn't mean: use the default
        text = "Danke für die Antwort! %s Wären %s ok?" % (pickup, offer)
    if name:
        text += "\nLg %s" % name
    return text
