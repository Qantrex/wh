# willhaben: data, searches and the login

Read with [SKILL.md](SKILL.md). Not sent to Claude by the AI commands.

## Notes, profiles and templates

Notes live in a folder you choose (`notes` in `~/.config/wh/config.toml`, `WH_NOTES` overrides), for example `Selling/<Item>/<Item>.md` for ads you sell and `Buying/<Item>.md` for things you want to buy. See the README of `wh` for the note properties.

`wh` reads willhaben's public pages (4 requests at a time, at most 4 per second; a full sweep takes about 12 s) and stores every ad it sees in `~/.local/share/wh/wh.db`. That is where the price history and "new since last time" come from.

- **Profiles** turn ads into comparable specs, filter junk and rank the sweep's shortlist. A buy note picks one with `wh-profile: <name>`; `wh profiles` lists them.
  - **Templates** (`~/.config/wh/templates/<name>.toml`, data, no code): junk/require rules, columns with scores and new prices, shortlist sort. **For a new kind of search, add a template** instead of a one-off script: copy the repo's `templates/example.toml` there (its header documents every key), test it on real ads with `wh search --url '<URL>' --profile <name> --all --json` and `wh sweep <note> --dry-run`, check `wh profiles` for errors, then set `wh-profile`. Keep the new prices current (with the date in a comment).
  - **Built-in** (`profiles.py`: `laptop`, `pc`, `server`, `hue`): only for items that need real parsing (RAM/GPU tiers, pack sizes).
- A buy note needs `status: open` and `search:` (one willhaben search URL per line, e.g. a category URL with `keyword=` and `PRICE_FROM`/`PRICE_TO`). A sell note needs `ad:`.
- `wh-area: wien, noe` on a buy note only marks ads in your pickup area; it never filters, because a good deal further away can be shipped.
- **Check the category** with `wh facets` before saving a search: the number at the end of the URL is what counts, not the slug. `laptops-notebooks-5824` is all of Computer / Software (half the "laptop" hits were PCs and GPUs); notebooks are `computer-tablets/notebooks-5831`, PCs `computer-tablets/pcs-5833`. `wh sweep` warns when most of a search's ads fall outside the profile's category.
- `--dry-run` (sweep, hunt) leaves no trace in the database, so it does not spoil the next real sweep's "new" and "gone".

## Getting the data (no browser needed)

This is what `wh` does under the hood. Plain HTTP works (the site is behind Cloudflare, but plain requests get no challenge). Send a browser User-Agent and `Accept-Language: de-AT`. Keep it to a few workers with a rate cap, and drop to one at a time on a 403, a 429 or a Cloudflare challenge page.

- **Search pages** embed the results as JSON in `<script id="__NEXT_DATA__">` → `props.pageProps.searchResult`: `rowsFound`, `advertSummaryList.advertSummary[]`. Per ad: `id`, `description`, and `attributes.attribute[]` (`name`, `values`) with `HEADING`, `PRICE`, `LOCATION`, `STATE`, `POSTCODE`, `BODY_DYN` (description snippet), `ISPRIVATE` (`1` = private), `PUBLISHED_String`, `SEO_URL` (prefix `https://www.willhaben.at/iad/`), `categorytreeids`.
  - Keyword: `https://www.willhaben.at/iad/kaufen-und-verkaufen/marktplatz?keyword=<words>&rows=200&page=N`
  - **Category (better for broad hunts):** complete, and no fan-out over dozens of keywords. Example: `…/marktplatz/computer-tablets/notebooks-5831?PRICE_FROM=80&PRICE_TO=1150&rows=200&page=N`. The id at the end picks the category, the slug before it is ignored. Pages go deep; `rows` tops out at 200.
  - The newest ads come first (`sort=1`, the default). `keyword=a OR b` works and returns both.
  - Price filter: `PRICE_FROM`, `PRICE_TO`.
  - **Attribute filters** (size, gender, …): `treeAttributes=<id>`, ids in `searchResult.navigatorGroups[].navigatorList[].groupedPossibleValues[].possibleValues[]` (`label`, `urlParamRepresentationForValue[0].value`, `hits`). One value per group per URL; filters from different groups combine as AND. `wh search --url` and a buy note's `search:` take these URLs.
- **Ad pages** `https://www.willhaben.at/iad/object?adId=<id>` → `props.pageProps.advertDetails`: `attributes` (`DESCRIPTION` is HTML), `attributeInformation`, `teaserAttributes`, `firstPublishedDate`, `advertStatus.id` (`active`, …) and image URLs. Look at the photos for part numbers, model years and label sizes; ads often get these wrong.
- Fetch ad pages only for a shortlist (filter the search JSON first), not for every hit.
- **Kleinanzeigen.de** works with curl too: `https://www.kleinanzeigen.de/s-<words-with-dashes>/k0`. Private sellers may not ship to Austria; ask them.
- **New prices** for comparison: search Google by part number (`google.com/search?q=<partno>&gl=at`, Shopping with `&udm=28`), then open the shop page to check the part number and the shipping cost to Austria. Compare several shops. Don't get past bot checks; use Google's listing and say "confirm at checkout".

## Behind the user's login (Claude in Chrome)

- The user's own ads: https://www.willhaben.at/iad/myprofile/myadverts
- Chat overview without opening each chat: on https://www.willhaben.at/iad/myprofile/chat, run `GET /webapi/chat-api/v1/conversations?limit=10&offset=0` in the page. It returns `participant_info.name`, `unseen` and `last_message.{is_mine, read, preview, timestamp}`. Full text: `GET /webapi/chat-api/v1/conversations/<id>/messages?limit=5` → `messages[].{text, is_mine, read, created_at}`. This does not mark messages as read. Timestamps are UTC.
- Views, watchers and offers on own ads are only visible here. Write them into the note with the date (`checked`).
