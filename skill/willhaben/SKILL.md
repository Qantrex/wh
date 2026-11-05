---
name: willhaben
description: Anything on willhaben.at, plus used-market searches on Kleinanzeigen.de. Searching or sweeping listings, judging whether an ad is a good deal or a scam, comparing used vs new prices, writing, pricing or updating your own ads, wanted ads (Suche), reading or drafting seller chats, relisting. Use it whenever a task mentions willhaben, a willhaben link or ad number, or buying/selling something used in Austria.
---

# willhaben

Setup: the Install section of the `wh` README (github.com/Qantrex/wh); `wh doctor` checks it. Notes folder, the database and note properties: [data.md](data.md).

## wh: use it instead of writing scripts

| Command | What it does |
|---|---|
| `wh search <words> [--url <search URL or category slug>] [--min N] [--max N] [--pages N] [--profile NAME] [--area wien,noe] [--md\|--json]` | lists ads, without junk (defects, wanted ads, parts) unless `--all` |
| `wh facets <words> [--url …] [--min N] [--max N]` | willhaben's own breakdown of a search: subcategories with ready URLs, condition, region, brand … with counts. Use it to write a note's `search:` lines |
| `wh profiles` | the built-in profiles and templates a note's `wh-profile` can name, plus broken templates with the reason |
| `wh doctor` | checks the config, notes (missing `for:`, unknown profiles or areas, bad `ad:`), the skill install, templates, the database and tools; run it first when something looks wrong |
| `wh ad <id or link>` | the full ad: description, seller (member since, active ads), price cut, price history |
| `wh history <id or link> [--json]` | the prices wh has seen for an ad over time, from the database only (no request) |
| `wh photos <id> <dir>` | downloads the photos, converting WebP to JPEG |
| `wh status [notes]` | is each open note's `ad:` still online, at what price? |
| `wh sweep [notes] [--json] [--no-write]` | runs the `search:` URLs of open buy/wanted notes and writes new ads, price cuts, gone ads and a shortlist into the note's `<!-- wh:sweep -->` block; `--json` prints the same for scripts, `--no-write` leaves the notes alone |
| `wh deal <id or link> [--compare "words"] [--question "…"]` | **AI:** verdict, comparable ads, a suggested offer, questions for the seller |
| `wh advise [notes]` | **AI:** should your live ads (sell notes) get a lower price? |
| `wh hunt <note>` | **AI:** sweep, then Claude writes the best picks into the note's `<!-- wh:picks -->` block |

- **Inside a Claude session,** run the AI commands with `--no-ai`. That prints the gathered data and the task, and you do the judging yourself with the rules below. Without `--no-ai`, wh calls `claude -p` (no tools, about 1 minute); that is for a terminal.
- **Profiles** turn ads into comparable specs, filter junk and rank the sweep's shortlist. A buy note picks one with `wh-profile: <name>`; `wh profiles` lists them.
  - New kind of search: add a template, not a script ([data.md](data.md)).

## Read before the task

- [buying.md](buying.md) before judging a deal or writing picks (verdicts, great finds, fps/hardware rules).
- [selling.md](selling.md) before writing, pricing or relisting an ad.
- [data.md](data.md) before fetching by hand, chats behind the login, Kleinanzeigen, new prices, or setting up a search or template.

## Ground rules

- **Who it's for comes first.** Every buy/wanted note says it in `for:` (`me`, `homelab`, or a name such as `<name> (friend)`). Read it before judging anything; if it is missing or vague, ask the user one question instead of guessing. Judge only by that person's or purpose's stated needs, never link or compare notes with a different `for:`, and name the person in answers instead of saying "your pick". Use `wh deal <ad> --for <who>` for single ads.
- **Never send a message, make an offer, buy, publish or change an ad without the user's OK.** Draft it, show it, wait. Opening and reading seller chats is fine.
- **Sending needs Claude in Chrome.** `wh` only reads public pages; messages go through the user's logged-in willhaben chat in Chrome. Before offering to send, check that the extension is connected. If it is not, give the drafts as copy-ready text instead.
- Write messages in German, in the user's own tone, with their name. Lowball first offers are fine.
- An ad that shows "Anzeige nicht mehr verfügbar" has usually just **expired** (the seller forgot to renew it). It does not mean sold. Don't treat it as sold and never mention it to the seller.
- Listing tables in notes only contain ads you would actually consider. Mention rejects in chat if they matter.
- Check specs and prices online instead of writing from memory, and cite sources in the note.
