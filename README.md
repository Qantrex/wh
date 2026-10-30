# wh

willhaben.at from the terminal. It reads the public pages fast, one request at a time, and keeps every ad it sees in a local SQLite database. Claude does the judging on top of that.

```
wh search dji fpv goggles v2            # list ads (junk filtered), --md for a note, --json for scripts
wh search --url laptops-notebooks-5824 --max 800 --profile laptop
wh ad 1041160074                        # one ad in full, with seller info and price history
wh photos 1041160074 ./photos           # photos as JPEG (WebP gets converted with magick)
wh status                               # online? price? for every open Marketplace note with an `ad:`
wh sweep                                # run the `search:` of every open buy/wanted note, write the results in

wh deal <link>                          # AI: worth buying? verdict, comparables, offer, questions
wh advise                               # AI: should my live ads get a lower price?
wh hunt Laptop                          # AI: sweep a buy note, Claude writes the best picks into it
```

The AI commands gather the data and ask `claude -p` (no tools, so it only reasons over what wh gives it) with the rules from the `willhaben` skill (`~/.claude/skills/willhaben/SKILL.md`). `--no-ai` prints the data and the task instead, which is what Claude itself uses inside a session.

## Files

- `wh`: the command (Python 3, standard library only). Linked as `~/.local/bin/wh`.
- `profiles.py`: per-category knowledge that turns ads into comparable specs and filters junk (`laptop`, `pc`, `server`, `hue`). A buy note picks one with `wh-profile: laptop`.
- `test_wh.py`: unit tests (`python3 -m unittest`).
- `seed/`: the scripts and CSVs from the first laptop hunt (2026-10-25), which the laptop profile came from.

## Notes it works with

Notes in `~/Notes/Marketplace` (`WH_NOTES` overrides), with YAML properties:

- sell notes: `type: sell`, `status: live`, `ad: <willhaben-Code>`
- buy/wanted notes: `type: buy` or `wanted`, `status: open`, `search:` (one willhaben search URL per line), optional `wh-profile`

`wh` only writes `checked`, `updated` and its own blocks between `<!-- wh:sweep -->` / `<!-- wh:picks -->` markers.

## Settings

| Env | Default |
|---|---|
| `WH_DB` | `~/.local/share/wh/wh.db` |
| `WH_NOTES` | `~/Notes/Marketplace` |
| `WH_DELAY` | `1.1` seconds between requests |
| `WH_MODEL` | Claude Code's default model |

There's no timer: wh runs when I run it.
