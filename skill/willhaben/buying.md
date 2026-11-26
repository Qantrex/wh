# willhaben: buying

Read with [SKILL.md](SKILL.md) (ground rules). `wh deal` and `wh hunt` send these rules to Claude.

## Judging a deal (buying)

Always end with a clear verdict: **good deal / fair / overpriced / walk away**, the reasons, and a suggested offer.

- **The offer:** with a "Price room" section (wh offer), give its plan: the first offer, the steps and the last offer, with odds; say why if you differ.

- **Market position:** compare with similar ads from the same sweep (same model or specs and condition). Say where this price sits ("cheapest of 9 comparable ads nearby, median €680"). Also check the new price across shops, shipping to Austria included.
- **Total cost:** price, shipping and whatever must be added or fixed (charger, RAM, tyres, service).
- **Does the ad match the title?** Model generation, year, size on the label, single-channel RAM, missing parts, "Bastler"/defect hints in the text.
- **RAM sticks: read the label in the photos.** "DDR4 16GB" ads rarely say laptop or server (2026-11-06: 6 of 8 cheap "desktop" picks were not). Desktop UDIMM: `M378…`, `HMA…U6…`, `MTA…AZ`, `KVR…N…`, `PC4-…-U`. Laptop SO-DIMM: `M471…`, `HMA…S6…`, `MTA…HZ`, `-S…`. Server RDIMM (no desktop board): `M393…`, `HMA…R7/R4…`, `MTA…PZ`, `PC4-…P-R`, HPE/Dell sticker, register chip, mostly `2Rx4`.
- **Scam and risk flags:** a price far below comparable ads, shipping only with payment outside PayLivery, a brand-new account, stock photos, a vague description, pressure to decide fast. Call out a too-good price plainly.
- **Questions for the seller** before buying: battery health, label photos, receipt or warranty, a test on site.
- Private sellers and a near pickup are a plus; dealer warranty can be worth more.
- **Only hardware counts** (laptops, PCs): no points for software (the OS, a Windows licence or "aktiviert", Office, a fresh install).
- **fps figures:** never count frame generation (DLSS 3/4 FG, FSR FG, AFMF); state resolution and preset. Notebookcheck's GPU pages ("…-Benchmarks-and-Specs") have per-game averages in `"avg_value"` JSON.

## Market values (wh find, value, watch)

- The value is the median asking price of the same item over 90 days, one vote per seller (a looser match with too few sellers). Low **confidence** is a hint, not a fact. Asking prices are above selling prices, so 10–15 % below value is only fair.
- Check that the comparables (`comps`, `wh value <ad>`) are the same item: generation, storage, size, bundle.
- **Far below value** (over 55 %): a part, a defect the title doesn't say, the wrong model, a scam, or a real bargain. Never drop it for being cheap: read the ad and the photos.
- **Urgent sales** ("Notverkauf", "muss weg", Umzug): the best chances. Act fast, but check the scam signs above first.

## Great finds

- While sweeping, note anything clearly below its new price that fits the user's interests under the buy note's "Great finds", with the new price; near-misses go under "Checked, not finds".

## willhaben quirks (buying)

- willhaben's size filter only offers "ab XL", so an ad saying XL can be XXL. Check the label photo.
