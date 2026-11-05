# willhaben: selling

Read with [SKILL.md](SKILL.md) (ground rules). `wh advise` sends these rules to Claude.

## Selling

Ask the user for their location (postcode), pickup and shipping preferences before drafting an ad; don't assume the profile default.

- **PayLivery:** shipping via Post. Off on wanted ads, or people can "buy" from you.
  - Pick the parcel size for the packed weight (3 / 10 / 31.5 kg). willhaben charges the difference if a parcel is under-franked.
  - For electronics, tick **Erweiterte Haftung** (+€4.90). Standard liability does not cover electronic, fragile or shock-sensitive items.
  - The buyer pays shipping.
- **Paid extras** (Vorreihen, Hervorheben, TOP-Anzeige): none unless the user asks.
- **Price:** a realistic used price, slightly below comparable ads. willhaben has no VB field, so just set the number.
- **Language:** everything in German, aimed at Austrian buyers.
- **Title:** model name plus the key features or included extras, so it shows up in searches.
- **Description:** short intro, then **Zustand** (honest about wear, pointing to the photos), then **Lieferumfang/Ausstattung** as bullet lists, compatibility where relevant, and the pickup/PayLivery line. End with "Privatverkauf – keine Garantie, Gewährleistung oder Rücknahme."
- **Accuracy:** don't invent facts such as condition, reason for selling or accessories. Ask the user if something is unclear.
- **Before publishing:** fill everything in up to the "Veröffentlichen" step, then show a summary and wait for the user's OK.

### Pricing advice for the user's ads

When asked "should I lower the price?", look at days online, views and watchers over time, chats and offers received, and the comparable ads online right now. Give a concrete number and the reason, e.g. "8 comparable ads at €80–95; yours is €100 with 156 views, 11 watchers and no offer in 3 weeks → €89". Watchers without offers usually mean the price is a bit high. Few views mean the title or category is the problem. Price cuts are the user's decision: draft the change, don't make it.

## willhaben quirks (selling)

- An ad marked sold through PayLivery **cannot be reactivated**. Its only options are "Rechnung anfordern" and "Löschen". To relist, create a new ad. The old photos can be downloaded from `https://cache.willhaben.at/...`; they come as WebP, so convert them to JPEG with `magick`.
- New ads are reviewed before going live, which can take up to 24 hours.
- On the ad form, typing into price or title while photos are still uploading gets wiped. Wait for the upload to finish, then check the fields.
- The description editor is Quill. Pasting HTML works well for bullet lists.
