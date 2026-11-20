# Plan: price database improvements (2026-11-20)

From a check of the price database on 2026-11-20. Six items, built in this order. Every extractor change gets a test
with real-looking titles and a coverage check on two real databases before and after (a copy of a database filled by a
nightly crawl of eleven kinds and a copy of one with every category). Measured with a script outside the repo:
per kind the share of priced, non-junk ads with no key, with the most specific key, and with a high or medium
confidence value, plus fixed sample queries.

## Baseline (nightly copy, 204k ads; the kinds it doesn't crawl from the full copy)

| Kind | No key | Most specific key | High/medium value |
|---|---|---|---|
| console | 24 % | 76 % | 75 % |
| laptop | 65 % | 26 % | 32 % |
| tv | 71 % | 10 % | 22 % |
| headphones | 66 % | 35 % | 19 % |
| cpu | 50 % | 50 % | 21 % |
| mainboard (full copy) | 67 % | 11 % | 13 % |
| turntable (full copy) | 66 % | 34 % | 1 % |
| hifi (full copy) | 69 % | 31 % | 0.1 % |

Sample values: `ps5` €550 (639 sellers, mixes limited editions, jailbreak firmware, bundles with a monitor and games
titled "… PS5"); `thinkpad t480`, `technics sl-1200`, `ryzen 5 5600x` (full copy), `bose qc35`, `dell u2723qe`:
no value.

## Steps

1. **Coarse keys.**
   - Console: games and parts titled "<game> PS5", "PS5 Laser", "OVP ohne Konsole" are not consoles; `head()` no
     longer cuts "Playstation 5 Controller" to "playstation"; an `edition` for limited/special editions and for
     jailbreak or old-firmware consoles, so they get their own key; bundles with a monitor, VR or portal are extras.
   - Laptop: model names without the series word ("Lenovo T430" is a ThinkPad), Intel MacBooks by size and year, a
     CPU from the model number when the profile's CPU table has no bucket, and a model-only key, so a query like
     "thinkpad t480" gets a value.
   - TV: more model codes (Sony Bravia series letters, Samsung display codes).
   - Headphones (all audio kinds): one spelling per model ("WH-1000XM4" = "wh1000xm4", "QuietComfort 35 II" =
     "qc35ii"), known models without a number (Beats Studio Pro, Galaxy Buds, Shokz OpenRun …), and a series key
     ("technics sl1200" for every SL-1200 variant) behind the exact model.
2. **More kinds in a nightly crawl** (turntable, hifi, server, pc, mainboard, psu). In wh: the full crawl stores each
   group of categories as it goes, so memory stays flat when the crawl grows by a third.
3. **History.** Instead of one row per ad per day (about 120k rows a night for a 200k-ad crawl), each price row keeps the
   last time it was seen (`prices.last_seen`): the same information as a daily point, without the growth. `wh
   history` and the JSON output show "€X from … to …".
4. **CPU and mainboard extraction.** Xeon E3/E5/X/W, Pentium/Celeron, first-gen Core i, Ryzen numbers without the
   tier, Opteron/Threadripper/EPYC; industrial "CPU" modules (SPS, Simatic) and CPU+board bundles are not CPUs.
   Mainboard chipsets from board names (M5A97 → 970), laptop and Mac logic boards are not desktop boards.
5. **`wh value` finds the kind itself** for brand and model queries: when the query words name no kind, wh looks for
   ads in the database whose titles contain the query's model and takes the kind with the most of them.
6. **Crawl time.** The crawl summary line says when willhaben pushed back (the likely reason a nightly crawl went
   from 315 s to 712 s while its CPU time stayed at 113 s).

## Not in scope

Sold-price inference from the history (needs weeks of data first); market values for the kinds outside the categories
above.
