import gzip
import importlib.machinery
import importlib.util
import io
import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

import profiles

loader = importlib.machinery.SourceFileLoader("wh_mod", os.path.join(os.path.dirname(__file__), "wh"))
spec = importlib.util.spec_from_loader("wh_mod", loader)
wh = importlib.util.module_from_spec(spec)
loader.exec_module(wh)


def next_page(obj):
    return '<html><head><script id="__NEXT_DATA__" type="application/json">%s</script></head></html>' % json.dumps(
        {"props": {"pageProps": obj}})


def make_summary(ad_id, heading, price, body="", seo="", cats="5824;5831", private="1", loc="Wien"):
    return {
        "id": str(ad_id),
        "description": heading,
        "attributes": {"attribute": [
            {"name": "HEADING", "values": [heading]},
            {"name": "PRICE", "values": [str(price)] if price is not None else []},
            {"name": "LOCATION", "values": [loc]},
            {"name": "STATE", "values": ["Wien"]},
            {"name": "POSTCODE", "values": ["1230"]},
            {"name": "ISPRIVATE", "values": [private]},
            {"name": "PUBLISHED_String", "values": ["2026-10-20T10:00:00Z"]},
            {"name": "SEO_URL", "values": [seo or ("kaufen-und-verkaufen/d/ad-%d/" % ad_id)]},
            {"name": "BODY_DYN", "values": [body]},
            {"name": "categorytreeids", "values": cats.split(";") if cats else []},
        ]},
    }


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
        "sellerProfileUserData": {"private": True, "name": "Anna", "registerDate": "2021-05-01", "activeAdCount": 3},
        "advertAddressDetails": {"postCode": "1230", "postalName": "Wien"},
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


class WhTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "wh.db")
        self.orig_db = wh.DB
        self.orig_delay = wh.DELAY
        wh.DB = self.db_path
        wh.DELAY = 0.0

    def tearDown(self):
        wh.DB = self.orig_db
        wh.DELAY = self.orig_delay
        self.tmp.cleanup()

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
        with mock.patch.object(wh, "fetch", return_value=("https://x", "<html>blocked</html>")):
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


if __name__ == "__main__":
    unittest.main()
