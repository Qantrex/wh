import gzip
import importlib.machinery
import importlib.util
import io
import json
import re
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
            "Display nicht gesprungen, keine Risse.",
            "Mit Panzerglas & Hülle. Das Panzerglas ist gesprungen, das Display darunter ist heil.",
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
            "Display gesprungen, Rückseite gesprungen, Akku 75 %",
            "Kleiner Riss im Display",
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
        wh._slow[0], wh._next[0], wh._slow_at[0] = False, 0.0, None

    def tearDown(self):
        wh.DB, wh.DELAY, wh.RATE, wh.WORKERS = self.orig
        wh._slow[0], wh._next[0], wh._slow_at[0] = False, 0.0, None
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

    def test_dates_are_austrian_days(self):
        if wh.TZ is wh.timezone.utc:
            self.skipTest("no tz database")
        self.assertEqual(wh.day("1760911200000"), "2025-10-20")            # 2025-10-19T22:00Z, midnight in Vienna
        self.assertEqual(wh.day("1760911200"), "2025-10-20")
        self.assertEqual(wh.day("2026-10-19T23:30:00Z"), "2026-10-20")
        self.assertEqual(wh.day("2026-10-19T23:30:00+02:00"), "2026-10-19")         # summer time
        self.assertEqual(wh.day("2026-10-19"), "2026-10-19")
        self.assertEqual(wh.day("2026-10-19T23:30:00"), "2026-10-19")       # no zone: as written
        self.assertEqual((wh.day(None), wh.day("garbage")), ("", "garbage"))

    def test_history_shows_prices_over_time_without_a_request(self):
        c = wh.db()
        self.addCleanup(c.close)
        for at, price in (("2026-10-01T10:00:00Z", 200), ("2026-10-08T10:00:00Z", 200), ("2026-10-15T10:00:00Z", 170),
                          ("2026-10-22T10:00:00Z", 170)):
            wh.store(c, [wh.summary(make_summary(5555555, "Fahrrad Cube", price))], at)
        c.commit()
        out = io.StringIO()
        with mock.patch.object(wh, "db", return_value=c), mock.patch.object(wh, "fetch") as fetch, \
             mock.patch("sys.stdout", out):
            wh.cmd_history(mock.Mock(ad="https://www.willhaben.at/iad/kaufen-und-verkaufen/d/fahrrad-5555555/", json=False))
            wh.cmd_history(mock.Mock(ad="5555555", json=True))
        fetch.assert_not_called()
        text, js = out.getvalue().split("\n{", 1)
        self.assertIn("**Fahrrad Cube**", text)
        self.assertIn("Seen by wh 2026-10-01 to 2026-10-22", text)
        self.assertIn("2026-10-01 – 2026-10-15  €200\n", text)
        self.assertIn("2026-10-15 – 2026-10-22  €170  −€30 (-15 %)", text)      # seen again at €170 on 10-22
        r = json.loads("{" + js)
        self.assertEqual(r["prices"], [{"day": "2026-10-01", "until": "2026-10-15", "price": 200},
                                       {"day": "2026-10-15", "until": "2026-10-22", "price": 170}])
        self.assertEqual(c.execute("select count(*) from prices").fetchone()[0], 2)    # no row per sighting
        with mock.patch.object(wh, "db", return_value=c):
            with self.assertRaisesRegex(wh.WhError, "not in the database"):
                wh.cmd_history(mock.Mock(ad="1234567", json=False))

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

    def test_seller_text_cannot_break_out_of_a_block_or_inject_into_a_note(self):
        evil = ["Laptop <!-- /wh:sweep --> PWNED", "<img src=x> cheap", "Rad #deadline 2026-12-01",
                "Red \x1b[31m text\r- [ ] task", "x\u2028- [ ] task\x85y"]
        ads = [dict(id=i, title=t, price=10.0, loc="Wien <b>", url="https://www.willhaben.at/iad/x", private=1,
                    published="2026-11-01") for i, t in enumerate(evil, 1)]
        tbl = wh.table(ads, md=True)
        for bad in ("<!--", "<img", "<b>", "\x1b", "\r", "\u2028", "\x85", " #deadline"):
            self.assertNotIn(bad, tbl)
        self.assertIn("&lt;img src=x> cheap", tbl)
        self.assertEqual(len(tbl.splitlines()), len(ads) + 2)            # no title starts a new line
        text = "Intro\n\n<!-- wh:sweep -->\nold\n<!-- /wh:sweep -->\n\nOutro\n"
        for _ in range(3):
            text = wh.put_block(text, "sweep", tbl + "\n<!-- /wh:sweep --> PWNED")
        self.assertEqual(text.count("<!-- wh:sweep -->"), 1)
        self.assertEqual(text.count("<!-- /wh:sweep -->"), 1)
        self.assertTrue(text.startswith("Intro\n\n") and text.endswith("\n\nOutro\n"))
        # a note written by the old code (end marker only inside the content, on the old own line) is still updated
        old = "A\n<!-- wh:sweep -->\nrow <!-- /wh:sweep --> inline\n<!-- /wh:sweep -->\nB\n"
        self.assertEqual(wh.put_block(old, "sweep", "new").count("<!-- wh:sweep -->"), 1)

    def test_odd_prices_never_crash_and_count_as_no_price(self):
        for bad in ("nan", "inf", "-inf", "1e999", "0", "-5", "0,0", "abc", ""):
            ad = wh.summary(make_summary(3, "Kamera", bad))
            self.assertIsNone(ad["price"], bad)
            self.assertIn("Kamera", wh.table([ad]))
            self.assertIn("Kamera", wh.table([ad], md=True))
        self.assertEqual(wh.summary(make_summary(3, "Kamera", "12,5"))["price"], 12.5)
        self.assertIsNone(wh.num("nan"))
        self.assertIsNone(wh.num("1e999"))
        for p in (float("nan"), float("inf"), None):
            self.assertEqual(wh.euro(p), "–")
        self.assertEqual(wh.euro(100.0), "€100")
        self.assertEqual(wh.euro(9.5), "€9.50")

    def test_one_malformed_ad_is_skipped_and_a_mostly_bad_page_is_an_error(self):
        good = [make_summary(i, "Kamera %d" % i, 10 + i) for i in range(1, 6)]
        bad = [{"id": "abc", "attributes": {"attribute": []}}, {"id": "9"}, {"id": "8", "attributes": {"attribute": [{}]}}]
        with mock.patch.object(wh, "log") as log, \
             mock.patch.object(wh, "fetch", return_value=("u", search_page(8, good + bad))):
            found, ads = wh.read_page("https://www.willhaben.at/x?a=1")
        self.assertEqual([a["id"] for a in ads], [1, 2, 3, 4, 5])
        self.assertIn("3 of 8 entries skipped", log.call_args[0][0])
        with mock.patch.object(wh, "log"), mock.patch.object(wh, "fetch", return_value=("u", search_page(4, good[:1] + bad))):
            with self.assertRaises(wh.FetchError):
                wh.read_page("https://www.willhaben.at/x?a=1")

    def test_fetch_only_takes_https_willhaben_urls_and_caps_the_size(self):
        for bad in ("file:///etc/hostname", "http://127.0.0.1/", "http://www.willhaben.at/x", "https://evil.example/x",
                    "https://willhaben.at.evil.example/x", "https://evilwillhaben.at/x"):
            with mock.patch("urllib.request.urlopen") as op:
                with self.assertRaises(wh.FetchError):
                    wh.fetch(bad)
            op.assert_not_called()
        for good in ("https://www.willhaben.at/x", "https://cache.willhaben.at/p.jpg", "https://willhaben.at/"):
            self.assertTrue(wh.allowed_url(good), good)
        with mock.patch.object(wh, "MAX_BYTES", 10), mock.patch.object(wh, "wait_turn"), mock.patch.object(wh, "log"), \
             mock.patch("time.sleep"):
            with mock.patch("urllib.request.urlopen", return_value=FakeResp(b"x" * 11)):
                with self.assertRaises(wh.FetchError):
                    wh.fetch("https://www.willhaben.at/x")
            bomb = wh.gzip.compress(b"x" * 1000)
            with mock.patch("urllib.request.urlopen", return_value=FakeResp(bomb, {"Content-Encoding": "gzip"})):
                with self.assertRaises(wh.FetchError):
                    wh.fetch("https://www.willhaben.at/x")

    def test_template_value_with_a_bad_group_reference_fails_at_load(self):
        def tpl(value, match="foo"):
            return {"field": [{"name": "f", "values": [{"match": match, "value": value}]}]}
        for bad in (r"\1", r"\g<nope>", r"\q"):
            with self.assertRaises(ValueError) as e:
                profiles.parse_template("t", tpl(bad))
            self.assertIn("bad value", str(e.exception))
        ok = profiles.parse_template("t", tpl(r"\1 GB", r"(\d+) ?gb"))
        ad = {"title": "ram 16 GB", "price": 10}
        profiles.template_annotate(ok, ad)
        self.assertEqual(ad["f"], "16 GB")

    def test_database_file_is_private_and_an_old_one_is_tightened(self):
        path = os.path.join(self.tmp.name, "new", "wh.db")
        with mock.patch.object(wh, "DB", path):
            wh.db().close()
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            os.chmod(path, 0o644)
            wh.db().close()
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            os.chmod(path, 0o644)
            with mock.patch("os.chmod", side_effect=PermissionError):
                wh.db().close()                             # never fails when the mode can't be changed

    def test_summary_drops_control_characters(self):
        a = make_summary(7, "Rad \x1b[2J\x1b]0;pwn\x07 neu", 50)
        self.assertNotIn("\x1b", wh.summary(a)["title"])
        self.assertNotIn("\x07", wh.table([wh.summary(a)]))

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

    def test_hunt_writes_the_models_answer_tamed_and_says_when_there_are_warnings(self):
        path = os.path.join(self.tmp.name, "Goggles.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("---\ntype: buy\nstatus: open\nfor: me\nsearch: goggles\n---\n# Goggles\n")
        page = search_page(1, [make_summary(1, "DJI Goggles V2", 180)])
        answer = ("## Picks\n\n1. **Goggles** https://www.willhaben.at/iad/x#top\n- [x] done <img src=x>\n"
                  "<!-- /wh:picks --> [[Secret]] ![[embed]] ![p](https://e.example/p.png)\n#deadline 2026-12-01\n"
                  + "long " * 3000 + "\n\n## Warnings\n\nAd 1 looks like a scam\n")
        c = wh.db()
        self.addCleanup(c.close)
        ns = mock.Mock(note=path, pages=1, limit=10, details=0, dry_run=False, no_ai=False)
        with mock.patch.object(wh, "db", return_value=c), mock.patch.object(wh, "fetch", return_value=("u", page)), \
             mock.patch.object(wh, "ask_claude", return_value=answer), \
             mock.patch.object(wh, "log"), mock.patch("sys.stdout", io.StringIO()):
            wh.cmd_hunt(ns)
        saved, _ = wh.read_note(path)
        self.assertEqual(saved.count("<!-- /wh:picks -->"), 1)
        for bad in ("<img", "[[", "![", "\n#deadline", "- [x]"):
            self.assertNotIn(bad, saved)
        self.assertIn("1. **Goggles** https://www.willhaben.at/iad/x#top", saved)       # normal Markdown stays
        self.assertIn("flagged ads that look like scams", saved)
        self.assertLess(len(saved), 9000)

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

    def test_a_cut_off_gzip_body_is_retried_not_a_traceback(self):
        cut = gzip.compress(b"x" * 1000)[:20]
        good = gzip.compress(b"<html>ok</html>")
        with mock.patch("urllib.request.urlopen", side_effect=[
                FakeResp(cut, {"Content-Encoding": "gzip"}), FakeResp(good, {"Content-Encoding": "gzip"})]), \
             mock.patch("time.sleep"), mock.patch.object(wh, "log"):
            self.assertEqual(wh.fetch("https://www.willhaben.at/x")[1], "<html>ok</html>")
        with mock.patch("urllib.request.urlopen", side_effect=lambda *a, **k: FakeResp(cut, {"Content-Encoding": "gzip"})), \
             mock.patch("time.sleep"), mock.patch.object(wh, "log"):
            with self.assertRaises(wh.FetchError):
                wh.fetch("https://www.willhaben.at/x")

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

    def test_sweep_skips_a_note_with_a_bad_area_and_reads_keywords_with_a_slash(self):
        notes = os.path.join(self.tmp.name, "notes")
        os.makedirs(notes)
        for name, extra in (("Typo", "wh-area: graz\n"), ("Gpu", "")):
            with open(os.path.join(notes, name + ".md"), "w", encoding="utf-8") as f:
                f.write("---\ntype: buy\nstatus: open\nfor: me\n%ssearch: rtx 3060/3070\n---\n" % extra)
        urls = []
        empty = next_page({"searchResult": {"rowsFound": 0, "advertSummaryList": {"advertSummary": []}}})
        c = wh.db()
        self.addCleanup(c.close)
        out = io.StringIO()
        with mock.patch.object(wh, "NOTES", notes), mock.patch.object(wh, "db", return_value=c), \
             mock.patch.object(wh, "fetch", side_effect=lambda u, binary=False: urls.append(u) or (u, empty)), \
             mock.patch.object(wh, "log"), mock.patch("sys.stdout", out):
            wh.cmd_sweep(mock.Mock(notes=[], pages=1, limit=5, dry_run=True, no_write=False, json=False))
        self.assertIn("Typo: skipped: unknown area 'graz'", out.getvalue())
        self.assertIn("## Sweep", out.getvalue())
        self.assertEqual(len(urls), 1)
        self.assertIn("/marktplatz?keyword=rtx+3060%2F3070", urls[0])

    def test_sweep_json_lists_new_ads_and_cuts_and_no_write_leaves_the_note(self):
        notes = os.path.join(self.tmp.name, "notes")
        os.makedirs(notes)
        path = os.path.join(notes, "Goggles.md")
        original = "---\ntype: buy\nstatus: open\nfor: me\nsearch: goggles\n---\n# Goggles\n"
        with open(path, "w", encoding="utf-8") as f:
            f.write(original)
        c = wh.db()
        self.addCleanup(c.close)

        def sweep(ads, at, **kw):
            out = io.StringIO()
            ns = mock.Mock(notes=[], pages=1, limit=5, **dict(dict(dry_run=False, no_write=True, json=True), **kw))
            with mock.patch.object(wh, "NOTES", notes), mock.patch.object(wh, "db", return_value=c), \
                 mock.patch.object(wh, "fetch", return_value=("u", search_page(len(ads), ads))), \
                 mock.patch.object(wh, "now", return_value=at), \
                 mock.patch.object(wh, "log"), mock.patch("sys.stdout", out):
                wh.cmd_sweep(ns)
            return out.getvalue()

        sweep([make_summary(1, "DJI Goggles V2", 180)], "2026-11-01T10:00:00Z")
        out = sweep([make_summary(1, "DJI Goggles V2", 150), make_summary(2, "DJI Goggles 2", 300)],
                    "2026-11-02T10:00:00Z")
        r = json.loads(out)
        note = r["notes"][0]
        self.assertEqual((note["note"], note["ads"]), ("Goggles", 2))
        self.assertEqual([(x["id"], x["price"]) for x in note["new"]], [(2, 300)])
        self.assertEqual([(x["id"], x["price"], x["was"]) for x in note["cuts"]], [(1, 150, 180)])
        self.assertEqual(note["gone"], [])
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), original)                        # --no-write
        self.assertEqual(c.execute("select count(*) from runs").fetchone()[0], 2)
        out = sweep([make_summary(1, "DJI Goggles V2", 150), make_summary(2, "DJI Goggles 2", 300)],
                    "2026-11-03T10:00:00Z", no_write=False, json=False)
        self.assertIn("Goggles: 2 ads", out)
        with open(path, encoding="utf-8") as f:
            self.assertIn("<!-- wh:sweep -->", f.read())

    def doctor(self, **patches):
        with mock.patch.multiple(wh, **patches), \
             mock.patch.object(wh.shutil, "which", side_effect=lambda t: "/usr/bin/" + t if t == "claude" else None):
            return wh.doctor_checks()

    def test_doctor_checks_notes_skill_database_and_tools(self):
        notes = os.path.join(self.tmp.name, "notes")
        os.makedirs(notes)
        for name, props in (("Laptop", "type: buy\nstatus: open\nsearch: x\nwh-area: graz\nwh-profile: nope\n"),
                            ("Bike", "type: sell\nstatus: live\nad: soon\n")):
            with open(os.path.join(notes, name + ".md"), "w", encoding="utf-8") as f:
                f.write("---\n%s---\n" % props)
        skills = os.path.join(self.tmp.name, "skills")
        os.makedirs(skills)
        os.symlink(os.path.dirname(wh.SHIPPED_SKILL), os.path.join(skills, "willhaben"))
        c = wh.db()
        c.close()
        config = os.path.join(self.tmp.name, "config.toml")
        with open(config, "w", encoding="utf-8") as f:
            f.write('notes = "x"\nlocaton = "1010 Wien"\n')
        checks = self.doctor(NOTES=notes, SKILL=os.path.join(skills, "willhaben", "SKILL.md"), CONFIG_PATH=config,
                             CONFIG=wh.load_config(config))
        text = "\n".join("%s %s %s" % x for x in checks)
        self.assertIn("warn config unknown key 'locaton'", text)
        self.assertIn("1 open buy/wanted (1 with `search:`), 1 live sell", text)
        for warning in ("Laptop has no `for:`", "Laptop: unknown wh-profile 'nope'", "Laptop: unknown area 'graz'",
                        "Bike: no willhaben ad id in 'soon'", "wh is not on PATH"):
            self.assertIn(warning, text)
        self.assertRegex(text, r"ok skill .*SKILL.md \(links to this repo\)")
        self.assertRegex(text, r"ok database .*intact, 0 ads")
        self.assertIn("ok tools claude found", text)
        self.assertNotIn("FAIL", text)

    def test_doctor_fails_without_notes_and_warns_without_a_skill(self):
        checks = self.doctor(NOTES=os.path.join(self.tmp.name, "none"), SKILL=os.path.join(self.tmp.name, "SKILL.md"),
                             CONFIG_PATH=os.path.join(self.tmp.name, "none.toml"), CONFIG={})
        levels = {(lvl, what) for lvl, what, _ in checks}
        self.assertIn(("FAIL", "notes"), levels)
        self.assertIn(("warn", "skill"), levels)
        self.assertIn(("info", "database"), levels)
        with mock.patch.object(wh, "doctor_checks", return_value=checks), mock.patch("sys.stdout", io.StringIO()):
            with self.assertRaises(SystemExit):
                wh.cmd_doctor(None)

    def test_sweep_warns_about_notes_without_for(self):
        notes = os.path.join(self.tmp.name, "notes")
        os.makedirs(notes)
        for name, extra in (("Gloves", "for: me\n"), ("Laptop", "")):
            with open(os.path.join(notes, name + ".md"), "w", encoding="utf-8") as f:
                f.write("---\ntype: buy\nstatus: open\n%ssearch: x\n---\n# %s\n" % (extra, name))
        empty = next_page({"searchResult": {"rowsFound": 0, "advertSummaryList": {"advertSummary": []}}})
        ns = mock.Mock(notes=[], pages=1, limit=5, dry_run=True, no_write=False, json=False)
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

    def test_claude_runs_in_a_throwaway_folder(self):
        seen = []

        def fake(cmd, **kw):
            seen.append((kw.get("cwd"), os.path.isdir(kw.get("cwd") or "")))
            return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")
        ns = mock.Mock(no_ai=False, model=None, timeout=5)
        with mock.patch.object(wh.subprocess, "run", side_effect=fake), mock.patch.object(wh, "log"):
            wh.ask_claude(ns, "task", "data")
            wh.ask_labels("q", [dict(id=1, title="t", price=1.0, body="")], "haiku")
        self.assertEqual(len(seen), 2)
        for cwd, existed in seen:
            self.assertTrue(existed)
            self.assertNotEqual(os.path.realpath(cwd), os.path.realpath(os.getcwd()))
            self.assertFalse(os.path.exists(cwd))              # removed again afterwards

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

    def test_public_tree_has_no_personal_data(self):
        # Generic markers live here (split so this file does not hold them); personal words stay private:
        # WH_LEAKWORDS may name a file with one word per line (e.g. ~/.config/wh/leakwords), so this public repo
        # never lists them itself. Every tracked file is checked, not only the skill.
        words = ["~/" + "Notes", "homelab" + " repo"]
        leak = os.environ.get("WH_LEAKWORDS")
        if leak:
            with open(os.path.expanduser(leak), encoding="utf-8") as f:
                words += [w.strip() for w in f if w.strip() and not w.startswith("#")]
        try:
            names = subprocess.run(["git", "ls-files", "-z"], cwd=HERE, capture_output=True, text=True,
                                   check=True).stdout.split("\0")
        except (OSError, subprocess.CalledProcessError):
            names = []
        names = [n for n in names if n]
        if not names:                                       # not a git checkout (a copy of the files): walk it
            names = [os.path.relpath(os.path.join(d, f), HERE) for d, ds, fs in os.walk(HERE)
                     if ".git" not in d.split(os.sep) and "__pycache__" not in d for f in fs]
        self.assertIn("wh", names)
        for name in sorted(names):
            try:
                with open(os.path.join(HERE, name), encoding="utf-8") as f:
                    text = f.read()
            except (OSError, UnicodeDecodeError):
                continue                                    # a binary file
            for word in words:
                self.assertNotIn(word, text, name)

    def test_leak_check_catches_a_word_in_any_tracked_file(self):
        with open(os.path.join(HERE, "README.md"), encoding="utf-8") as f:
            readme = f.read()
        tmp = os.path.join(self.tmp.name, "leak")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("wh\n")                                 # a word every file holds: the test must fail on it
        with mock.patch.dict(os.environ, {"WH_LEAKWORDS": tmp}):
            with self.assertRaises(AssertionError):
                self.test_public_tree_has_no_personal_data()
        self.assertTrue(readme)


import market  # noqa: E402


def mad(title, price, body="", tattrs="", seller=None, private=1, i=None, cats=None, kind="ram", first="2026-11-01T00:00:00Z",
        last="2026-11-07T00:00:00Z"):
    """An annotated ad dict for market tests."""
    ad = dict(id=i or abs(hash((title, price, seller))) % 10**9, title=title, price=price, body=body, tattrs=tattrs,
              seller=seller, private=private, cats=cats or ";".join(market.KINDS[kind]["ids"][:1]),
              first_seen=first, last_seen=last)
    return market.specs(ad, kind)


class MarketExtractTests(unittest.TestCase):
    def test_ram_kit_speed_and_form(self):
        s = mad("Corsair Vengeance 32GB (2x16GB) DDR4 3200MHz", 100)["specs"]
        self.assertEqual((s["gen"], s["form"], s["kit"], s["speed"]), ("ddr4", "dimm", "2x16", 3200))
        s = mad("Kingston 16GB DDR4 PC4-25600 SO-DIMM", 40)["specs"]
        self.assertEqual((s["form"], s["speed"], s["total"]), ("sodimm", 3200, 16))
        s = mad("2 Stk. 8GB DDR3 Riegel", 20)["specs"]
        self.assertEqual(s["kit"], "2x8")
        # a description that only mentions laptops or servers doesn't turn a desktop kit into something else
        s = mad("G.Skill 2x16GB DDR4 3600", 120, body="passt nicht in Laptops, war in meinem Server")["specs"]
        self.assertEqual(s["form"], "dimm")
        self.assertEqual(mad("Ryzen 5 3600 + 16GB DDR4 RAM", 150)["junk"], "bundle or not RAM")

    def test_gpu_models(self):
        g = lambda t: mad(t, 200, kind="gpu")["specs"].get("model")  # noqa: E731
        self.assertEqual(g("MSI GeForce RTX 3060 Ti Gaming X"), "rtx 3060 ti")
        self.assertEqual(g("Gigabyte 3070 Gaming OC 8GB"), "rtx 3070")
        self.assertEqual(g("Sapphire Radeon RX 6700 XT Pulse"), "rx 6700 xt")
        self.assertEqual(g("Medion MSI GeForce GTX 550 Ti"), "gtx 550 ti")
        self.assertEqual(mad("RTX 3060 12GB", 200, kind="gpu")["specs"]["vram"], 12)
        self.assertEqual(mad("Gaming PC mit RTX 3070", 600, kind="gpu")["junk"], "a computer, not a card")

    def test_consoles_and_their_accessories(self):
        c = lambda t: mad(t, 200, kind="console")  # noqa: E731
        self.assertEqual(c("PS5 Slim mit 2 Controllern")["specs"]["model"], "ps5 slim")
        self.assertEqual(c("Xbox Series S - guter Zustand - mit Rechnung")["specs"]["model"], "xbox series s")
        self.assertEqual(c("Nintendo Switch OLED + 3 Spiele")["specs"]["bundle"], "with games")
        for t in ("Original Nintendo Switch Pro Controller", "Xbox Series S Wireless Controller", "PS4 Spiele",
                  "Schale Case für PS Vita", "Red Dead Redemption 2 (PS4)"):
            self.assertIsNotNone(c(t)["junk"], t)

    def test_console_games_parts_and_editions(self):
        c = lambda t: mad(t, 450, kind="console")  # noqa: E731
        # games and parts named after the console, a controller whose model number the old code cut off
        for t in ("Madden NFL 25 PS5", "Taxi Life: A City Driving Simulator - PS5", "CD Minecraft PS5",
                  "Call of Duty Black Ops 6 PS5", "Playstation 5 Controller", "Xbox 360 Controller weiß",
                  "PS5 Laser 497A", "PS5 Lesekopf KEM-497", "PS5 OVP ohne Konsole", "PS 5 Frontblende"):
            self.assertIsNotNone(c(t)["junk"], t)
        for t in ("Sony PS5", "Verkaufe PS5", "Playstation 5 Disk Edition", "Nagelneue PS5", "PS5",
                  "PS4 Slim 2 Controller", "Sony Playstation 5 Konsole"):
            self.assertIsNone(c(t)["junk"], t)
        e = lambda t: c(t)["specs"].get("edition")  # noqa: E731
        self.assertEqual(e("PS5 Slim Disc"), "standard")
        self.assertEqual(e("PS5 30th Anniversary Limited Edition"), "limited")
        self.assertEqual(e("PS5 Jailbreak fähig Firmware 4.03"), "jailbreak")
        self.assertEqual(e("Nintendo Switch gemoddet"), "jailbreak")
        self.assertEqual(mad("PS5 Slim", 450, body="Kein Jailbreak, nicht gemoddet.", kind="console")["specs"]["edition"],
                         "standard")
        self.assertEqual(e("Steam Deck OLED 1TB"), "1024")
        b = lambda t: c(t)["specs"]["bundle"]  # noqa: E731
        self.assertEqual(b("PS5 + Monitor 27 Zoll"), "with extras")
        self.assertEqual(b("PS5 inkl. PS Portal"), "with extras")
        self.assertEqual(b("PS5 mit 2 Controllern"), "console only")
        self.assertEqual(market.query_specs("ps5", "console"), {"model": "ps5", "edition": "standard"})

    def test_laptop_models_cpus_and_accessories(self):
        lp = lambda t, **kw: mad(t, 300, kind="laptop", **kw)  # noqa: E731
        m = lambda t: lp(t)["specs"].get("model")  # noqa: E731
        self.assertEqual(m("Lenovo T430 i5 8GB"), "thinkpad t430")
        self.assertEqual(m("Lenovo ThinkPad X1 Carbon 6th Gen i7"), "thinkpad x1 carbon gen 6")
        self.assertEqual(m("ThinkPad T14s G2 Ryzen 5"), "thinkpad t14s gen 2")
        self.assertEqual(m("HP 840 G5 i5 16GB"), "elitebook 840 g5")
        self.assertEqual(m("Dell E7470 Notebook"), "latitude e7470")
        self.assertEqual(m("HP 450 G6 / i5-8265U / 8GB Ram"), "probook 450 g6")
        self.assertIsNone(m("Dell 5570 i5"))                       # Inspiron or Latitude: can't tell
        self.assertIsNone(lp("Apple MacBook Air 2020", body="256 GB SSD")["specs"]["ram"])
        self.assertEqual(m("Apple MacBook Air 13\" (2017) | i5 | 8GB RAM"), "macbook air 13 2017")
        self.assertEqual(m("Apple MacBook Pro 15,4\" Retina (Mid 2014) - 2,2 GHz i7"), "macbook pro 15 2014")
        self.assertEqual(m("MacBook Pro 13\" 2019 512gb"), "macbook pro 13 2019")
        self.assertEqual(m("Apple MacBook Air 13\" M1 8GB"), "macbook air m1")
        self.assertEqual(m("MacBook Air 15 Zoll M2"), "macbook air 15 m2")
        # a model-only key just for models that pin down one machine, not a line like "ideapad 5" or "thinkpad x1"
        sku = lambda t: lp(t)["specs"].get("sku")  # noqa: E731
        self.assertEqual(sku("Lenovo ThinkPad T480 i5-8350U 16GB"), "thinkpad t480")
        self.assertEqual(sku("Dell Latitude 7490"), "latitude 7490")
        self.assertEqual(sku("MacBook Air M1 8GB 256GB"), "macbook air m1")
        for t in ("Lenovo ThinkPad X1", "Lenovo IdeaPad 5 15\"", "Acer Aspire 3", "ThinkPad T14", "HP Elitebook 840",
                  "MacBook Pro 2019"):
            self.assertIsNone(sku(t), t)
        # older CPUs the laptop profile has no score for still get a generation
        c = lambda t: lp(t)["specs"].get("cpu")  # noqa: E731
        self.assertEqual(c("Lenovo ThinkPad T430 i5-3320M 8GB"), "Intel 2/3rd")
        self.assertEqual(c("HP 840 G2 Core i5-5300U"), "Intel 4/5th")
        self.assertEqual(c("Acer Aspire Celeron N4020 4GB"), "Intel Celeron/Pentium")
        for t in ("ThinkPad OneLink Pro Dock (4X10E52935)", "Lenovo ThinkPad X13 Aufkleber",
                  "Apple 85W MagSafe Power Adapter - Original", "LTE 4G Modem Module - WWAN",
                  "ASUS Zenbook 14 Flip Original Touchpad"):
            self.assertIsNotNone(lp(t)["junk"], t)
        self.assertIsNone(lp("ThinkPad T480 mit Docking Station")["junk"])
        self.assertEqual(market.query_specs("thinkpad t480", "laptop"), {"model": "thinkpad t480", "sku": "thinkpad t480"})

    def test_cpu_models_xeon_old_intel_amd_and_not_cpus(self):
        cpu = lambda t, body="": mad(t, 50, body=body, kind="cpu")  # noqa: E731
        for t, model in (("CPU Intel Xeon X5675", "xeon x5675"), ("Intel xeon E3 1220 v3", "xeon e3-1220v3"),
                         ("XEION E5-2667V4 CPU", "xeon e5-2667v4"), ("Intel Xeon E5-1630v3", "xeon e5-1630v3"),
                         ("Epyc 7401p", "epyc 7401p"), ("CPU Intel i3-380", "i3-380"), ("i7 920 2,66 GHz", "i7-920"),
                         ("Intel Pentium Gold G5400T CPU 3.10GHz", "pentium g5400t"),
                         ("Intel Core i5 CPU 10500T (LGA1200)", "i5-10500t"),
                         ("INTEL Core 2 Duo E 6750 boxed", "core2 e6750"), ("CPU AMD A8-6600 inkl. Kühler", "amd a8-6600"),
                         ("AMD Rysen5 3600 + passenden Kühler", "ryzen 5 3600"), ("Ryzen 3600", "ryzen 5 3600"),
                         ("AMD 5800X3D", "ryzen 7 5800x3d"), ("Threadripper 1950X", "threadripper 1950x"),
                         ("Intel Core i7-7820X, 8 Kerne", "i7-7820x"), ("I7 7820x Prozessor", "i7-7820x"),
                         ("Intel Xeon W3550 | 3.06GHz | LGA 1366 | wie ein i7 950", "xeon w3550")):
            self.assertEqual(cpu(t)["specs"].get("model"), model, t)
        self.assertIsNone(cpu("AMD Ryzen 9", "Dazu passt RAM mit 3200 MHz")["specs"]["model"])
        self.assertEqual(cpu("AMD Ryzen 7 3700x inkl. CPU-Kühler - Alpenföhn")["specs"]["model"], "ryzen 7 3700x")
        self.assertEqual(cpu("AMD Ryzen 5 5600 boxed mit Wraith Stealth Cooler")["specs"]["model"], "ryzen 5 5600")
        self.assertEqual(cpu("AMD Phenom II X4 955 Black Edition + Scythe CPU-Kühler")["specs"]["model"], "phenom ii x4 955")
        for t in ("2x Intel Xeon E5-2603 v2 - 1.60GHz", "Siemens Simatic S7 SM 1223 DC/ DC I/ O Modul",
                  "Supermicro SNK-P0048AP4 - 2U Xeon CPU-Kühler", "AMD EPYC Genoa 9334 32 Core Engineering Sample",
                  "Arduino ESP32 Microcontroller Starter Set"):
            self.assertIsInstance(cpu(t)["junk"], str, t)

    def test_mainboard_chipsets_from_board_names_and_not_boards(self):
        mb = lambda t: mad(t, 50, kind="mainboard")  # noqa: E731
        for t, chip in (("ASUS M5A97 R2.0", "970"), ("ASUS M5A78L-M/ USB3", "760g"), ("Gigabyte Z 390 LGA 1151", "z390"),
                        ("ASUS Z-790 P Mainboard Neu", "z790"), ("Gigabyte GA-F2A88XM-HD3P - Micro ATX", "a88x"),
                        ("Neu Asus Mainboard F2 A85-V PRO", "a85x"), ("ASRock 870 Extreme 3, Socket AM3", "870"),
                        ("MSI X399 Gaming Pro Carbon", "x399"), ("Gigabyte B450M DS3H", "b450")):
            self.assertEqual(mb(t)["specs"].get("chipset"), chip, t)
        for t in ("Asus M4A89GTD PRO + AMD Phenom II X6 1090T", "Asrock A88M itx/ ac 8gb ram und amd A10",
                  "Apple Logic Board MacBook Pro 15\" Early 2013", "HP EliteOne 800 G3 AIO Hauptplatine",
                  "Arduino Portenta Max Carrier", "Retro Set Intel E8600 + Intel Board + 4GB Ram"):
            self.assertIsInstance(mb(t)["junk"], str, t)

    def test_audio_models_one_spelling_and_series(self):
        a = lambda t, kind="headphones": mad(t, 100, kind=kind)["specs"]  # noqa: E731
        for t in ("Sony WH-1000XM4", "Sony WH 1000 XM4 Kopfhörer", "WH-1000XM4 Noise Cancelling"):
            self.assertEqual(a(t)["model"], "sony wh1000xm4", t)
        self.assertEqual(a("Sony WH-1000XM4")["series"], "sony wh1000")
        for t in ("Ohrstöpsel aus Silikon für Beats Flex, X oder Powerbeats Pro", "Air Pods Pro Schachtel LEER",
                  "Ladeschale für Samsung Galaxy Buds SM-R170"):
            self.assertIsInstance(mad(t, 10, kind="headphones")["junk"], str, t)
        self.assertEqual(a("Bose QuietComfort 35 II")["model"], "bose qc35ii")
        self.assertEqual(a("Bose QuietComfort 35 II")["series"], "bose qc35")
        self.assertEqual(a("Bose QC Ultra Headphones")["model"], "bose qc ultra")
        self.assertEqual(a("DT 990 Pro 250 Ohm")["model"], "beyerdynamic dt990pro")
        self.assertEqual(a("Sennheiser HD 600")["model"], a("Sennheiser HD600")["model"])
        for t, model in (("Beats Studio Pro schwarz", "beats studio pro"), ("Shokz OpenRun Pro", "shokz openrunpro"),
                         ("Samsung Galaxy Buds 2 Pro", "samsung galaxy buds 2 pro"), ("Marshall Monitor II", "marshall monitor ii"),
                         ("Airpod Max Gen 1", "airpods max 1"), ("Air Pods Generation 2", "airpods 2"),
                         ("Teufel Supreme On Kopfhörer Bluetooth", "teufel supreme on")):
            self.assertEqual(a(t)["model"], model, t)
        self.assertIsNone(a("Bluetooth Kopfhörer in ear")["model"])
        self.assertEqual(a("JBL Kopfhörer Tune 510 BT")["model"], a("JBL Tune 510BT On-Ear")["model"])
        self.assertEqual(a("Anker Soundcore Q30")["model"], a("soundcore by Anker Q30")["model"])
        self.assertIsNotNone(mad("Airpod 3 ( Recht )", 30, kind="headphones")["junk"])
        tt = lambda t: a(t, "turntable")  # noqa: E731
        self.assertEqual(tt("Technics SL-1210 MK2")["model"], "technics sl1210mk2")
        self.assertEqual(tt("Technics SL-1210 MK2")["series"], "technics sl1200")
        self.assertEqual(tt("Technics SL1200 MK7 silber")["series"], "technics sl1200")
        self.assertEqual(tt("Technics 1210 MK2 DJ Turntable")["model"], "technics sl1210mk2")
        self.assertEqual(tt("Technics SL-1200M7L 50th Anniversary")["series"], "technics sl1200")
        for t in ("Technics SL-1210 Mk2 Plattenspieler (2x Stück)", "Technics SL-1210 MK2 (Paar)",
                  "Technics SL-BD3 - Anleitung im Original", "Technics SL-1210 M5G Headshell Neu!",
                  "Technics EPA-A501G Tonarm"):
            self.assertIsInstance(mad(t, 500, kind="turntable")["junk"], str, t)
        self.assertEqual(tt("TECHNICS 1210 MK2 inclusive CASE von THON")["model"], "technics sl1210mk2")
        self.assertEqual(tt("Pro-Ject Debut Carbon EVO")["model"], "project debutcarbonevo")
        self.assertEqual(a("Denon AVR-X1600H", "hifi")["model"], "denon avrx1600h")

    def test_phones_keep_battery_notes_but_drop_cases(self):
        p = mad("iPhone 16 Pro 256GB | 90% Akku", 700, kind="phone")
        self.assertIsNone(p["junk"])
        self.assertEqual(p["specs"], {"model": "iphone 16 pro", "storage": 256})
        self.assertEqual(mad("Galaxy S23 Ultra", 500, kind="phone", tattrs="[7215;7216]")["specs"]["storage"], 256)
        self.assertIsNotNone(mad("iPhone 15 Pro Hülle neu", 8, kind="phone")["junk"])
        self.assertIsNone(mad("Samsung Galaxy XCover 7", 130, kind="phone")["junk"])
        self.assertIsNotNone(mad("IPHONE 14 PRO LCD & AUSTAUSCH ! SOFORT", 100, kind="phone")["junk"])
        self.assertIsNotNone(mad("Nintendo Gameboy Advance Spider-Man GBA PAL", 10, kind="console")["junk"])
        self.assertIsNone(mad("Gameboy Advance SP Konsole PAL", 60, kind="console")["junk"])
        self.assertIsNotNone(mad("Apple Airpods 4 Ladecase", 40, kind="headphones")["junk"])
        self.assertIsNone(mad("JBL Tune 500BT On-Ear Kopfhörer kabellos", 34, kind="headphones")["junk"])
        self.assertIsNotNone(mad("Sennheiser HD 600 Kabel 3m", 20, kind="headphones")["junk"])
        self.assertEqual(market.query_specs("", "laptop"), {})

    def test_tv_codes_sizes_and_parts(self):
        s = mad("LG OLED55C17LB", 600, kind="tv")["specs"]
        self.assertEqual((s["brand"], s["series"], s["size"], s["panel"], s["year"]), ("lg", "oled c1", 55, "oled", 2020))
        s = mad("Samsung GQ55Q80T 4K", 500, kind="tv")["specs"]
        self.assertEqual((s["series"], s["panel"]), ("q80t", "qled"))
        self.assertEqual(mad("Fernseher 139 cm", 100, kind="tv")["specs"]["size"], 55)
        self.assertEqual(mad("Fernseher", 100, kind="tv", tattrs="[5807;7316]")["specs"]["size"], 55)
        s = mad("Samsung Fernseher UE55U7020FU", 350, kind="tv")["specs"]
        self.assertEqual((s["series"], s["size"], s["res"]), ("u7020", 55, "4k"))
        s = mad("Samsung UE46F6640SS", 150, kind="tv")["specs"]
        self.assertEqual((s["series"], s["year"], s["res"]), ("f6640", 2012, None))      # 2013, in two-year steps
        self.assertEqual(mad("Samsung UE55NU7400", 300, kind="tv")["specs"]["year"], 2018)
        self.assertEqual(mad("Samsung Fernseher LE32D551", 30, kind="tv")["specs"]["series"], "d551")
        self.assertEqual(mad("Philips 55OLED808 55\" Ambilight", 700, kind="tv")["specs"]["series"], "oled808")
        for t, series in (("LG49UH6109 Fernseher TV", "uh6109"), ("LG Fernseher 42LE4500", "le4500"),
                          ("LG Smart TV 43 Zoll - Modell 43LH590V-ZD - webOS", "lh590"),
                          ("Philips 32PFL5007K Fernseher", "pfl5007")):
            self.assertEqual(mad(t, 50, kind="tv")["specs"]["series"], series, t)
        for t in ("Samsung Netzteil für Smart TV", "Rückwand eines QE50Q60T", "LG 55UK Komplettchassis da Displaybruch",
                  "Bedienungsanleitung User Guide Samsung TV UE46F6640SS"):
            self.assertIsNotNone(mad(t, 20, kind="tv")["junk"], t)

    def test_defect_condition_is_junk(self):
        self.assertEqual(mad("RTX 3080", 300, kind="gpu", tattrs="[21;24]")["junk"], "marked defect")
        self.assertEqual(mad("RTX 3080", 300, kind="gpu", tattrs="[21;2546]")["cond"], "like new")


class MarketValueTests(unittest.TestCase):
    def kits(self, prices, title="Kingston 2x16GB DDR4 3200", sellers=None, **kw):
        return [mad(title, p, seller=(sellers[n] if sellers else "s%d" % n), i=1000 + n, **kw) for n, p in enumerate(prices)]

    def test_value_is_a_robust_median_with_one_vote_per_seller(self):
        ads = self.kits([90, 95, 100, 100, 105, 110, 2000])                       # 2000: an outlier
        ads += [mad("Kingston 2x16GB DDR4 3200", 40, seller="dealer", i=2000 + n) for n in range(10)]   # one seller
        idx = market.build_index(ads, "ram")
        est = market.value_of(idx, "ram", ads[0]["specs"])
        self.assertEqual(est["value"], 100)
        self.assertEqual(est["n"], 7)          # the dealer's 10 ads count once, the outlier is dropped
        self.assertEqual(est["level"], ("gen", "form", "kit", "speed"))

    def test_too_few_sellers_fall_back_to_a_looser_key(self):
        ads = self.kits([100, 100])                                                  # 3200: only 2 sellers
        ads += self.kits([80, 85, 90, 95, 100], title="Kingston 2x16GB DDR4 2666")
        for n, a in enumerate(ads):
            a["id"] = 3000 + n
            a["seller"] = "x%d" % n
        idx = market.build_index(ads, "ram")
        est = market.value_of(idx, "ram", ads[0]["specs"])
        self.assertEqual(est["level"], ("gen", "form", "kit"))
        self.assertIsNone(market.value_of({}, "ram", ads[0]["specs"]))

    def test_series_key_values_only_specs_without_a_generation(self):
        ads = [mad("Technics SL-1210 MK2", p, seller="a%d" % n, i=4000 + n, kind="turntable")
               for n, p in enumerate([500, 520, 540, 560, 580])]
        ads += [mad("Technics SL-1200 MK7", 900, seller="b%d" % n, i=4100 + n, kind="turntable") for n in range(2)]
        idx = market.build_index(ads, "turntable")
        est = market.value_of(idx, "turntable", market.query_specs("technics sl1200", "turntable"))
        self.assertEqual(est["level"], ("series",))                 # no generation named: all SL-1200s
        self.assertIsNone(market.value_of(idx, "turntable", ads[-1]["specs"]))   # an MK7 is not valued as an MK2

    def test_dealer_new_stock_and_junk_dont_count(self):
        ads = self.kits([100, 100, 100])
        ads.append(mad("Kingston 2x16GB DDR4 3200", 300, seller="shop", private=0, tattrs="[21;22]", i=9))
        ads.append(mad("Kingston 2x16GB DDR4 3200 defekt", 10, seller="z", i=10))
        est = market.value_of(market.build_index(ads, "ram"), "ram", ads[0]["specs"])
        self.assertEqual((est["value"], est["n"]), (100, 3))

    def test_deal_flags_urgent_sales_instead_of_hiding_them(self):
        est = dict(value=200.0, conf="high")
        cheap = mad("RTX 3070 Notverkauf, muss weg", 60, kind="gpu")
        d = market.deal(cheap, est)
        self.assertEqual(d["discount"], 0.7)
        self.assertEqual(d["urgent"], "notverkauf")
        self.assertTrue(any("urgent sale" in f for f in d["flags"]))
        self.assertFalse(market.odd(dict(cheap, **d)))           # explained: stays in the main ranking
        plain = mad("RTX 3070", 60, kind="gpu")
        self.assertTrue(market.odd(dict(plain, **market.deal(plain, est))))

    def test_queries(self):
        self.assertEqual(market.guess_kind("2x16gb ddr4 3200"), "ram")
        self.assertEqual(market.guess_kind("rtx 3070"), "gpu")
        self.assertEqual(market.guess_kind("ps5 slim"), "console")
        self.assertEqual(market.guess_kind("tv 45-55 zoll"), "tv")
        want = market.query_specs("2x16gb ddr4 3200", "ram")
        self.assertEqual(want, {"gen": "ddr4", "form": "dimm", "kit": "2x16", "speed": 3200})
        self.assertTrue(market.matches({"gen": "ddr4", "form": "dimm", "kit": "2x16", "speed": 3600}, want))  # faster ok
        self.assertFalse(market.matches({"gen": "ddr4", "form": "dimm", "kit": "2x16", "speed": 2666}, want))
        self.assertFalse(market.matches({"gen": "ddr4", "form": "sodimm", "kit": "2x16", "speed": 3200}, want))
        self.assertEqual(market.size_range("tv 45-55 zoll"), (45, 55))
        self.assertTrue(market.matches({"size": 50}, {}, (45, 55)))
        self.assertFalse(market.matches({"size": 65}, {}, (45, 55)))


class FindWatchTests(TmpDbCase):
    """find and watch on a database filled through store(), the way crawls fill it."""
    RAM = "pc-komponenten/ram-speicher-arbeitsspeicher-5887"

    def fill(self, c, ads, at, full=True):
        wh.store(c, [wh.summary(a) for a in ads], at)
        if full:
            wh.record_crawl(c, wh.search_url(url=self.RAM), self.RAM, len(ads), True, at)
        c.commit()

    def market_ads(self, start=100):
        return [make_summary(start + n, "Kingston 2x16GB DDR4 3200", p, cats="5824;5878;5887") for n, p in
                enumerate([95, 100, 100, 105, 110, 98, 102])]

    def setUp(self):
        super().setUp()
        self.cfg = tempfile.TemporaryDirectory()
        self.addCleanup(self.cfg.cleanup)
        wh._ROWS.clear()
        p = mock.patch.object(wh, "WATCHES", os.path.join(self.cfg.name, "watches.toml"))
        p.start()
        self.addCleanup(p.stop)

    def args(self, **kw):
        base = dict(kind=None, size=None, min=None, max=None, area=None, details=0, limit=15, no_crawl=True,
                    md=False, json=True, all=False, below=0.15)
        base.update(kw)
        return argparse_ns(**base)

    def test_old_database_gets_the_new_columns(self):
        import sqlite3
        old = sqlite3.connect(self.db_path)
        old.executescript("create table ads (id integer primary key, title text, price real, loc text, state text, "
                          "postcode text, private integer, published text, url text, body text, cats text, "
                          "first_seen text, last_seen text); insert into ads (id, title) values (1, 'x');")
        old.commit()
        old.close()
        c = wh.db()
        self.addCleanup(c.close)
        cols = {r["name"] for r in c.execute("pragma table_info(ads)")}
        self.assertTrue({"tattrs", "seller", "p2p", "coords"} <= cols)
        self.assertEqual(c.execute("select title from ads where id=1").fetchone()[0], "x")

    def test_find_lists_ads_below_value_best_first(self):
        c = wh.db()
        self.addCleanup(c.close)
        ads = self.market_ads() + [make_summary(900, "G.Skill 32GB 2x16GB DDR4 3200", 60, cats="5824;5878;5887"),
                                   make_summary(901, "Kingston 2x16GB DDR4 2400", 30, cats="5824;5878;5887")]
        self.fill(c, ads, wh.now())
        out = io.StringIO()
        with mock.patch.object(wh, "db", return_value=c), mock.patch("sys.stdout", out), \
                mock.patch.object(wh, "fetch") as fetch:
            wh.cmd_find(self.args(words=["2x16gb", "ddr4", "3200"]))
        fetch.assert_not_called()
        r = json.loads(out.getvalue())
        self.assertEqual(r["kind"], "ram")
        self.assertEqual(r["market"]["value"], 100)
        self.assertEqual([d["id"] for d in r["deals"]], [900])          # the 2400 kit doesn't match, the rest is fair
        self.assertEqual(r["deals"][0]["discount"], 0.4)
        self.assertTrue(r["deals"][0]["comps"])

    def test_value_finds_the_kind_of_a_model_query_from_the_database(self):
        c = wh.db()
        self.addCleanup(c.close)
        mon = [make_summary(700 + n, t, p, cats="5824;5849") for n, (t, p) in enumerate([
            ("Dell U2723QE 27 Zoll 4K", 400), ("DELL U2723QE Monitor", 420), ("Dell UltraSharp U2723-QE", 380),
            ("Dell U2723QE wie neu", 410)])]
        cams = [make_summary(800 + n, t, 900, cats="5824;7777") for n, t in enumerate(
            ["Sony A7 III Body", "Sony A7III mit Objektiv", "Sony a7 iii Kit"])]
        self.fill(c, mon + cams + [make_summary(810, "Sony A7 III Kopfhörer?", 50, cats="5824;6813")], wh.now())
        self.assertIsNone(market.guess_kind("dell u2723qe"))
        self.assertEqual(wh.kind_from_db(c, "dell u2723qe"), "monitor")
        self.assertIsNone(wh.kind_from_db(c, "sony a7 iii"))             # a camera: most ads with these words are no kind
        self.assertIsNone(wh.kind_from_db(c, "sony xyz9"))
        out = io.StringIO()
        with mock.patch.object(wh, "db", return_value=c), mock.patch("sys.stdout", out), \
                mock.patch.object(wh, "fetch") as fetch:
            wh.cmd_value(self.args(words=["dell", "u2723qe"], price=None))
        fetch.assert_not_called()
        r = json.loads(out.getvalue())
        self.assertEqual((r["kind"], r["value"]["value"], r["value"]["n"]), ("monitor", 400, 4))
        with mock.patch.object(wh, "db", return_value=c), self.assertRaisesRegex(wh.WhError, "can't tell"):
            wh.cmd_value(self.args(words=["sony", "a7", "iii"], price=None))

    def test_watch_reports_new_or_cheaper_ads_once_and_not_the_starting_stock(self):
        c = wh.db()
        self.addCleanup(c.close)
        cheap = make_summary(900, "G.Skill 2x16GB DDR4 3200", 60, cats="5824;5878;5887")
        self.fill(c, self.market_ads() + [cheap], "2026-11-01T00:00:00Z")      # first full crawl: starting stock
        wh.save_watches([dict(name="ram", query="2x16gb ddr4 3200", below=0.2, conf="low")])
        def run():
            wh._ROWS.clear()
            out = io.StringIO()
            with mock.patch.object(wh, "db", return_value=c), mock.patch("sys.stdout", out):
                wh.cmd_watch(argparse_ns(action="run", args=[], json=True, no_crawl=True, dry_run=False, details=0))
            return [d["id"] for d in json.loads(out.getvalue())["watches"][0]["deals"]]
        self.assertEqual(run(), [])                                          # 900 was there from the start
        self.fill(c, [make_summary(901, "Kingston Fury 2x16GB DDR4 3200", 55, cats="5824;5878;5887")],
                  wh.now(), full=False)
        self.assertEqual(run(), [901])                                       # new and cheap
        self.assertEqual(run(), [])                                          # reported once
        self.fill(c, [make_summary(901, "Kingston Fury 2x16GB DDR4 3200", 45, cats="5824;5878;5887")],
                  wh.now(), full=False)
        self.assertEqual(run(), [901])                                       # cheaper again: reported again

    def test_parse_time_is_the_strict_utc_format_only(self):
        from datetime import datetime, timezone
        self.assertEqual(market.parse_time("2026-11-09T22:20:31Z"),
                         datetime(2026, 11, 9, 22, 20, 31, tzinfo=timezone.utc))
        for bad in (None, "", 5, "2026-11-09 22:20:31Z", "2026-11-09T22:20:31", "2026-11-09T22:20:31+0000", "x" * 20):
            self.assertIsNone(market.parse_time(bad), bad)

    def test_watch_budget_skips_the_rest_and_runs_those_first_next_time(self):
        c = wh.db()
        self.addCleanup(c.close)
        wh.save_watches([dict(name="a", query="2x16gb ddr4 3200"), dict(name="b", query="2x16gb ddr4 3200"),
                         dict(name="c", query="2x16gb ddr4 3200")])
        ran = []
        clock = [0.0]

        def fake_run(c_, w, details_n, record=True):
            ran.append(w["name"])
            clock[0] += 10                                                   # every watch "takes" 10 s
            c_.execute("insert or replace into watch_runs values (?,?)", (w["name"], "2026-11-09T0%d:00:00Z" % len(ran)))
            return dict(name=w["name"], deals=[], market=None, query="", wants="", kind="ram", below=0.25)

        def run(budget):
            ran.clear()
            out = io.StringIO()
            with mock.patch.object(wh, "db", return_value=c), mock.patch.object(wh, "run_watch", fake_run), \
                    mock.patch.object(wh.time, "monotonic", lambda: clock[0]), mock.patch("sys.stdout", out), \
                    mock.patch("sys.stderr", io.StringIO()):
                wh.cmd_watch(argparse_ns(action="run", args=[], json=True, no_crawl=True, dry_run=False, details=0,
                                         budget=budget))
            return json.loads(out.getvalue())
        r = run(15)                                                          # a and b start (0 s, 10 s), c is skipped
        self.assertEqual((ran, r["skipped"]), (["a", "b"], ["c"]))
        r = run(15)                                                          # c has never run: it goes first
        self.assertEqual(ran[0], "c")
        self.assertEqual(len(r["watches"]) + len(r["skipped"]), 3)
        r = run(None)                                                        # no budget: everything runs
        self.assertEqual((len(ran), r["skipped"]), (3, []))

    def test_watch_run_builds_the_market_index_once_per_kind(self):
        c = wh.db()
        self.addCleanup(c.close)
        self.fill(c, self.market_ads(), "2026-11-01T00:00:00Z")
        wh._ROWS.clear()
        wh._IDX.clear()
        with mock.patch.object(market, "build_index", wraps=market.build_index) as bi:
            wh.find_deals(c, "ram", {}, details_n=0, cache=True)
            wh.find_deals(c, "ram", {}, details_n=0, cache=True)
        self.assertEqual(bi.call_count, 1)
        wh._ROWS.clear()
        wh._IDX.clear()

    def test_watch_file_round_trip(self):
        out = io.StringIO()
        with mock.patch("sys.stdout", out):
            wh.cmd_watch(argparse_ns(action="add", args=["tv", ""], kind="tv", size="45-55", min=None, max=None,
                                     below=0.4, conf="high", area="wien", for_=None))
            wh.cmd_watch(argparse_ns(action="add", args=["ram", "2x16gb", "ddr4"], kind=None, size=None, min=None,
                                     max=150.0, below=0.25, conf="medium", area=None, for_="homelab"))
        ws = wh.load_watches()
        self.assertEqual([w["name"] for w in ws], ["tv", "ram"])
        self.assertEqual((ws[0]["query"], ws[0]["size"], ws[1]["max"], ws[1]["for"]), ("", "45-55", 150.0, "homelab"))
        with mock.patch("sys.stdout", out):
            wh.cmd_watch(argparse_ns(action="rm", args=["tv"]))
        self.assertEqual([w["name"] for w in wh.load_watches()], ["ram"])

    def test_specs_are_cached_until_the_ad_changes(self):
        c = wh.db()
        self.addCleanup(c.close)
        self.fill(c, self.market_ads(), wh.now())
        rows = wh.kind_rows(c, "ram")
        self.assertEqual(c.execute("select count(*) from specs").fetchone()[0], len(rows))
        with mock.patch.object(market, "specs", side_effect=AssertionError("recomputed")):
            wh.kind_rows(c, "ram")                                        # all from the cache
        self.fill(c, [make_summary(100, "Kingston 2x8GB DDR4 3200", 50, cats="5824;5878;5887")], wh.now(), full=False)
        rows = {r["id"]: r for r in wh.kind_rows(c, "ram")}
        self.assertEqual(rows[100]["specs"]["kit"], "2x8")

    def test_full_crawl_stores_one_category_before_reading_the_next(self):
        c = wh.db()
        self.addCleanup(c.close)
        seen = []                                         # ads in the database when each category's page 1 is read
        cats = {"laptops-5824": make_summary(700, "ThinkPad T480", 300, cats="5824"),
                "pc-komponenten/arbeitsspeicher-5878": make_summary(701, "Kingston 2x16GB DDR4 3200", 90, cats="5824;5878")}

        def fake(url, binary=False):
            seen.append(c.execute("select count(*) from ads").fetchone()[0])
            p = next(k for k in cats if k in url)
            return url, search_page(1, [cats[p]])
        with mock.patch.object(wh, "fetch", side_effect=fake), mock.patch.object(wh, "log"), \
             mock.patch.object(wh, "kind_rows"), mock.patch.object(wh, "prune"), \
             mock.patch.dict(market.KINDS, {"x": dict(market.KINDS["ram"], cats=["marktplatz/" + p for p in cats])}):
            wh.crawl(c, ["x"], full=True)
        self.assertEqual(seen, [0, 1])

    def test_crawl_summary_says_when_willhaben_pushed_back(self):
        self.assertEqual(wh.pushback_note(1000.0), "")
        with mock.patch.object(wh, "log"), mock.patch.object(wh.time, "time", return_value=1120.0):
            wh.slow_down("HTTP 429")
        self.assertIn("pushed back after 120 s", wh.pushback_note(1000.0))

    def test_crawl_new_stops_at_a_page_with_nothing_new(self):
        c = wh.db()
        self.addCleanup(c.close)
        known = self.market_ads()
        self.fill(c, known, wh.now())
        pages = {1: search_page(1000, [make_summary(950, "Neu 2x16GB DDR4 3200", 90, cats="5824;5878;5887")] + known[:3]),
                 2: search_page(1000, known[3:]), 3: search_page(1000, [])}
        calls = []
        def fake(url, binary=False):
            n = int(re.search(r"page=(\d+)", url).group(1))
            calls.append(n)
            return url, pages[n]
        with mock.patch.object(wh, "fetch", side_effect=fake):
            wh.crawl_new(c, [self.RAM])
        self.assertEqual(calls, [1, 2])
        self.assertIsNotNone(c.execute("select id from ads where id=950").fetchone())

    def crawl_args(self, **kw):
        return mock.Mock(**dict(dict(kinds=["ram"], list=False, full=False, new=True, budget=None), **kw))

    def test_a_crawl_that_read_nothing_is_not_recorded_and_fails(self):
        c = wh.db()
        self.addCleanup(c.close)
        cats = market.KINDS["ram"]["cats"]
        for broken in (wh.FetchError("boom"), "<html>no data</html>"):
            def fake(url, binary=False):
                if isinstance(broken, Exception):
                    raise broken
                return url, broken
            for new in (True, False):
                with mock.patch.object(wh, "db", return_value=c), mock.patch.object(wh, "fetch", side_effect=fake), \
                     mock.patch.object(wh, "log"), mock.patch.object(wh, "kind_rows"), mock.patch.object(wh, "prune"):
                    with self.assertRaises(wh.WhError) as e:
                        wh.cmd_crawl(self.crawl_args(new=new, full=not new))
                self.assertIn("read nothing", str(e.exception))
        self.assertEqual(c.execute("select count(*) from runs").fetchone()[0], 0)
        self.assertEqual(len(cats), len(set(cats)))

    def test_a_crawl_with_one_failed_category_warns_and_succeeds(self):
        c = wh.db()
        self.addCleanup(c.close)
        cats = ["marktplatz/a-1", "marktplatz/b-2"]
        ok = search_page(1, [make_summary(900, "Kamera", 10, cats="1")])

        def fake(url, binary=False):
            if "b-2" in url:
                raise wh.FetchError("boom")
            return url, ok
        with mock.patch.object(wh, "db", return_value=c), mock.patch.object(wh, "fetch", side_effect=fake), \
             mock.patch.object(wh, "log") as log, mock.patch.object(wh, "kind_rows"), mock.patch.object(wh, "prune"), \
             mock.patch.dict(market.KINDS, {"x": dict(market.KINDS["ram"], cats=cats)}):
            wh.cmd_crawl(self.crawl_args(kinds=["x"], new=True))
        self.assertTrue(any("1 of 2 categories could not be read" in str(x) for x in log.call_args_list))
        self.assertEqual(c.execute("select count(*) from runs").fetchone()[0], 1)

    def test_crawl_new_keeps_the_pages_read_before_a_failing_page(self):
        c = wh.db()
        self.addCleanup(c.close)
        new = [make_summary(950 + n, "Neu 2x16GB DDR4 3200", 90 + n, cats="5824;5878;5887") for n in range(3)]

        def fake(url, binary=False):
            n = int(re.search(r"page=(\d+)", url).group(1))
            if n == 2:
                raise wh.FetchError("boom")
            return url, search_page(5000, new[:1])
        partial = []
        with mock.patch.object(wh, "fetch", side_effect=fake), mock.patch.object(wh, "log"):
            out = wh.crawl_new(c, [self.RAM], partial=partial)
        self.assertEqual(partial, [self.RAM])
        self.assertEqual(len(out[self.RAM][1]), 1)
        self.assertIsNotNone(c.execute("select id from ads where id=950").fetchone())

    def test_crawl_new_budget_stops_reading_but_keeps_what_it_read(self):
        c = wh.db()
        self.addCleanup(c.close)
        known = self.market_ads()
        self.fill(c, known, wh.now())
        new = [make_summary(950 + n, "Neu 2x16GB DDR4 3200", 90 + n, cats="5824;5878;5887") for n in range(3)]
        calls = []
        clock = [0.0]

        def fake(url, binary=False):
            n = int(re.search(r"page=(\d+)", url).group(1))
            calls.append(n)
            clock[0] += 30                                                   # every page "takes" 30 s
            return url, search_page(5000, new[n - 1:n])                      # always something new: would go on
        with mock.patch.object(wh, "fetch", side_effect=fake), mock.patch.object(wh.time, "monotonic", lambda: clock[0]):
            wh.crawl_new(c, [self.RAM], budget=40)
        self.assertEqual(calls, [1, 2])                                      # page 3 was not started
        self.assertEqual(c.execute("select count(*) from ads where id between 950 and 952").fetchone()[0], 2)


class GenericFindTests(TmpDbCase):
    RAM, fill, market_ads, args = FindWatchTests.RAM, FindWatchTests.fill, FindWatchTests.market_ads, FindWatchTests.args

    def run_find(self, c, labels=None, no_ai=False):
        ads = [make_summary(500 + n, t, p, cats="5824;6808") for n, (t, p) in enumerate([
            ("Sony A7 III Body", 850), ("Sony Alpha 7 III", 900), ("Sony a7iii Gehäuse", 800), ("Sony A7 III", 880),
            ("Sony A7 III Akku", 30), ("Sony A7 III", 500)])]
        out = io.StringIO()
        fake = lambda q, batch, model, timeout=240: labels(batch)  # noqa: E731
        with mock.patch.object(wh, "db", return_value=c), mock.patch("sys.stdout", out), \
                mock.patch.object(wh, "fetch", return_value=("u", search_page(len(ads), ads))), \
                mock.patch.object(wh, "ask_labels", side_effect=fake), \
                mock.patch.object(wh.shutil, "which", return_value="/usr/bin/claude"):
            wh.cmd_find(self.args(words=["sony", "a7", "iii"], pages=1, no_ai=no_ai))
        return json.loads(out.getvalue())

    def test_claude_names_the_products_and_accessories_drop_out(self):
        c = wh.db()
        self.addCleanup(c.close)
        def labels(batch):
            out = [dict(id=0, product="sony alpha 7 iii", variant="", item=True, same=True)]
            for a in batch:
                acc = "akku" in a["title"].lower()
                out.append(dict(id=a["id"], product="sony np-fz100" if acc else "sony alpha 7 iii", variant="",
                                item=True, same=not acc))
            return out
        r = self.run_find(c, labels)
        self.assertEqual(r["wants"], "sony alpha 7 iii")
        self.assertEqual(r["matching"], 5)
        self.assertEqual(r["market"]["value"], 850)
        self.assertEqual([d["id"] for d in r["deals"]], [505])           # €500 against €850
        self.assertEqual(c.execute("select count(*) from products").fetchone()[0], 6)

    def test_without_claude_every_title_with_the_words_counts_at_low_confidence(self):
        c = wh.db()
        self.addCleanup(c.close)
        r = self.run_find(c, no_ai=True)
        self.assertEqual(r["market"]["conf"], "low")
        self.assertIn("all these words", r["wants"])

    def test_prune_forgets_old_ads_but_keeps_note_ads(self):
        c = wh.db()
        self.addCleanup(c.close)
        self.fill(c, self.market_ads(), "2026-01-01T00:00:00Z")
        run = c.execute("insert into runs (key, url, at, found, complete) values ('note:X:u','u','2026-01-01T00:00:00Z',1,1)")
        c.execute("insert into hits values (?, 100)", (run.lastrowid,))
        wh.prune(c, days=30)
        self.assertEqual([r[0] for r in c.execute("select id from ads")], [100])

    def test_deal_gets_the_market_value(self):
        c = wh.db()
        self.addCleanup(c.close)
        self.fill(c, self.market_ads() + [make_summary(900, "G.Skill 2x16GB DDR4 3200", 60, cats="5824;5878;5887")],
                  wh.now())
        d = dict(id=900, title="G.Skill 2x16GB DDR4 3200", price=60.0, descr="", info=[])
        block = wh.market_block(c, d)
        self.assertIn("Value €100", block)
        self.assertIn("-40 %", block)
        self.assertEqual(wh.market_block(c, dict(d, id=12345)), "")


def argparse_ns(**kw):
    import argparse
    return argparse.Namespace(**kw)


if __name__ == "__main__":
    unittest.main()
