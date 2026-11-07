# willhaben: buying

Read with [SKILL.md](SKILL.md) (ground rules). `wh deal` and `wh hunt` send these rules to Claude.

## Judging a deal (buying)

Always end with a clear verdict: **good deal / fair / overpriced / walk away**, the reasons, and a suggested offer.

- **Market position:** compare with similar ads from the same sweep (same model or specs, similar condition). Say where this price sits ("cheapest of 9 comparable ads nearby, median €680"). Also check the new price across shops, shipping to Austria included.
- **Total cost:** price + shipping + whatever would have to be added or fixed (charger, RAM upgrade, tyres, service).
- **Does the ad match the title?** Model generation, year, size on the label, single-channel RAM, missing parts, "Bastler"/defect hints in the text.
- **Scam and risk flags:** a price far below comparable ads, shipping only with payment outside PayLivery, a brand-new account, stock photos, a vague description, pressure to decide fast. A price that is too good to be true gets called out plainly.
- **Questions for the seller** before buying: battery health, label photos, receipt or warranty, a test on site.
- Private sellers and pickup nearby are a plus. Dealer warranty can be worth a higher price.
- **Only hardware counts** (laptops, PCs, anything with an OS): give no points to software: not the OS, not a Windows licence or "aktiviert", Office, preinstalled apps or a fresh install.
- **fps figures:** never include frame generation (DLSS 3/4 FG, FSR FG, AFMF). Only rendered frames, and always state resolution and quality preset. Notebookcheck's GPU pages ("…-Benchmarks-and-Specs") have per-game averages in `"avg_value"` JSON.

## Market values (wh find, value, watch)

- The value is the median asking price of the same item (same key: model and variant first, looser if too few sellers) over the last 90 days, one vote per seller. **Confidence** says how many sellers and how close their prices are; a low-confidence value is a hint, not a fact. Asking prices are above selling prices, so a deal 10–15 % below value is only fair.
- Check that the comparables (`comps`, `wh value <ad>`) really are the same item: generation, storage, size, bundle.
- **Far below value** (over 55 %): a part, a defect the title doesn't say, the wrong model, a scam, or a real bargain. Never drop it for being cheap: read the ad and the photos.
- **Urgent sales** ("Notverkauf", "muss weg", Umzug): the best chances. Act fast and offer a fair price, but check the scam signs above first.

## Great finds

- **Great finds:** while sweeping, also note anything clearly below its new price that fits the user's interests, in a "Great finds" section of the matching buy note with the new price next to it. List near-misses (only a few % below new) under "Checked, not finds" so they do not get re-checked.

## willhaben quirks (buying)

- willhaben's size filter only offers "ab XL", so an ad saying XL can be XXL. Check the label photo.
