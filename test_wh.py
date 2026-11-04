import gzip
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from unittest import mock

import sys

HERE = os.path.dirname(os.path.abspath(__file__))     # runnable from any folder: python3 path/to/test_wh.py
os.environ["WH_CONFIG"] = os.path.join(HERE, "no-such-config")   # before the imports: tests never read personal
os.environ.pop("WH_TEMPLATES", None)                             # settings or templates
for k in ("WH_NOTES", "WH_SKILL", "WH_DB", "WH_MODEL"):
    os.environ.pop(k, None)
sys.path.insert(0, HERE)
import profiles  # noqa: E402

loader = importlib.machinery.SourceFileLoader("wh_mod", os.path.join(HERE, "wh"))
spec = importlib.util.spec_from_loader("wh_mod", loader)
wh = importlib.util.module_from_spec(spec)
loader.exec_module(wh)


def next_page(obj):
    return '<html><head><script id="__NEXT_DATA__" type="application/json">%s</script></head></html>' % json.dumps(
        {"props": {"pageProps": obj}})


def make_summary(ad_id, heading, price, body="", seo="", cats="5824;5831", private="1", loc="Wien", state="Wien"):
    return {
        "id": str(ad_id),
        "description": heading,
        "attributes": {"attribute": [
            {"name": "HEADING", "values": [heading]},
            {"name": "PRICE", "values": [str(price)] if price is not None else []},
            {"name": "LOCATION", "values": [loc]},
            {"name": "STATE", "values": [state]},
            {"name": "POSTCODE", "values": ["1010"]},
            {"name": "ISPRIVATE", "values": [private]},
            {"name": "PUBLISHED_String", "values": ["2026-10-20T10:00:00Z"]},
            {"name": "SEO_URL", "values": [seo or ("kaufen-und-verkaufen/d/ad-%d/" % ad_id)]},
            {"name": "BODY_DYN", "values": [body]},
            {"name": "categorytreeids", "values": cats.split(";") if cats else []},
        ]},
    }


def search_page(found, ads):
    return next_page({"searchResult": {"rowsFound": found, "advertSummaryList": {"advertSummary": ads}}})


class FakeResp(io.BytesIO):
    def __init__(self, body, headers=None):
        super().__init__(body)
        self.headers = headers or {}
    def geturl(self): return "https://www.willhaben.at/ok"
    def __enter__(self): return self
    def __exit__(self, *a): pass


def make_detail_html(ad_id, title, price, descr="", status="active", images=None, info=None, old_price=None):
    attrs = [
        {"name": "PRICE", "values": [str(price)]},
        {"name": "ISPRIVATE", "values": ["1"]},
        {"name": "DESCRIPTION", "values": [descr]},
    ]
    if old_price is not None:
        attrs.append({"name": "OLD_PRICE", "values": [str(old_price)]})
    attr_info = [{"treeAttributeElement": {"label": k}, "values": [{"label": v}]} for k, v in (info or [])]
    return next_page({"advertDetails": {
        "id": str(ad_id),
        "description": title,
        "advertStatus": {"id": status},
        "firstPublishedDate": "2026-10-15T12:00:00Z",
        "changedDate": "2026-10-20T12:00:00Z",
        "endDate": "2026-11-15T12:00:00Z",
        "sellerProfileUserData": {"private": True, "name": "Seller", "registerDate": "2021-05-01", "activeAdCount": 3},
        "advertAddressDetails": {"postCode": "1010", "postalName": "Wien"},
        "attributes": {"attribute": attrs},
        "attributeInformation": attr_info,
        "advertImageList": {"advertImage": [{"referenceImageUrl": u} for u in (images or [])]},
    }})


class ProfilesTests(unittest.TestCase):
    def test_negated_defects_kept_while_real_defects_filtered(self):
        clean_cases = [
            "Technisch läuft alles einwandfrei, kein Defekt, keine Reparaturen.",
            "Keine Gebrauchsspuren, keine mir bekannten Defekte vorhanden!",
            "Im guten gebrauchten Zustand (keine Defekte), keine System Defekte.",
            "Sofort einsatzbereit - kein Bastlergerät, sondern ein Premium-System.",
            "Aus der iCloud entfernt, hat keine Aktivierungssperre.",
            "Die iCloud-/Aktivierungssperre („Wo ist?“) wurde ordnungsgemäß deaktiviert.",
            "Display defektfrei, SIM ungesperrt, kein Wasserschaden, kein MDM.",
            "iFlight Nazgul Komplettset + RC2 + Ersatzteile inklusive",
            "Akku kann bei Bedarf ersetzt werden, sofern ein passendes Ersatzteil gefunden wird.",
        ]
        for body in clean_cases:
            ad = {"id": 1, "title": "Laptop Test", "body": body, "price": 500}
            profiles.annotate([ad])
            self.assertIsNone(ad["junk"], msg=f"falsely flagged as junk: {body!r} -> {ad['junk']}")

        dirty_cases = [
            "Display defekt, sonst ok",
            "Kein Wasserschaden, aber Mainboard defekt!",
            "Fehlerhaft. Daher nicht als defekt inseriert, nur funktionseingeschränkt.",
            "Tasten sind nicht inkludiert weil die kaputt gegangen sind.",
            "Verkaufe Laptop als Ersatzteil / für Bastler",
            "Ersatzteilspender ohne Garantie",
            "Gerät hat BIOS-Passwort",
        ]
        for body in dirty_cases:
            ad = {"id": 1, "title": "Laptop Test", "body": body, "price": 200}
            profiles.annotate([ad])
            self.assertIsNotNone(ad["junk"], msg=f"missed real defect: {body!r}")

    def test_structured_condition_defekt_caught(self):
        ad = {"id": 1, "title": "Lenovo Laptop", "body": "Optisch schön", "price": 250, "info": ["Zustand: Defekt"]}
        profiles.annotate([ad], "laptop")
        self.assertEqual(ad["junk"], "says 'defekt'")

    def test_macbook_vs_windows_laptop_detection(self):
        # ASUS Zenbook mentioning MacBook & M3 in body must NOT become Apple M3 or Mac
        zen = {"id": 1, "title": "ASUS Zenbook 14", "body": "Verkaufe wegen Umstieg auf MacBook Air M3, OLED",
               "price": 750, "cats": "5824,5831"}
        alien = {"id": 2, "title": "Dell Alienware m15 R7 - Tausche gegen ein MacBook M4", "body": "RTX 3070 Ti",
                 "price": 950, "cats": "5824,5831"}
        omen = {"id": 3, "title": "HP Omen 16 I5 16DDR5 RTX 4060 8GB + Asus TUF Gaming M3 Mouse", "body": "",
                "price": 850, "cats": "5824,5831"}
        mac_space = {"id": 4, "title": "Mac Book Air 13 M2 16GB/512GB", "body": "", "price": 700, "cats": "5824,5831"}
        profiles.annotate([zen, alien, omen, mac_space], "laptop")
        self.assertIsNone(zen["cpu"])
        self.assertFalse(profiles.is_mac(zen))
        self.assertIsNone(alien["cpu"])
        self.assertFalse(profiles.is_mac(alien))
        self.assertIsNone(omen["cpu"])
        self.assertEqual(omen["ram"], 16)
        self.assertEqual(mac_space["cpu"], "Apple M2")
        self.assertEqual(mac_space["ram"], 16)
        self.assertTrue(profiles.is_mac(mac_space))

    def test_apple_chip_lists_are_comparisons_not_the_spec(self):
        intel = {"id": 1, "title": "MacBook Pro *32GB RAM*1TB SSD*", "price": 549, "cats": "5824,5831",
                 "body": "Macbook Pro 13 32GB Ram 1TB SSD. Gleichwertig wie ein M1, M2, M3, M4"}
        cmp_ = {"id": 2, "title": "MacBook Pro 13 2020 i5", "price": 400, "cats": "5824,5831",
                "body": "so schnell, vergleichbar mit einem M2"}
        air = {"id": 3, "title": "MacBook Air 13 M4 16GB", "price": 850, "cats": "5824,5831", "body": "neuwertig"}
        pro = {"id": 4, "title": "MacBook Pro 14 M1 Pro 16/512", "price": 650, "cats": "5824,5831", "body": ""}
        profiles.annotate([intel, cmp_, air, pro], "laptop")
        self.assertNotIn("Apple", intel["cpu"] or "")
        self.assertNotIn("Apple", cmp_["cpu"] or "")
        self.assertEqual(air["cpu"], "Apple M4")
        self.assertEqual(pro["cpu"], "Apple M1 Pro/Max")

    def test_cpu_gpu_ram_and_desktop_part_edge_cases(self):
        ads = [
            {"id": 1, "title": "HP EliteBook 865 G10 | Ryzen 7 Pro 32GB 512GB SSD | GARANTIE",
             "body": "AMD Ryzen 7 PRO 7840U", "price": 819, "cats": "5824,5831"},
            {"id": 2, "title": "Lenovo ThinkPad T14s Gen 5 | Ultra 7 | 32GB RAM | Premier Garantie",
             "body": "", "price": 830, "cats": "5824,5831"},
            {"id": 3, "title": "Lenovo ThinkPad T14s Gen 3 - AMD Ryzen 5 PRO 6650U, 16 GB RAM",
             "body": "", "price": 449, "cats": "5824,5831"},
            {"id": 4, "title": "Gaming Laptop i7, RTX 3060", "body": "Inter i7 12.700h, 16 GB DDR4 Arbeitsspeicher",
             "price": 600, "cats": "5824,5831"},
            {"id": 5, "title": "Apple MacBook Air M3 (2024) - 8GB/256GB", "body": "", "price": 750, "cats": "5824,5831"},
            {"id": 6, "title": "Dell Precision 5470 | i7-12800H | 32GB | 1TB SSD | RTX A1000",
             "body": "Wegen Umstieg auf Desktop PC abzugeben", "price": 800, "cats": "5824,5831"},
            {"id": 7, "title": "SSD 1TB, RAM 32GB, CLEVO, i7-8700K Desktop, GTX 1080, notebook",
             "body": "", "price": 299, "cats": "5824,5831"},
            {"id": 8, "title": "Akku für Lenovo ThinkPad T14", "body": "", "price": 45, "cats": "5824,5831"},
            {"id": 9, "title": "Gaming Laptop RTX 4060 8GB", "body": "RTX 4060 8GB / 512GB SSD",
             "price": 700, "cats": "5824,5831"},
        ]
        profiles.annotate(ads, "laptop")
        by_id = {a["id"]: a for a in ads}
        self.assertEqual(by_id[1]["cpu"], "Ryzen 7040U")
        self.assertEqual(by_id[1]["ram"], 32)
        self.assertEqual(by_id[2]["cpu"], "Core Ultra")
        self.assertEqual(by_id[3]["cpu"], "Ryzen 6000U")
        self.assertEqual(by_id[4]["cpu"], "Intel 12th H")
        self.assertEqual(by_id[5]["ram"], 8)                   # 8GB MacBook gets -1 penalty, not None
        self.assertIsNone(by_id[6]["junk"])                    # Dell Precision in 5831 kept despite "Desktop" in body
        self.assertEqual(by_id[6]["gpu"], "RTX A1000")
        self.assertEqual(by_id[6]["ram"], 32)
        self.assertIsNone(by_id[7]["junk"])
        self.assertEqual(by_id[8]["junk"], "part, not a laptop")
        self.assertIsNone(by_id[9]["ram"])                     # GPU 8GB VRAM before / 512GB not mistaken for system RAM

    def test_shortlist_interleaves_all_five_goals_in_top_15(self):
        ads = []
        for i in range(6):
            ads.append({"id": 100 + i, "title": f"Nitro 5 #{i}", "body": "i5-12500H RTX 3060 16GB RAM",
                        "price": 450 + i * 20, "cats": "5831"})
            ads.append({"id": 200 + i, "title": f"ThinkPad T14s #{i}", "body": "Ryzen 7 PRO 7840U 32GB RAM",
                        "price": 750 + i * 20, "cats": "5831"})
            ads.append({"id": 300 + i, "title": f"Dell XPS 15 #{i}", "body": "i7-13700H RTX 4060 32GB RAM OLED",
                        "price": 900 + i * 20, "cats": "5831"})
            ads.append({"id": 400 + i, "title": f"MacBook Air M3 #{i}", "body": "M3 16GB RAM",
                        "price": 800 + i * 20, "cats": "5831"})
            ads.append({"id": 500 + i, "title": f"Gaming Laptop #{i}", "body": "RTX 3050 Ti 16GB RAM",
                        "price": 400 + i * 20, "cats": "5831"})
        profiles.annotate(ads, "laptop")
        short = profiles.shortlist(ads, "laptop", 40)
        top15_groups = {a["id"] // 100 for a in short[:15]}
        self.assertEqual(top15_groups, {1, 2, 3, 4, 5})


class TmpDbCase(unittest.TestCase):
    """A fresh database per test; requests in order, without waiting."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "wh.db")
        self.orig = (wh.DB, wh.DELAY, wh.RATE, wh.WORKERS)
        wh.DB, wh.DELAY, wh.RATE, wh.WORKERS = self.db_path, 0.0, 0, 1   # in order, no waiting
        wh._slow[0], wh._next[0] = False, 0.0

    def tearDown(self):
        wh.DB, wh.DELAY, wh.RATE, wh.WORKERS = self.orig
        wh._slow[0], wh._next[0] = False, 0.0
        self.tmp.cleanup()


class WhTests(TmpDbCase):
    def test_search_url_preserves_repeated_query_params(self):
        u = "https://www.willhaben.at/iad/kaufen-und-verkaufen/marktplatz/laptops-5824?areaId=900&areaId=3&page=4"
        out = wh.search_url(words="thinkpad", pmax=900, url=u)
        self.assertIn("areaId=900&areaId=3", out)
        self.assertIn("keyword=thinkpad", out)
        self.assertIn("PRICE_TO=900", out)
        self.assertIn("rows=200", out)
        self.assertNotIn("page=", out)

    def test_fetch_decompresses_gzip(self):
        payload = gzip.compress(b"hello willhaben")

        class FakeResp(io.BytesIO):
            headers = {"Content-Encoding": "gzip"}
            def geturl(self): return "https://www.willhaben.at/ok"
            def __enter__(self): return self
            def __exit__(self, *a): pass

        with mock.patch("urllib.request.urlopen", return_value=FakeResp(payload)):
            _, text = wh.fetch("https://www.willhaben.at/ok")
        self.assertEqual(text, "hello willhaben")

    def test_comp_words_keeps_digits_and_strips_seller_noise(self):
        self.assertEqual(wh.comp_words("Preis Fix! Apple MacBook Air 15 M4 16GB"), "apple macbook air 15")
        self.assertEqual(wh.comp_words("(reserviert) Apple Mac mini M4 16GB"), "apple mac mini m4")
        self.assertEqual(wh.comp_words("Lenovo Legion 5 Gaming Laptop"), "lenovo legion 5 gaming")
        self.assertEqual(wh.comp_words("Suche: Alpinestars SMX-1 Air v2"), "alpinestars smx 1 air")

    def test_table_escapes_brackets_and_omits_empty_specs_without_profile(self):
        ads = [{"id": 1234567, "price": 700.0, "title": "MacBook Air M2 [16GB, 256GB]", "loc": "Wien",
                "private": 1, "published": "2026-10-25", "url": "https://www.willhaben.at/iad/d/x-1234567/",
                "cpu": "Apple M2", "gpu": "RTX 3050", "ram": 16, "hz": 144}]
        md_plain = wh.table(ads, profile=None, md=True)
        self.assertNotIn("Specs", md_plain)
        self.assertIn("[MacBook Air M2 (16GB, 256GB)](https://www.willhaben.at/iad/d/x-1234567/)", md_plain)

        md_laptop = wh.table(ads, profile="laptop", md=True)
        self.assertIn("Specs", md_laptop)
        self.assertIn("RTX 3050 · Apple M2 · 16 GB · 144 Hz", md_laptop)  # not truncated at 30 chars

    def test_run_search_incomplete_when_search_result_missing(self):
        c = wh.db()
        self.addCleanup(c.close)
        with mock.patch.object(wh, "fetch", return_value=("https://x", "<html>blocked</html>")), \
             mock.patch.object(wh, "log"):
            ads, found, complete = wh.run_search(c, "https://www.willhaben.at/s?rows=200", pages=2, key="k1")
        self.assertEqual(ads, [])
        self.assertEqual(found, 0)
        self.assertFalse(complete)

    def test_details_preserves_cached_data_and_photos_when_offline(self):
        c = wh.db()
        self.addCleanup(c.close)
        online_html = make_detail_html(9999991, "DJI Goggles V2", 185, descr="Top Brille",
                                       images=["https://cache.willhaben.at/img1.webp"])
        with mock.patch.object(wh, "fetch", return_value=("https://www.willhaben.at/iad/d/goggles-9999991/", online_html)):
            d1 = wh.details(c, 9999991, refresh=True)
        self.assertEqual(d1["status"], "active")
        self.assertEqual(d1["images"], ["https://cache.willhaben.at/img1.webp"])

        with mock.patch.object(wh, "fetch", return_value=("https://www.willhaben.at/iad/search", "")):
            d2 = wh.details(c, 9999991, refresh=True)
        self.assertEqual(d2["status"], "offline")
        self.assertEqual(d2["title"], "DJI Goggles V2")
        self.assertEqual(d2["images"], ["https://cache.willhaben.at/img1.webp"])
        self.assertIn("DJI Goggles V2", wh.fmt_details(d2, c))

        # cmd_photos still downloads cached CDN image and survives missing magick
        webp_bytes = b"RIFF\x10\x00\x00\x00WEBPVP8 "
        photo_dir = os.path.join(self.tmp.name, "photos")
        ns = mock.Mock(ad="9999991", dir=photo_dir)

        def fake_fetch(url, binary=False):
            return (url, webp_bytes) if binary else (url, "")

        with mock.patch.object(wh, "fetch", side_effect=fake_fetch), \
             mock.patch.object(wh, "db", return_value=c), \
             mock.patch("subprocess.run", side_effect=FileNotFoundError), \
             mock.patch("sys.stdout", new_callable=io.StringIO):
            wh.cmd_photos(ns)
        self.assertTrue(os.path.exists(os.path.join(photo_dir, "9999991-01.webp")))

    def test_a_page_without_ad_data_is_an_error_not_an_offline_ad(self):
        c = wh.db()
        self.addCleanup(c.close)
        with mock.patch.object(wh, "fetch", return_value=("u", make_detail_html(4242424, "Item", 50))):
            wh.details(c, 4242424, refresh=True)
        for page in ("<html><h1>Wartungsarbeiten</h1></html>",
                     '<script id="__NEXT_DATA__" type="application/json">{"props": </script>',
                     '<script id="__NEXT_DATA__" type="application/json">{"other": 1}</script>'):
            with mock.patch.object(wh, "fetch", return_value=("u", page)):
                with self.assertRaises(wh.FetchError):
                    wh.details(c, 4242424, refresh=True)
        cached = json.loads(c.execute("select data from details where id=4242424").fetchone()[0])
        self.assertEqual(cached["status"], "active")             # the cache still says what was last known
        with mock.patch.object(wh, "fetch", return_value=("u", "<html>maintenance</html>")), \
             mock.patch.object(wh, "log"):
            self.assertIsNone(wh.read_page("https://x?rows=200&page=1"))

    def test_status_reports_a_bad_ad_property_and_checks_the_other_notes(self):
        notes = os.path.join(self.tmp.name, "notes")
        os.makedirs(notes)
        for name, ad in (("Bad", "see chat"), ("Good", "1234567")):
            with open(os.path.join(notes, name + ".md"), "w", encoding="utf-8") as f:
                f.write("---\ntype: sell\nstatus: live\nad: %s\n---\n" % ad)
        c = wh.db()
        self.addCleanup(c.close)
        out = io.StringIO()
        with mock.patch.object(wh, "db", return_value=c), mock.patch.object(wh, "NOTES", notes), \
             mock.patch.object(wh, "fetch", return_value=("u", make_detail_html(1234567, "Item", 40))), \
             mock.patch("sys.stdout", out):
            wh.cmd_status(mock.Mock(notes=[], dry_run=True))
        self.assertIn("no willhaben ad id in 'see chat'", out.getvalue())
        self.assertRegex(out.getvalue(), r"Good\s+active\s+€40")

    def test_sweep_note_multi_search_dedupes_and_preserves_was_price(self):
        c = wh.db()
        self.addCleanup(c.close)
        note_path = os.path.join(self.tmp.name, "Laptop.md")
        props = {"search": ["rtx", "thinkpad"], "wh-profile": "laptop"}

        # Sweep 1: ad 1001 (€700, in both searches), ad 1002 (€600, will vanish in sweep 2)
        s1_rtx = next_page({"searchResult": {"rowsFound": 2, "advertSummaryList": {"advertSummary": [
            make_summary(1001, "Lenovo ThinkPad P14s RTX A2000", 700, "i7-1260P 16GB RAM"),
            make_summary(1002, "Acer Nitro 5 RTX 3050", 600, "i5-11400H 16GB RAM"),
        ]}}})
        s1_tp = next_page({"searchResult": {"rowsFound": 1, "advertSummaryList": {"advertSummary": [
            make_summary(1001, "Lenovo ThinkPad P14s RTX A2000", 700, "i7-1260P 16GB RAM"),
        ]}}})
        with mock.patch.object(wh, "fetch", side_effect=[("u", s1_rtx), ("u", s1_tp)]), \
             mock.patch.object(wh, "now", return_value="2026-10-24T10:00:00Z"), \
             mock.patch.object(wh, "log"):
            wh.sweep_note(c, note_path, props, pages=1, limit=10)

        # Simulate an unrelated `wh search` seeing the price cut to €620 BEFORE sweep 2 runs!
        inter_search = next_page({"searchResult": {"rowsFound": 1, "advertSummaryList": {"advertSummary": [
            make_summary(1001, "Lenovo ThinkPad P14s RTX A2000", 620, "i7-1260P 16GB RAM"),
        ]}}})
        with mock.patch.object(wh, "fetch", return_value=("u", inter_search)), \
             mock.patch.object(wh, "now", return_value="2026-10-25T09:00:00Z"), \
             mock.patch.object(wh, "log"):
            wh.run_search(c, wh.search_url("p14s"), pages=1)

        # Sweep 2: ad 1001 cut €700 -> €620 (in both searches), ad 1003 new (in both searches), ad 1002 gone
        s2 = next_page({"searchResult": {"rowsFound": 2, "advertSummaryList": {"advertSummary": [
            make_summary(1001, "Lenovo ThinkPad P14s RTX A2000", 620, "i7-1260P 16GB RAM"),
            make_summary(1003, "Lenovo ThinkPad X1 RTX 3050", 800, "i7-12700H 32GB RAM"),
        ]}}})
        with mock.patch.object(wh, "fetch", side_effect=[("u", s2), ("u", s2)]), \
             mock.patch.object(wh, "now", return_value="2026-10-25T10:00:00Z"), \
             mock.patch.object(wh, "log"):
            block, short, good, _ = wh.sweep_note(c, note_path, props, pages=1, limit=10)

        self.assertIn("1 new · 1 price cuts · 1 gone", block)
        self.assertIn("| €620 | €700 |", block)                # Was column shows €700, NOT clobbered €620!

    def test_last_prices_reads_only_the_asked_ads_up_to_a_time(self):
        c = wh.db()
        self.addCleanup(c.close)
        c.executemany("insert into prices values (?,?,?)", [
            (1, 100, "2026-10-01T10:00:00Z"), (1, 90, "2026-10-02T10:00:00Z"), (1, 80, "2026-10-03T10:00:00Z"),
            (2, 50, "2026-10-01T10:00:00Z"), (3, 70, "2026-10-01T10:00:00Z")])
        self.assertEqual(wh.last_prices(c, {1, 2}, "2026-10-02T10:00:00Z"), {1: 90, 2: 50})
        self.assertEqual(wh.last_prices(c, set(range(1, 1200)), "2026-10-01T10:00:00Z"), {1: 100, 2: 50, 3: 70})

    def test_sweep_note_detail_enrichment_filters_offline_and_updates_specs(self):
        c = wh.db()
        self.addCleanup(c.close)
        note_path = os.path.join(self.tmp.name, "Laptop.md")
        props = {"search": ["rtx"], "wh-profile": "laptop"}
        sr = next_page({"searchResult": {"rowsFound": 2, "advertSummaryList": {"advertSummary": [
            make_summary(2001, "Acer Nitro 5 Gaming Laptop", 450, "RTX 3060"),
            make_summary(2002, "Dead Laptop", 400, "RTX 3060 i5-11400H"),
        ]}}})
        det_2001 = make_detail_html(2001, "Acer Nitro 5 Gaming Laptop", 450,
                                    descr="Intel i5-12500H, 16 GB RAM, 144 Hz Display, top Zustand!")

        def fake_fetch(url, binary=False):
            if "adId=2001" in url:
                return (url, det_2001)
            if "adId=2002" in url:
                return (url, "")                               # 2002 expired!
            return (url, sr)

        with mock.patch.object(wh, "fetch", side_effect=fake_fetch), mock.patch.object(wh, "log"):
            block, short, _, _ = wh.sweep_note(c, note_path, props, pages=1, limit=10, detail_count=5)

        self.assertEqual([x["id"] for x in short], [2001])     # offline 2002 dropped from both short and sweep block
        self.assertNotIn("Dead Laptop", block)
        self.assertIn("RTX 3060 · Intel 12th H · 16 GB · 144 Hz", block)

    def test_note_frontmatter_comments_and_atomic_write(self):
        p = os.path.join(self.tmp.name, "Item.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(
                "---\n"
                "type: sell # inline comment\n"
                "price: 185  # lowered from 200\n"
                "search:\n"
                "  - https://www.willhaben.at/iad/marktplatz?keyword=foo#frag\n"
                "---\nBody\n"
            )
        os.chmod(p, 0o640)
        text, props = wh.read_note(p)
        self.assertEqual(props["type"], "sell")
        self.assertEqual(wh.num(props["price"]), 185.0)
        self.assertEqual(props["search"], ["https://www.willhaben.at/iad/marktplatz?keyword=foo#frag"])
        wh.write_note(p, wh.put_block(text, "sweep", "## Sweep\n\nok"))
        self.assertEqual(os.stat(p).st_mode & 0o777, 0o640)
        text2, props2 = wh.read_note(p)
        self.assertIn("updated", props2)
        self.assertIn("<!-- wh:sweep -->", text2)

    def test_find_notes_skips_hidden_folders_and_unreadable_notes(self):
        notes = os.path.join(self.tmp.name, "vault")
        for sub in ("Buying", ".trash", ".obsidian"):
            os.makedirs(os.path.join(notes, sub))
        for sub in ("Buying", ".trash"):
            with open(os.path.join(notes, sub, "Laptop.md"), "w", encoding="utf-8") as f:
                f.write("---\ntype: buy\nstatus: open\n---\n")
        with open(os.path.join(notes, "Buying", "Latin1.md"), "wb") as f:
            f.write(b"---\ntype: buy\n---\nK\xe4se\n")
        with mock.patch.object(wh, "NOTES", notes), mock.patch.object(wh, "log") as log:
            self.assertEqual([f for f, *_ in wh.find_notes([])], [os.path.join(notes, "Buying", "Laptop.md")])
            self.assertEqual(len(wh.find_notes(["laptop"])), 1)          # by name: not the deleted copy either
        self.assertIn("Latin1.md", log.call_args[0][0])

    def test_frontmatter_edge_cases_never_get_a_second_frontmatter(self):
        self.assertEqual(wh.set_prop("---\n---\nBody\n", "checked", "2026-11-04"), "---\nchecked: 2026-11-04\n---\nBody\n")
        self.assertEqual(wh.set_prop("---\ntype: buy\n---", "checked", "x"), "---\ntype: buy\nchecked: x\n---\n")
        self.assertEqual(wh.set_prop("---\r\ntype: buy\r\n---\r\nB", "type", "sell").count("---"), 2)
        self.assertEqual(wh.FM.match("---\ntype: buy\n---").group(1), "type: buy\n")
        self.assertEqual(wh.set_prop("# no props\n", "a", "1"), "---\na: 1\n---\n# no props\n")
        text = "---\na: 1\n---\nBody\n\n---\n\nmore"                  # a horizontal rule later stays text
        self.assertEqual(wh.set_prop(text, "b", "2"), "---\na: 1\nb: 2\n---\nBody\n\n---\n\nmore")

    def test_put_block_ignores_a_stray_end_marker_before_the_block(self):
        text = "Uses <!-- /wh:sweep --> as marker.\n\n<!-- wh:sweep -->\nold\n<!-- /wh:sweep -->\n"
        once = wh.put_block(text, "sweep", "new")
        self.assertEqual(once, "Uses <!-- /wh:sweep --> as marker.\n\n<!-- wh:sweep -->\nnew\n<!-- /wh:sweep -->\n")
        self.assertEqual(wh.put_block(once, "sweep", "new"), once)       # no copy appended on every sweep

    def test_hunt_keeps_edits_made_while_claude_thinks_and_symlinks_stay(self):
        real = os.path.join(self.tmp.name, "real.md")
        link = os.path.join(self.tmp.name, "Goggles.md")
        with open(real, "w", encoding="utf-8") as f:
            f.write("---\ntype: buy\nstatus: open\nfor: me\nsearch: goggles\n---\n# Goggles\n")
        os.symlink(real, link)
        page = search_page(1, [make_summary(1, "DJI Goggles V2", 180)])

        def claude_while_the_owner_types(a, task, data, rules="buy"):
            with open(link, "a", encoding="utf-8") as f:
                f.write("\nAsked the seller about the battery.\n")
            return "## Picks\n\n1. Goggles\n"
        c = wh.db()
        self.addCleanup(c.close)
        ns = mock.Mock(note=link, pages=1, limit=10, details=0, dry_run=False, no_ai=False)
        with mock.patch.object(wh, "db", return_value=c), mock.patch.object(wh, "fetch", return_value=("u", page)), \
             mock.patch.object(wh, "ask_claude", side_effect=claude_while_the_owner_types), \
             mock.patch.object(wh, "log"), mock.patch("sys.stdout", io.StringIO()):
            wh.cmd_hunt(ns)
        self.assertTrue(os.path.islink(link))
        saved, props = wh.read_note(link)
        self.assertIn("Asked the seller about the battery.", saved)
        self.assertIn("<!-- wh:picks -->", saved)
        self.assertIn("<!-- wh:sweep -->", saved)
        self.assertEqual(props["for"], "me")

    def test_cmd_hunt_formats_metadata_and_splits_warnings_resiliently(self):
        note_path = os.path.join(self.tmp.name, "Laptop.md")
        with open(note_path, "w", encoding="utf-8") as f:
            f.write("---\ntype: buy\nstatus: open\nsearch: rtx\nwh-profile: laptop\n---\n# Laptop\n")

        sr = next_page({"searchResult": {"rowsFound": 1, "advertSummaryList": {"advertSummary": [
            make_summary(3001, "Lenovo Legion 5 RTX 3060", 500, "Ryzen 7 5800H 16GB RAM"),
        ]}}})
        det = make_detail_html(
            3001, "Lenovo Legion 5 RTX 3060", 500,
            descr="Sehr gepflegt, 165 Hz WQHD Display, kein Defekt. " + ("Details " * 120),
            status="reserved", old_price=580,
            info=[("Zustand", "Gebraucht"), ("Übergabe", "Selbstabholung")],
        )
        captured = {}

        def fake_fetch(url, binary=False):
            return (url, det) if "adId=3001" in url else (url, sr)

        def fake_claude(a, task, data, *headings):
            captured["data"] = data
            return "Sure, here are the results:\n### Picks\n1. **€500 Legion 5**\n### Warnings: watch out\n- Reserved ad"

        c = wh.db()
        self.addCleanup(c.close)
        ns = mock.Mock(note=note_path, pages=1, limit=10, details=5, dry_run=False, no_ai=False)
        out = io.StringIO()
        with mock.patch.object(wh, "db", return_value=c), \
             mock.patch.object(wh, "fetch", side_effect=fake_fetch), \
             mock.patch.object(wh, "ask_claude", side_effect=fake_claude), \
             mock.patch.object(wh, "log"), \
             mock.patch("sys.stdout", out):
            wh.cmd_hunt(ns)

        self.assertIn("## Who it's for\n\nNot stated. Don't assume it's for me", captured["data"])
        self.assertIn("STATUS: reserved", captured["data"])
        self.assertIn("cut from €580", captured["data"])
        self.assertIn("Übergabe: Selbstabholung", captured["data"])
        self.assertIn("165 Hz", captured["data"])
        saved, _ = wh.read_note(note_path)
        self.assertIn("<!-- wh:picks -->", saved)
        self.assertIn("1. **€500 Legion 5**", saved)
        self.assertNotIn("Warnings", saved)
        self.assertIn("## Warnings (not written to the note)", out.getvalue())

    def test_pc_profile_filters_parts_swap_and_no_gpu_traps(self):
        ads = [
            {"id": 1, "title": "Gaming PC RTX 3060 12GB Ryzen 5 5600 32GB DDR4", "price": 520,
             "body": "1TB NVMe SSD", "cats": "5824;5828;5833"},
            {"id": 2, "title": "Einsteiger PC ( Tausch gegen Gaming Laptop möglich )", "price": 220,
             "body": "Tasch gegen Gaming Laptop ( RTX 3050 ) Grafikkarte: GTX 1060 6GB VRAM, i7 4790, 16 GB RAM",
             "cats": "5824;5828;5833"},
            {"id": 3, "title": "High-End Gaming PC OHNE Grafikkarte (war mit RTX 4080)", "price": 600,
             "body": "Ryzen 7 7700X, 32GB DDR5, Verkauf ohne Grafikkarte", "cats": "5824;5828;5833"},
            {"id": 4, "title": "GeForce RTX 3060 12gb", "price": 210, "body": "Grafikkarte", "cats": "5824;5878;5882"},
            {"id": 5, "title": "Gaming monitor", "price": 150, "body": "MSI 32 Zoll WQHD", "cats": "5824;5828;5833"},
        ]
        profiles.annotate(ads, "pc")
        self.assertIsNone(ads[0]["junk"])
        self.assertEqual((ads[0]["gpu"], ads[0]["cpu"], ads[0]["ram"], ads[0]["vram"]),
                         ("RTX 3060", "Ryzen 5 5600", 32, "12 GB VRAM"))
        self.assertIsNone(ads[1]["junk"])
        self.assertEqual(ads[1]["gpu"], "GTX 1060")            # swap wish "RTX 3050" ignored!
        self.assertEqual(ads[1]["vram"], "6 GB VRAM")
        self.assertIsNone(ads[2]["gpu"])                       # "ohne Grafikkarte" clears GPU
        self.assertIsNotNone(ads[3]["junk"])                   # GPU component category rejected
        self.assertIsNotNone(ads[4]["junk"])                   # mis-categorized monitor rejected
        short = profiles.shortlist(ads, "pc", 5)
        self.assertEqual(short[0]["id"], 1)

        # Real-world collisions: DDR4-3600 != Ryzen 3600, i7-7700 != Ryzen 7700, RX 5700 != Ryzen 5700,
        # "RTX 5060 / 32 GB DDR4" != 32 GB VRAM, "2x8GB DDR4" == 16 GB RAM, loose GPU in 5833 rejected
        tricky = [
            {"id": 6, "title": "Mini-ITX PC - Intel i7-10700K + ASUS TUF RTX 3080 + 32 GB DDR4-3600", "price": 1100,
             "body": "RTX 3080 O10G (10 GB), 2x16 GB Corsair", "cats": "5824;5828;5833"},
            {"id": 7, "title": "Gaming-PC - Ryzen 7 5700X / RTX 5060 / 32 GB DDR4", "price": 800,
             "body": "1 TB SSD", "cats": "5824;5828;5833"},
            {"id": 8, "title": "Gaming PC", "price": 300, "body": "Rtx 2060 6gb - i7 7700 - Corsair 2x8GB DDR4",
             "cats": "5824;5828;5833"},
            {"id": 9, "title": "Gaming PC Ryzen + Radeon", "price": 405,
             "body": "AMD Ryzen 5 2400G, AMD Radeon RX 5700 XT mit 8 GB VRAM, 16 GB RAM", "cats": "5824;5828;5833"},
            {"id": 15, "title": "Rtx 3060 12gb 1 year old", "price": 310,
             "body": "Ich verkaufe meine Gigabyte Grafikkarte", "cats": "5824;5828;5833"},
        ]
        profiles.annotate(tricky, "pc")
        self.assertEqual((tricky[0]["cpu"], tricky[0]["vram"], tricky[0]["ram"]), ("Intel 10th", "10 GB VRAM", 32))
        self.assertEqual((tricky[1]["cpu"], tricky[1]["vram"]), ("Ryzen 7 5700/5800", "8 GB VRAM"))
        self.assertEqual((tricky[2]["cpu"], tricky[2]["ram"]), ("Intel 6/7th", 16))
        self.assertEqual((tricky[3]["cpu"], tricky[3]["gpu"]), ("Ryzen 2400G-4600G", "RX 5700 XT"))
        self.assertIsNotNone(tricky[4]["junk"])

    def test_server_profile_classifies_tiny_nas_and_filters_parts(self):
        ads = [
            {"id": 10, "title": "Lenovo ThinkCentre M720q Tiny i5-8500T 16GB RAM 256GB NVMe", "price": 140,
             "body": "Inkl. Netzteil", "cats": "5824;5828;5833"},
            {"id": 11, "title": "Synology DiskStation DS920+ NAS", "price": 320,
             "body": "8GB RAM, 4-Bay NAS ohne Festplatten", "cats": "5824;5871;5873"},
            {"id": 12, "title": "HP Proliant DL 360 Gen9 Barebone", "price": 50,
             "body": "Rackserver ohne HDDs, ohne RAM, ohne CPU und ohne Netzgerät", "cats": "5824;5871;5875"},
            {"id": 13, "title": "4x HP 600GB SAS 10K Festplatten inkl. Rahmen für ProLiant", "price": 50,
             "body": "Serverfestplatten", "cats": "5824;5871;5875"},
            {"id": 14, "title": "Synology ECC RAM DDR4 4GB", "price": 25, "body": "aus DS1821+", "cats": "5824;5878;5887"},
        ]
        profiles.annotate(ads, "server")
        self.assertIsNone(ads[0]["junk"])
        self.assertEqual((ads[0]["form"], ads[0]["cpu"], ads[0]["ram"]), ("Tiny/Mini", "Intel i5/i7 8/9th", 16))
        self.assertIsNone(ads[1]["junk"])
        self.assertEqual((ads[1]["form"], ads[1]["cpu"], ads[1]["bays"]), ("NAS", "Celeron J4xxx (x86)", "4-bay"))
        self.assertIsNotNone(ads[2]["junk"])                   # stripped chassis without CPU & PSU
        self.assertIsNotNone(ads[3]["junk"])                   # loose SAS drives
        self.assertIsNotNone(ads[4]["junk"])                   # loose RAM module

    def test_hue_profile_filters_humidifiers_clones_and_v1_bridges(self):
        ads = [
            {"id": 20, "title": "Philips Hue Dimmer Switch V2 + Wandhalterung", "price": 14,
             "body": "RWL022 neuwertig"},
            {"id": 21, "title": "3x Philips Hue White & Color Ambiance E27 1100lm OVP", "price": 55,
             "body": "Originalverpackt"},
            {"id": 22, "title": "Philips 2000 Series HU4811/10 Luftbefeuchter", "price": 10, "body": "Mit Filter"},
            {"id": 23, "title": "Smarthome bewegungsmelder aqara", "price": 10, "body": "Zigbee wie Philips Hue"},
            {"id": 24, "title": "Philips Hue Bridge", "price": 5, "body": "Bridge der I Generation rund"},
            {"id": 25, "title": "Abdeckung für Philips Hue Smart Button", "price": 5, "body": "Neu"},
            {"id": 26, "title": "Philips Hue Bridge V2", "price": 10, "body": "Eckige Bridge zurückgesetzt"},
        ]
        profiles.annotate(ads, "hue")
        self.assertIsNone(ads[0]["junk"])
        self.assertEqual(ads[0]["kind"], "Dimmer V2")
        self.assertIsNone(ads[1]["junk"])
        self.assertEqual((ads[1]["kind"], ads[1]["qty"]), ("Bulb", "3×"))
        self.assertIn("E27", ads[1]["spec"])
        self.assertIn("Color", ads[1]["spec"])
        for j in (22, 23, 24, 25):
            ad = next(x for x in ads if x["id"] == j)
            self.assertIsNotNone(ad["junk"], msg="Expected %d to be junk" % j)
        short = profiles.shortlist(ads, "hue", 2)
        self.assertEqual({x["id"] for x in short}, {20, 21})   # standalone Bridge V2 doesn't crowd out controls & bulbs

    def test_hue_lamps_with_a_dimmer_power_supplies_and_gateway_bundles(self):
        ads = [
            {"id": 30, "title": "(NEU) Philips Hue White Ambiance Runner Spot 1 flg. weiß inkl. Dimmschalter in OVP",
             "price": 74, "body": ""},
            {"id": 31, "title": "Philips Hue White Ambiance Being Pendelleuchte weiß 2750lm inkl. Dimmschalter",
             "price": 130, "body": ""},
            {"id": 32, "title": "Philips Hue Niedervolt-Netzteile Outdoor 40 Watt", "price": 35,
             "body": "7 Stück vorhanden, für Lily und Calla"},
            {"id": 33, "title": "* Philips Hue Gateway mit 2 Lampen und Lichtband *", "price": 80, "body": ""},
            {"id": 34, "title": "Philips Hue Base Station 2.1 + 3x Dimmer", "price": 50, "body": ""},
            {"id": 35, "title": "Philips Hue Dimmschalter mit Glühbirnen", "price": 90, "body": "2x GU10"},
            {"id": 36, "title": "Philips Hue Dimmer Switch V2 9290023986 mit Wandhalterung", "price": 15, "body": ""},
            {"id": 37, "title": "Stehlampe Schwarz/Gold inkl. Philips Hue Color Big Studio", "price": 90, "body": ""},
        ]
        profiles.annotate(ads, "hue")
        kind = {a["id"]: a["kind"] for a in ads}
        self.assertEqual((kind[30], kind[31]), ("Lamp", "Lamp"))
        self.assertIsNotNone(ads[2]["junk"])                   # a power supply isn't a light
        self.assertEqual((kind[33], kind[34], kind[35]), ("Bundle", "Bundle", "Bundle"))
        self.assertEqual(kind[36], "Dimmer V2")                # a wall plate is an add-on, still the dimmer
        self.assertEqual(kind[37], "Lamp")


class FetchSweepTests(TmpDbCase):
    def sweep(self, c, props, pages_by_keyword, pages=1, record=True):
        """sweep_note() against fake search pages: {keyword: html or exception}."""
        def fake_fetch(url, binary=False):
            r = next(v for k, v in pages_by_keyword.items() if "keyword=" + k in url)
            if isinstance(r, Exception):
                raise r
            return url, r
        with mock.patch.object(wh, "fetch", side_effect=fake_fetch), mock.patch.object(wh, "log"):
            return wh.sweep_note(c, os.path.join(self.tmp.name, "Note.md"), props, pages, 10, record=record)

    def test_dry_run_leaves_no_run_so_new_ads_stay_new(self):
        c = wh.db()
        self.addCleanup(c.close)
        props = {"search": ["goggles"]}
        a, b, n = (make_summary(i, "DJI Goggles V2 #%d" % i, 150 + i) for i in (1, 2, 3))
        self.sweep(c, props, {"goggles": search_page(2, [a, b])})
        block, *_ = self.sweep(c, props, {"goggles": search_page(3, [a, b, n])}, record=False)
        self.assertIn("1 new", block)
        self.assertEqual(c.execute("select count(*) from runs").fetchone()[0], 1)
        block, *_ = self.sweep(c, props, {"goggles": search_page(3, [a, b, n])})
        self.assertIn("1 new", block)                          # still new: the dry run didn't count as a sweep

    def test_gone_compares_with_the_last_sweep_that_read_every_page(self):
        c = wh.db()
        self.addCleanup(c.close)
        props = {"search": ["goggles"]}
        a, b = make_summary(1, "DJI Goggles V2", 180), make_summary(2, "DJI Goggles 2 Fly More", 300)
        self.sweep(c, props, {"goggles": search_page(2, [a, b])})
        block, *_ = self.sweep(c, props, {"goggles": search_page(250, [a])})     # page limit: incomplete
        self.assertIn("read 1 of 250 ads", block)
        self.assertIn("0 gone", block)
        block, *_ = self.sweep(c, props, {"goggles": search_page(1, [a])})
        self.assertIn("1 gone", block)
        self.assertIn("DJI Goggles 2 Fly More", block)

    def test_a_failed_search_is_reported_and_the_sweep_carries_on(self):
        c = wh.db()
        self.addCleanup(c.close)
        props = {"search": ["rtx", "gtx"]}
        page = search_page(1, [make_summary(1, "Acer Nitro 5 RTX 3060", 500)])
        block, short, *_ = self.sweep(c, props, {"rtx": page, "gtx": wh.FetchError("can't fetch: timed out")})
        self.assertIn("gtx: couldn't read it all (can't fetch: timed out)", block)
        self.assertIn("Acer Nitro 5 RTX 3060", block)
        self.assertEqual(c.execute("select complete from runs order by run").fetchall()[1][0], 0)

    def test_parallel_fetch_reads_every_page_of_every_search(self):
        wh.WORKERS = 4
        c = wh.db()
        self.addCleanup(c.close)
        calls = []

        def fake_fetch(url, binary=False):
            calls.append(url)
            base = 1000 if "keyword=rtx" in url else 2000
            page = int(url.rsplit("page=", 1)[1])
            n = 50 if page == 3 else 200
            ads = [make_summary(base * 10 + page * 200 + i, "Laptop %d" % i, 500) for i in range(n)]
            return url, search_page(450, ads)

        with mock.patch.object(wh, "fetch", side_effect=fake_fetch), mock.patch.object(wh, "log"):
            res = wh.run_searches(c, [(wh.search_url("rtx"), "a"), (wh.search_url("gtx"), "b")], pages=5)
        self.assertEqual([(len(r["ads"]), r["complete"], r["error"]) for r in res], [(450, True, None)] * 2)
        self.assertEqual(len(calls), 6)

    def test_pushback_slows_every_worker_down_and_retries(self):
        ok = FakeResp(next_page({"searchResult": {"rowsFound": 0}}).encode())
        busy = wh.urllib.error.HTTPError("https://www.willhaben.at/x", 429, "Too Many Requests", {}, io.BytesIO())
        self.addCleanup(busy.close)
        with mock.patch("urllib.request.urlopen", side_effect=[busy, ok]), mock.patch("time.sleep"), \
             mock.patch.object(wh, "log"):
            _, text = wh.fetch("https://www.willhaben.at/x")
        self.assertIn("rowsFound", text)
        self.assertTrue(wh._slow[0])

    def test_a_cloudflare_challenge_is_never_returned_as_a_page(self):
        challenge = b"<html><head><title>Just a moment...</title></head></html>"
        with mock.patch("urllib.request.urlopen", side_effect=lambda *a, **k: FakeResp(challenge)), \
             mock.patch("time.sleep"), mock.patch.object(wh, "log"):
            with self.assertRaises(wh.FetchError):
                wh.fetch("https://www.willhaben.at/x")
        self.assertTrue(wh._slow[0])

    def test_sweep_warns_when_a_search_is_in_the_wrong_category(self):
        c = wh.db()
        self.addCleanup(c.close)
        url = "https://www.willhaben.at/iad/kaufen-und-verkaufen/marktplatz/laptops-notebooks-5824?keyword=rtx&PRICE_TO=850"
        ads = ([make_summary(i, "Gaming PC RTX 3060 #%d" % i, 600, cats="5824;5828;5833") for i in range(20)]
               + [make_summary(100 + i, "Lenovo Legion RTX 3060 #%d" % i, 650) for i in range(5)])
        block, *_ = self.sweep(c, {"search": [url], "wh-profile": "laptop"}, {"rtx": search_page(25, ads)})
        self.assertIn("80% of its ads are outside willhaben's notebooks-5831 category", block)
        self.assertIn("/marktplatz/computer-tablets/notebooks-5831?keyword=rtx&PRICE_TO=850 instead", block)

    def test_area_marks_near_ads_and_keeps_the_others(self):
        c = wh.db()
        self.addCleanup(c.close)
        ads = [make_summary(1, "DJI Goggles V2", 180, state="Wien"),
               make_summary(2, "DJI Goggles V2 Graz", 150, loc="Graz", state="Steiermark")]
        block, short, *_ = self.sweep(c, {"search": ["goggles"], "wh-area": "wien, noe"},
                                      {"goggles": search_page(2, ads)})
        self.assertIn("1 in Wien/NÖ", block)
        self.assertIn("| Near |", block)
        self.assertEqual({x["id"]: x["near"] for x in short}, {1: True, 2: False})   # Graz stays on the list

    def test_area_names(self):
        self.assertEqual(wh.area("wien, noe"), {"Wien", "Niederösterreich"})
        self.assertEqual(wh.area(["Wien", "NÖ"]), {"Wien", "Niederösterreich"})
        self.assertEqual(wh.area(None), set())
        with self.assertRaises(wh.WhError):
            wh.area("graz")

    def test_hunt_keeps_the_sweep_when_claude_fails(self):
        note_path = os.path.join(self.tmp.name, "Goggles.md")
        with open(note_path, "w", encoding="utf-8") as f:
            f.write("---\ntype: buy\nstatus: open\nsearch: goggles\n---\n# Goggles\n")
        page = search_page(1, [make_summary(1, "DJI Goggles V2", 180)])
        c = wh.db()
        self.addCleanup(c.close)
        ns = mock.Mock(note=note_path, pages=1, limit=10, details=0, dry_run=False, no_ai=False)
        with mock.patch.object(wh, "db", return_value=c), \
             mock.patch.object(wh, "fetch", return_value=("u", page)), \
             mock.patch.object(wh, "ask_claude", side_effect=wh.WhError("claude failed: rate limit")), \
             mock.patch.object(wh, "log"):
            with self.assertRaises(wh.WhError):
                wh.cmd_hunt(ns)
        saved, _ = wh.read_note(note_path)
        self.assertIn("<!-- wh:sweep -->", saved)
        self.assertIn("DJI Goggles V2", saved)

    def test_ask_all_keeps_order_and_reports_failures(self):
        def fake(a, task, data):
            if data == "b":
                raise wh.WhError("claude failed: boom")
            return "answer " + data
        with mock.patch.object(wh, "ask_claude", side_effect=fake):
            self.assertEqual(wh.ask_all(mock.Mock(), [("t", "a"), ("t", "b"), ("t", "c")]),
                             ["answer a", "wh: claude failed: boom", "answer c"])

    def test_facets_prints_category_urls_and_filter_params(self):
        nav = [{"label": "Kategorie", "navigatorList": [{"id": "category", "label": "Kategorie",
                "groupedPossibleValues": [{"possibleValues": [
                    {"label": "Notebooks", "hits": 207, "webLink": {"uri": "https://www.willhaben.at/iad/kaufen-und-"
                     "verkaufen/marktplatz/computer-tablets/notebooks-5831?keyword=rtx"},
                     "urlParamRepresentationForValue": [{"urlParameterName": "ATTRIBUTE_TREE", "value": "5831"}]},
                    {"label": "Netbooks", "hits": 0, "webLink": {"uri": "x"}}]}]}]},
               {"label": "Basisdaten", "navigatorList": [
                   {"id": "price", "label": "Preis", "groupedPossibleValues": [{"possibleValues": [
                       {"label": "ab € 0", "hits": 994, "urlParamRepresentationForValue": [
                           {"urlParameterName": "PRICE_FROM", "navigatorUrlParameterType": "RANGE_FROM", "value": "0"}]}]}]},
                   {"id": "Zustand", "label": "Zustand", "groupedPossibleValues": [{"possibleValues": [
                       {"label": "Gebraucht", "hits": 713, "urlParamRepresentationForValue": [
                           {"urlParameterName": "treeAttributes", "value": "23"}]}]}]}]}]
        page = next_page({"searchResult": {"rowsFound": 994, "navigatorGroups": nav}})
        out = io.StringIO()
        with mock.patch.object(wh, "fetch", return_value=("u", page)), mock.patch("sys.stdout", out):
            wh.cmd_facets(mock.Mock(words=["rtx"], url=None, min=None, max=None, limit=15))
        text = out.getvalue()
        self.assertIn("994 ads for", text)
        self.assertIn("computer-tablets/notebooks-5831?keyword=rtx", text)
        self.assertIn("treeAttributes=23", text)
        self.assertNotIn("Netbooks", text)                     # no ads
        self.assertNotIn("Preis", text)                        # price ranges: use --min/--max


class TemplateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(profiles.load_templates)              # back to the real templates
        self.dir = tmp.name

    def write(self, name, body):
        with open(os.path.join(self.dir, name + ".toml"), "w") as fh:
            fh.write(body)

    def ad(self, title, price, body=""):
        return {"id": title, "title": title, "price": price, "body": body, "loc": "Wien"}

    def test_template_registers_filters_scores_and_ranks(self):
        self.write("gloves", r"""
about = "test"
category = "motorradbekleidung/handschuhe-6363"
[[junk]]
reason = "short glove"
title = '\bkurz\w*'
unless = 'stulpe'
[[require]]
reason = "not leather"
text = 'leder'
[[field]]
name = "model"
values = [{ match = 'sp\s*-?\s*(\d)', value = 'SP-\1', score = 2, new = 100 }, { match = 'gp', score = 1 }]
[shortlist]
min_score = 1
""")
        profiles.load_templates([self.dir])
        self.assertEqual(profiles.FIELDS["gloves"], ["model", "vs_new"])
        self.assertEqual(profiles.CATEGORY["gloves"], ("6363", "motorradbekleidung/handschuhe-6363"))
        ads = profiles.annotate([self.ad("Alpinestars SP-8 Leder", 50), self.ad("Kurze Handschuhe Leder SP8", 20),
                                 self.ad("Kurze Handschuhe mit Stulpe Leder GP", 30), self.ad("Textil SP-8", 40),
                                 self.ad("Leder Handschuhe", 10)], "gloves")
        junk = {a["title"]: a["junk"] for a in ads}
        self.assertEqual(junk, {"Alpinestars SP-8 Leder": None, "Kurze Handschuhe Leder SP8": "short glove",
                                "Kurze Handschuhe mit Stulpe Leder GP": None,      # `unless` cancels the rule
                                "Textil SP-8": "not leather", "Leder Handschuhe": None})
        sp8 = ads[0]
        self.assertEqual((sp8["model"], sp8["score"], sp8["below_new"], sp8["vs_new"]),
                         ("SP-8", 2, 0.5, "new €100 (-50 %)"))
        self.assertEqual(ads[2]["model"], "gp")                                  # no `value`: the matched text
        short = profiles.shortlist([a for a in ads if not a["junk"]], "gloves", 10)
        self.assertEqual([a["title"] for a in short],                           # min_score drops the plain one
                         ["Alpinestars SP-8 Leder", "Kurze Handschuhe mit Stulpe Leder GP"])

    def test_broken_templates_are_skipped_and_the_rest_still_load(self):
        self.write("good", "[[field]]\nname = 'x'\nvalues = [{ match = 'a' }]\n")
        self.write("bad", "[[junk]]\nreason = 'r'\ntitle = '(unclosed'\n")
        self.write("laptop", "about = 'clash'\n")
        self.write("typo", "[[feild]]\nname = 'x'\n")
        self.write("badsort", "[shortlist]\nsort = ['-size']\n")
        profiles.load_templates([self.dir])
        self.assertIn("good", profiles.PROFILES)
        errs = {os.path.basename(p): e for p, e in profiles.TEMPLATE_ERRORS.items()}
        self.assertIn("bad pattern", errs["bad.toml"])
        self.assertIn("built-in", errs["laptop.toml"])
        self.assertIn("unknown keys", errs["typo.toml"])
        self.assertIn("[shortlist]", errs["badsort.toml"])
        self.assertIs(profiles.PROFILES["laptop"][0], profiles.laptop)      # the built-in stays

    def test_reload_forgets_removed_templates(self):
        self.write("gone", "about = 'x'\n")
        profiles.load_templates([self.dir])
        self.assertIn("gone", profiles.PROFILES)
        os.remove(os.path.join(self.dir, "gone.toml"))
        profiles.load_templates([self.dir])
        self.assertNotIn("gone", profiles.PROFILES)
        self.assertNotIn("gone", profiles.FIELDS)

    def test_sort_keys_handle_strings_and_missing_values(self):
        tpl = profiles.parse_template("t", {"shortlist": {"sort": ["-published", "price"]}})
        ads = [dict(id=1, title="a", price=5, published=None, junk=None),
               dict(id=2, title="b", price=9, published="2026-10-29", junk=None),
               dict(id=3, title="c", price=1, published="2026-10-30", junk=None)]
        self.assertEqual([a["id"] for a in profiles.template_shortlist(tpl, ads, 10)], [3, 2, 1])

    def test_tests_never_read_personal_templates(self):
        home = os.path.expanduser("~/.config/wh")
        self.assertFalse([d for d in profiles.TEMPLATE_DIRS if d.startswith(home)], profiles.TEMPLATE_DIRS)

    def test_shipped_example_template(self):
        profiles.load_templates()
        self.assertIn("example", profiles.TEMPLATES, profiles.TEMPLATE_ERRORS)
        ads = profiles.annotate([
            self.ad("Rancilio Silvia Espressomaschine", 300),
            self.ad("Suche Gaggia Espressomaschine", 100),
            self.ad("Tamper für Siebträger", 20),
            self.ad("Gaggia Classic", 150, "Espresso"),
            self.ad("Toaster", 10),
        ], "example")
        by = {a["title"]: a for a in ads}
        self.assertEqual((by["Rancilio Silvia Espressomaschine"]["junk"], by["Rancilio Silvia Espressomaschine"]["brand"]),
                         (None, "Rancilio"))
        self.assertEqual(by["Suche Gaggia Espressomaschine"]["junk"], "wanted ad")
        self.assertEqual(by["Tamper für Siebträger"]["junk"], "part or accessory")
        self.assertIsNone(by["Gaggia Classic"]["junk"])
        self.assertEqual(by["Toaster"]["junk"], "not a machine")

class NoteProfileTests(TmpDbCase):
    def test_unknown_wh_profile_warns_and_sweeps_without_one(self):
        with mock.patch.object(wh, "log") as log:
            self.assertIsNone(wh.note_profile({"wh-profile": "glovez"}, "/x/Gloves.md"))
            self.assertEqual(wh.note_profile({"wh-profile": "laptop"}, "/x/Laptop.md"), "laptop")
        self.assertIn("unknown wh-profile 'glovez'", log.call_args[0][0])

    def test_for_is_read_warned_about_and_put_in_the_prompt(self):
        with mock.patch.object(wh, "log") as log:
            self.assertIsNone(wh.note_for({}, "/x/Laptop.md"))
            self.assertIn("Laptop has no `for:`", log.call_args[0][0])
            log.reset_mock()
            self.assertEqual(wh.note_for({"for": "a friend"}, "/x/Laptop.md"), "a friend")
            self.assertEqual(wh.note_for({"for": ["me", "homelab"]}, "/x/Mixed.md"), "me, homelab")
            log.assert_not_called()
        block = wh.who_block("a friend")
        self.assertTrue(block.startswith("## Who it's for\n\na friend. Judge only by"))
        self.assertIn("unless it says it's for me", block)
        self.assertIn("Don't assume it's for me", wh.who_block(None))

    def test_sweep_warns_about_notes_without_for(self):
        notes = os.path.join(self.tmp.name, "notes")
        os.makedirs(notes)
        for name, extra in (("Gloves", "for: me\n"), ("Laptop", "")):
            with open(os.path.join(notes, name + ".md"), "w", encoding="utf-8") as f:
                f.write("---\ntype: buy\nstatus: open\n%ssearch: x\n---\n# %s\n" % (extra, name))
        empty = next_page({"searchResult": {"rowsFound": 0, "advertSummaryList": {"advertSummary": []}}})
        ns = mock.Mock(notes=[], pages=1, limit=5, dry_run=True)
        c = wh.db()
        self.addCleanup(c.close)
        with mock.patch.object(wh, "NOTES", notes), mock.patch.object(wh, "fetch", return_value=("u", empty)), \
             mock.patch.object(wh, "db", return_value=c), \
             mock.patch.object(wh, "log") as log, mock.patch("sys.stdout", io.StringIO()):
            wh.cmd_sweep(ns)
        warned = [c[0][0] for c in log.call_args_list if "no `for:`" in c[0][0]]
        self.assertEqual(len(warned), 1)
        self.assertIn("Laptop", warned[0])


class AdviseRulesTest(unittest.TestCase):
    def test_advise_sends_the_pricing_rules(self):
        """advise asked for "Pricing advice for my ads", the skill says "for the user's ads": the rules never got sent."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "SKILL.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write("## Ground rules\n\nG\n\n## Selling\n\nS\n\n### Pricing advice for the user's ads\n\nPRICING\n")
            jobs = []
            with mock.patch.object(wh, "SKILL", path), mock.patch.object(wh, "find_notes", return_value=[
                    ("/n/Item.md", "---\n---\n", {"type": "sell", "ad": "1234567"})]), \
                 mock.patch.object(wh, "details_many", return_value={1234567: dict(
                     id=1234567, status="active", title="Item", price=10, old_price=None, loc="", private=True,
                     seller="s", seller_since="", seller_ads=1, first_published="", changed="", ends="", info=[],
                     descr="", images=[], url="u")}), \
                 mock.patch.object(wh, "run_searches", return_value=[dict(ads=[], found=0, complete=True, error=None)]), \
                 mock.patch.object(wh, "db", return_value=mock.Mock()), \
                 mock.patch.object(wh, "price_history", return_value=[]), \
                 mock.patch.object(wh, "attach_details", side_effect=lambda c, ads: ads), \
                 mock.patch.object(wh, "ask_all", side_effect=lambda a, j: jobs.extend(j) or ["ok"] * len(j)), \
                 mock.patch("sys.stdout", io.StringIO()):
                wh.cmd_advise(mock.Mock(notes=[], pages=1, limit=5, no_ai=False))
                rules = wh.skill_rules(jobs[0][2])
        self.assertIn("PRICING", rules)



SPLIT_SKILL = """---
name: willhaben
---

# willhaben

## wh: use it instead of writing scripts

| `wh search` | lists ads |

## Read before the task

- buying.md, selling.md

## Ground rules

- GROUND-RULE
"""

OLD_SKILL = """# willhaben

## wh: use it instead of writing scripts

COMMAND-TABLE

## Ground rules

- GROUND-RULE

## Getting the data (no browser needed)

DATA-RULE

## Judging a deal (buying)

BUY-RULE

## Selling

SELL-RULE

### Pricing advice for the user's ads

PRICING-RULE

## willhaben quirks

- QUIRK-RULE
"""


class SkillRulesTest(unittest.TestCase):
    """Which rules the AI commands send: SKILL.md's ground rules plus buying.md (deal, hunt) or selling.md (advise)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.skill = os.path.join(self.tmp.name, "SKILL.md")
        patcher = mock.patch.object(wh, "SKILL", self.skill)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, name, text):
        with open(os.path.join(self.tmp.name, name), "w", encoding="utf-8") as f:
            f.write(text)

    def write_split(self):
        self.write("SKILL.md", SPLIT_SKILL)
        self.write("buying.md", "# willhaben: buying\n\nBUY-INTRO\n\n## Judging a deal (buying)\n\nBUY-RULE\n")
        self.write("selling.md", "# willhaben: selling\n\nSELL-INTRO\n\n## Selling\n\nSELL-RULE\n")
        self.write("data.md", "## Getting the data\n\nDATA-RULE\n")

    def test_split_buy_sends_ground_rules_and_buying_only(self):
        self.write_split()
        r = wh.skill_rules("buy")
        self.assertTrue(r.startswith("## Ground rules\n- GROUND-RULE"))
        self.assertIn("## Judging a deal (buying)\n\nBUY-RULE", r)
        for other in ("SELL-RULE", "DATA-RULE", "lists ads", "BUY-INTRO", "name: willhaben", "Read before"):
            self.assertNotIn(other, r)

    def test_split_sell_sends_ground_rules_and_selling_only(self):
        self.write_split()
        r = wh.skill_rules("sell")
        self.assertIn("GROUND-RULE", r)
        self.assertIn("## Selling\n\nSELL-RULE", r)
        for other in ("BUY-RULE", "DATA-RULE", "lists ads", "SELL-INTRO"):
            self.assertNotIn(other, r)

    def test_old_single_file_skill_still_works(self):
        self.write("SKILL.md", OLD_SKILL)
        buy, sell = wh.skill_rules("buy"), wh.skill_rules("sell")
        self.assertIn("GROUND-RULE", buy)
        self.assertIn("BUY-RULE", buy)
        self.assertNotIn("SELL-RULE", buy)
        for rule in ("GROUND-RULE", "SELL-RULE", "PRICING-RULE", "QUIRK-RULE"):   # pricing was lost before the split
            self.assertIn(rule, sell)
        self.assertIn("### Pricing advice for the user's ads", sell)
        for rule in ("BUY-RULE", "DATA-RULE", "COMMAND-TABLE"):
            self.assertNotIn(rule, sell)

    def test_one_split_file_missing_falls_back_for_that_kind(self):
        self.write("SKILL.md", OLD_SKILL)
        self.write("buying.md", "# t\n\n## Judging a deal (buying)\n\nNEW-BUY-RULE\n")
        self.assertIn("NEW-BUY-RULE", wh.skill_rules("buy"))
        self.assertIn("SELL-RULE", wh.skill_rules("sell"))

    def test_no_skill_gives_no_rules(self):
        with mock.patch.object(wh, "SHIPPED_SKILL", os.path.join(self.tmp.name, "nope", "SKILL.md")), \
             mock.patch.object(wh, "log") as log:
            self.assertEqual(wh.skill_rules("buy"), "")
        self.assertIn("not found", log.call_args[0][0])

    def test_ask_claude_puts_the_kinds_rules_in_the_system_prompt(self):
        self.write_split()
        ns = mock.Mock(no_ai=False, model=None, timeout=5)
        done = subprocess.CompletedProcess([], 0, stdout=" ok \n", stderr="")
        with mock.patch.object(wh.subprocess, "run", return_value=done) as run, mock.patch.object(wh, "log"), \
             mock.patch.dict(os.environ, {"WH_MODEL": ""}):
            self.assertEqual(wh.ask_claude(ns, "task", "data", "sell"), "ok")
            self.assertEqual(wh.ask_claude(ns, "task", "data"), "ok")          # default: buying rules
        (sell_cmd,), _ = run.call_args_list[0]
        (buy_cmd,), _ = run.call_args_list[1]
        sell_sys = sell_cmd[sell_cmd.index("--append-system-prompt") + 1]
        buy_sys = buy_cmd[buy_cmd.index("--append-system-prompt") + 1]
        self.assertTrue(sell_sys.startswith(wh.system_prompt()))
        self.assertIn("SELL-RULE", sell_sys)
        self.assertNotIn("BUY-RULE", sell_sys)
        self.assertIn("BUY-RULE", buy_sys)
        self.assertNotIn("SELL-RULE", buy_sys)

    def test_commands_ask_for_the_right_kind(self):
        with open(os.path.join(HERE, "wh"), encoding="utf-8") as f:
            src = f.read()
        for cmd, kind in (("cmd_deal", "buy"), ("cmd_hunt", "buy"), ("cmd_advise", "sell")):
            body = src[src.index("def %s(" % cmd):]
            body = body[:body.index("\ndef ", 1)]
            self.assertIn('"%s")' % kind, body, cmd)

    def test_shipped_skill_split_sizes(self):
        skill = os.path.join(HERE, "skill", "willhaben", "SKILL.md")
        with mock.patch.object(wh, "SKILL", skill):
            buy, sell = wh.skill_rules("buy"), wh.skill_rules("sell")
        self.assertIn("Judging a deal", buy)
        self.assertIn("Pricing advice", sell)
        self.assertNotIn("Pricing advice", buy)
        self.assertNotIn("Judging a deal", sell)
        self.assertLessEqual(len(sell.encode()), 5000)    # keep the rules each call sends small
        self.assertLessEqual(len(buy.encode()), 5000)


    def test_skill_may_name_the_folder(self):
        self.write_split()
        with mock.patch.object(wh, "SKILL", self.tmp.name):
            self.assertIn("SELL-RULE", wh.skill_rules("sell"))

    def test_missing_skill_falls_back_to_the_shipped_one(self):
        with mock.patch.object(wh, "SKILL", os.path.join(self.tmp.name, "nope", "SKILL.md")):
            self.assertEqual(wh.skill_path(), wh.SHIPPED_SKILL)
            self.assertIn("Pricing advice", wh.skill_rules("sell"))

    def test_shipped_skill_has_no_personal_data(self):
        d = os.path.dirname(wh.SHIPPED_SKILL)
        for name in sorted(os.listdir(d)):
            with open(os.path.join(d, name), encoding="utf-8") as f:
                text = f.read()
            for word in ("Anna", "girlfriend", "~/Notes", "kbauer", "pi-two", "homelab repo", "sport-gloves"):
                self.assertNotIn(word, text, name)


if __name__ == "__main__":
    unittest.main()
