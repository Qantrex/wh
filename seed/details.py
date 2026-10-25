import json, re, sys, time, urllib.request, os, html
from concurrent.futures import ThreadPoolExecutor

D = sys.argv[1]
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0"
todo = json.load(open(os.path.join(D, "detail_todo.json")))
outp = os.path.join(D, "details.json")
done = json.load(open(outp)) if os.path.exists(outp) else {}


def get(item):
    if item["id"] in done:
        return None
    for attempt in range(3):
        try:
            req = urllib.request.Request(item["url"], headers={"User-Agent": UA, "Accept-Language": "de-AT,de;q=0.9"})
            h = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
            ad = json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S).group(1))["props"]["pageProps"]["advertDetails"]
            at = {x["name"]: x["values"] for x in ad["attributes"]["attribute"]}
            desc = html.unescape(re.sub(r"<[^>]+>", " ", (at.get("DESCRIPTION") or [""])[0]))
            info = []
            for grp in ad.get("attributeInformation") or []:
                for v in grp.get("values", []) if isinstance(grp, dict) else []:
                    info.append(v)
            teaser = [(t.get("prefix") or "") + ":" + (t.get("value") or "") for t in ad.get("teaserAttributes") or []]
            time.sleep(1.0)
            return item["id"], {"desc": re.sub(r"\s+", " ", desc).strip(), "info": info, "teaser": teaser,
                                "first_published": ad.get("firstPublishedDate"), "status": (ad.get("advertStatus") or {}).get("id")}
        except Exception as e:
            print("retry", item["id"], attempt, e, file=sys.stderr)
            time.sleep(4 * (attempt + 1))
    return item["id"], {"error": True}


n = 0
with ThreadPoolExecutor(2) as ex:
    for r in ex.map(get, todo):
        if r:
            done[r[0]] = r[1]
            n += 1
            if n % 50 == 0:
                json.dump(done, open(outp, "w"), ensure_ascii=False)
                print("done", n, file=sys.stderr)
json.dump(done, open(outp, "w"), ensure_ascii=False)
print("finished", len(done), "errors", sum(1 for v in done.values() if v.get("error")), file=sys.stderr)
