# PROJECT-NOTES — spacexyGrok.github.io (Astro) — Deals and Finds

Companion to `README.md`. Project folder index entry: [`../blog-site/`](../blog-site/).

## What this is

Primary SEO home for **Deals and Finds** gift/deal lists and related guides. Affiliate links use `rel="sponsored nofollow"`. Disclosure pages: `/disclosure`, `/privacy`. Brand X: https://x.com/DealsAndFindsHQ · Shop: https://linktr.ee/chadd990

## Current status

- **Live:** https://spacexygrok.github.io/
- **Brand:** Deals and Finds (rebranded from “Free AI & Gift Guides” chrome; older `/posts/free-ai-tools-2026/` URL kept)
- **Repo:** https://github.com/spacexyGrok/spacexyGrok.github.io
- `gh` CLI authed as **spacexyGrok**
- `scripts/publish.sh` builds, commits if dirty, pushes `main` (GitHub Actions → Pages)
- **Gift grids:** `/gifts/` — 11 lists generated from `../telegraph-pages/lists/` via `scripts/list_to_grid.py`
- **Search Console verification pending** — needs the user’s HTML tag / property add
- Article / pillar ideas: [`../PLATFORM-PLAN.md`](../PLATFORM-PLAN.md)
- Comparison: [`../deals-board/GRID-VS-TELEGRAPH.md`](../deals-board/GRID-VS-TELEGRAPH.md)
- Planned deals board (forum-style): [`../deals-board/`](../deals-board/) → https://spacexygrok.github.io/deals/ (**not built**)

## Live URLs

- https://spacexygrok.github.io/
- https://spacexygrok.github.io/gifts/
- https://github.com/spacexyGrok/spacexyGrok.github.io

## Key files

See `README.md`. Seed lists: [`../telegraph-pages/lists/`](../telegraph-pages/lists/). Gift JSON: `src/data/gifts/`.

## How to run scripts

```bash
python3 scripts/list_to_grid.py          # regenerate gift JSON from telegraph lists
./scripts/publish.sh "post: your message"   # builds + commit + push — ONLY when user asks
SKIP_PUSH=1 ./scripts/publish.sh            # build only (safe default for agents)
```

## Next steps

1. User: Google Search Console URL-prefix property for `https://spacexygrok.github.io/` + HTML verification; submit sitemap.
2. Add product images to the 10 lists that are still text-only in source MD.
3. Optional: Telegraph teasers linking to blog canonicals (no full duplicates; no Rakuten on Telegraph).
4. Optional later: `/deals/` forum-style IA from deals-board FORUM-PLAN.

## Rules / constraints

- Agents must not push unless explicitly asked.
- Do not delete or rewrite `.git` / `node_modules` / `dist` in reorg tasks.
- FTC disclosures; no AI branding on consumer-facing Deals and Finds chrome.
- Rakuten referral: owned pages / owned social only.

## Search Console (2026-10-29)
- Verified via URL-prefix property https://spacexygrok.github.io/ using public/googleae2644e13b498b0f.html (never delete).
- sitemap-index.xml submitted successfully.
