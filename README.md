# wh

willhaben.at from the terminal. It reads the public pages, 4 requests at a time (at most 4 per second), and keeps every ad it sees in a local SQLite database. Claude does the judging on top of that.

```
wh search dji fpv goggles v2            # list ads (junk filtered), --md for a note, --json for scripts
wh search --url computer-tablets/notebooks-5831 --max 800 --profile laptop --area wien,noe
wh facets rtx --url computer-tablets-5828   # willhaben's subcategories and filters for a search, with counts
wh ad 1041160074                        # one ad in full, with seller info and price history
wh history 1041160074                   # its prices over time as wh saw them (database only, no request; --json)
wh photos 1041160074 ./photos           # photos as JPEG (WebP gets converted with magick)
wh status                               # online? price? for every open Marketplace note with an `ad:`
wh sweep                                # run the `search:` of every open buy/wanted note, write the results in
wh sweep --json --no-write              # the same as JSON for a script or a timer, notes left alone
wh profiles                             # built-in profiles and templates a note's `wh-profile` can name
wh doctor                               # check config, notes, skill install, templates, database and tools

wh find 2x16gb ddr4 3200 --area wien,noe   # the best deals: ads below their market value, best first
wh find tv 45-55 zoll                   # works for whole kinds too (sizes for tv/monitor)
wh value "LG OLED55C1"                  # what an item (or an ad link) is worth used, and the ads behind it
wh crawl --list                         # the categories behind the market values, and when they were last read
wh watch add gpu --kind gpu --below 0.35   # a saved find; `wh watch run --json` reports new deals once (for a timer)

wh deal <link> --for "a friend"         # AI: worth buying (for whom)? verdict, comparables, offer, questions
wh advise                               # AI: should my live ads get a lower price? (one Claude call per ad, in parallel)
wh hunt Laptop                          # AI: sweep a buy note, Claude writes the best picks into it
```

The AI commands gather the data and ask `claude -p` (no tools, so it only reasons over what wh gives it) with the rules from the `willhaben` skill (`skill/willhaben/` in this repo, installed as `~/.claude/skills/willhaben`): the ground rules from `SKILL.md` plus `buying.md` for `deal` and `hunt`, or `selling.md` for `advise`. An old single-file `SKILL.md` still works (wh takes the matching sections from it), and without an installed skill wh uses the copy in this repo. `--no-ai` prints the data and the task instead, which is what Claude itself uses inside a session.

## Market values

`find`, `value` and `watch` know 18 kinds of items: ram, gpu, cpu, mainboard, psu, disk, monitor, tv, laptop, pc, server, phone, tablet, console, headphones, speakers, hifi and turntable (`market.py`). Each kind reads its willhaben categories whole (`wh crawl`: about 180k ads in 4 minutes at the rate limit, then only the new ads; `find` and `value` crawl what they need by themselves, a full crawl at most once every 20 hours) and turns every ad into specs and *keys*: `ddr4 · dimm · 2x16 · 3200`, then `ddr4 · dimm · 2x16`, then `ddr4 · dimm · 32 GB`.

- **Market value** = the weighted median asking price of ads with the same key over the last 90 days, at the most specific key with enough sellers. One vote per seller (dealers repost), outliers (below a third or above three times the median) dropped, ads that sat unsold for weeks or are gone count a bit less, dealers' new stock and defects not at all. The confidence (high/medium/low) comes from the number of sellers and how far apart their prices are.
- **A deal** is an ad below that value. `find` shows the best first and checks the top ads in full (still online? does the description match? seller's account age, photos). Ads more than 55 % below value are listed separately unless the seller gives a reason ("Notverkauf", "muss weg", Umzug …): they're as often parts, defects or scams as they're bargains, so read them, but they're never hidden.
- Ads without a clear key (no model, size or capacity in the text) get no value instead of a wrong one. Accessories and parts in the categories (controllers, cases, TV power boards …) are recognised and left out.
- **Watches** (`~/.config/wh/watches.toml`, edited with `wh watch add/rm`): `wh watch run` reports matching ads that are new or cheaper since the watch's last run and at least `below` (default 25 %) under value, each once. The ads of a category's first full crawl are the starting stock, not news. `--json` is made for a timer or an agent.
- Asking prices aren't selling prices, and the value is only as good as the key: check the comparables (`wh value <ad link>` lists them).

## Install

Needs Python 3.11+ (standard library only) and, for the AI commands, Claude Code. Both links point into the clone, so a `git pull` updates the tool and the skill at once.

```bash
git clone https://github.com/Qantrex/wh ~/Projects/wh && cd ~/Projects/wh
mkdir -p ~/.local/bin ~/.claude/skills ~/.config/wh/templates
ln -sf "$PWD/wh" ~/.local/bin/wh                      # ~/.local/bin must be on your PATH
[ -d ~/.claude/skills/willhaben ] && [ ! -L ~/.claude/skills/willhaben ] &&
  mv ~/.claude/skills/willhaben ~/.claude/skills/willhaben.old   # an old copied skill: keep it aside
ln -sfn "$PWD/skill/willhaben" ~/.claude/skills/willhaben
[ -f ~/.config/wh/config.toml ] || printf 'notes = "~/path/to/marketplace-notes"\n' > ~/.config/wh/config.toml
wh doctor                                             # checks all of the above, sends no request
python3 test_wh.py                                    # offline tests
```

The database (`~/.local/share/wh/wh.db`) starts empty and builds up the price history as you search.

## Speed

A full `wh sweep` of the five buy notes (28 searches, 41 pages) takes about 12 s; one request every 1.1 s took 46 s. The time is almost all network: parsing a 200-ad page takes ~14 ms, the profiles ~0.25 ms per ad, storing 1000 ads ~6 ms (one transaction per run). Preparing a 28-note sweep on a database with 800k price rows takes under a second. `sweep` puts the searches of every note into one queue, page 1 of each search first (it says how many pages there are), then the rest.

If willhaben pushes back (HTTP 403/429/503 or a Cloudflare challenge page), every worker drops to one request per `WH_DELAY` for the rest of the run. A request that keeps failing marks its search incomplete in the note instead of stopping the run.

## Files

- `wh`: the command (Python 3.11+, standard library only). Linked as `~/.local/bin/wh`.
- `market.py`: the kinds of items (categories, spec extractors, keys) and the market value maths, pure Python without network or database.
- `profiles.py`: per-category knowledge that turns ads into comparable specs and filters junk: the built-in profiles (`laptop`, `pc`, `server`, `hue`) and the template engine. A buy note picks one with `wh-profile: laptop`.
- `templates/example.toml`: a sample template. Your own live in `~/.config/wh/templates/` (see [Templates](#templates)).
- `skill/willhaben/`: the Claude skill. `SKILL.md` (commands + ground rules) plus `buying.md`, `selling.md` and `data.md`, read when needed.
- `test_wh.py`: unit tests, no network, from any folder: `python3 test_wh.py`. GitHub Actions runs them on every push.
- `CLAUDE.md`: notes for Claude Code working on this repo.

## Templates

Most searches don't need code: a template says what's junk, which columns to show, what scores higher and what an item costs new. Built-in profiles are only for items that need real parsing (RAM and GPU tiers, pack sizes).

- One TOML file per template in `~/.config/wh/templates/` (plus any directory in `WH_TEMPLATES`, which can override one by name). The file name is the profile name: `espresso.toml` is `wh-profile: espresso`.
- `[[junk]]` rules (title and/or text pattern, optional `unless`), `[[require]]` rules, `[[field]]` columns whose values carry a `score` and optionally a `new` price (adds "new €X (−Y %)"), `[shortlist]` with `min_score` and `sort`, and `category` for the sweep's wrong-category warning. `templates/example.toml` documents every key in its header; copy it to start a new one.
- `wh profiles` lists everything and shows broken templates with the reason; a broken one is skipped and every other command says so, but keeps working. A note naming an unknown profile gets a warning and is swept without one.
- Test a template on real ads with `wh search --url '<search URL>' --profile <name> --all --json` (junk reason, fields and score per ad) or `wh sweep <note> --dry-run`.

## Notes it works with

Notes in the notes folder (`notes` in the config, `WH_NOTES` overrides), with YAML properties:

- sell notes: `type: sell`, `status: live`, `ad: <willhaben-Code>`
- buy/wanted notes: `type: buy` or `wanted`, `status: open`, `for:` (who or what it's for), `search:` (one willhaben search URL per line), optional `wh-profile` (a built-in profile or a template) and `wh-area`
- `for:` (`me`, `homelab`, `<name> (friend)` …) says who a purchase is for. `hunt` puts it at the top of what Claude sees ("judge only by this person's needs"); `sweep` and `hunt` warn when it's missing. `wh deal <ad> --for "a friend"` does the same for a single ad; without `--for`, Claude is told not to assume it's for you.
- `wh-area: wien, noe` marks the ads in those states (a "Near" column, "N in Wien/NÖ" in the sweep line, and a hint for Claude in `hunt`). It never filters anything out: a good deal further away can still be picked up or shipped.

`wh` only writes `checked`, `updated` and its own blocks between `<!-- wh:sweep -->` / `<!-- wh:picks -->` markers. It reads the note again right before each (atomic) write, so what you type while a sweep or Claude runs stays. `hunt` saves the sweep before asking Claude, so a failed Claude call doesn't lose it. Hidden folders (Obsidian's `.trash` and `.obsidian`) are never read.

A sweep's "new", "price cuts" and "gone" compare with earlier runs of the same search URL (changing a URL starts over). "Gone" compares with the last run that read every page. `--dry-run` records no run, so the next real sweep still compares with the last real one.

`wh sweep --json` prints, per note, the market line, the new ads, the price cuts (with `was`), the gone ads, the shortlist and any warnings, for a script or an agent on a timer. Progress goes to stderr, so stdout is only the JSON. `--no-write` records the run (so the next sweep's "new" starts from here) but leaves the notes alone, for a machine that only has a copy of them.

When most ads of a search fall outside the profile's willhaben category (`profiles.CATEGORY`), the sweep says so and suggests the URL inside it. Category ids count, slugs don't: `laptops-notebooks-5824` is all of "Computer / Software", the notebooks are `computer-tablets/notebooks-5831`. `wh facets` shows the subcategories of any search.

## Private data

Nothing personal belongs in this repo, and `.gitignore` blocks the usual suspects. Everything about you stays on your machine:

| What | Where |
|---|---|
| Settings (`notes`, `skill`, `location`) | `~/.config/wh/config.toml` |
| Your templates | `~/.config/wh/templates/` |
| Ads, price history, old exports | `~/.local/share/wh/` |
| Notes | your notes folder |

```toml
# ~/.config/wh/config.toml
notes = "~/path/to/marketplace-notes"
location = "1010 Wien"        # optional: lets Claude weigh pickup distance
```

The AI commands (`deal`, `advise`, `hunt`) are the exception: they send what they gather to Claude, including the note, the `location` and the skill's rules. `--no-ai` prints it instead of sending it.

## Settings

| Env | Default |
|---|---|
| `WH_CONFIG` | `~/.config/wh` |
| `WH_DB` | `~/.local/share/wh/wh.db` |
| `WH_NOTES` | `notes` in the config, else `~/.local/share/wh/notes` |
| `WH_SKILL` | `skill` in the config, else `~/.claude/skills/willhaben/SKILL.md` (a file or its folder; `buying.md`/`selling.md` are read next to it) |
| `WH_TEMPLATES` | extra template directories |
| `WH_WORKERS` | `4` requests at once (`1` for one at a time) |
| `WH_RATE` | `4` requests per second, all workers together |
| `WH_DELAY` | `1.1` seconds between requests once willhaben pushes back |
| `WH_MODEL` | Claude Code's default model |

wh has no timer of its own; `wh sweep --json --no-write` is made for one (a systemd timer, cron, an agent).
