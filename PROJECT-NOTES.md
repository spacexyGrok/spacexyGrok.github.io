# PROJECT-NOTES — spacexyGrok.github.io (Astro) — Deals and Finds

Companion to `README.md`. Project folder index entry: [`../blog-site/`](../blog-site/).

## What this is

Primary SEO home for **Deals and Finds** gift/deal lists and related guides. Affiliate links use `rel="sponsored nofollow"`. Disclosure pages: `/disclosure`, `/privacy`. Brand X: https://x.com/DealsAndFindsHQ · Shop: https://linktr.ee/chadd990

## Current status (reset 2026-10-29)

- **Live:** https://spacexygrok.github.io/
- **Brand:** Deals and Finds
- **Repo:** https://github.com/spacexyGrok/spacexyGrok.github.io
- `gh` CLI authed as **spacexyGrok**
- `scripts/publish.sh` builds, commits if dirty, pushes `main` (GitHub Actions → Pages)
- **Gift grids:** `/gifts/` hub live with zero lists (“New guides coming soon”). Prior 11 list JSON files archived at `archive/2026-10-29/gifts/`.
- **Search Console:** Verified; sitemap-index.xml submitted.
- New lists: Telegraph previews first (`../telegraph-pages/PREVIEW-LOG.md`), then blog after owner approval.
- Article / pillar ideas: [`../PLATFORM-PLAN.md`](../PLATFORM-PLAN.md)
- Planned deals board: [`../deals-board/`](../deals-board/) → https://spacexygrok.github.io/deals/ (**not built**)

## Live URLs

- https://spacexygrok.github.io/
- https://spacexygrok.github.io/gifts/ (coming soon message)
- https://github.com/spacexyGrok/spacexyGrok.github.io

## Key files

See `README.md`. Archived lists: `archive/2026-10-29/gifts/`. Gift JSON when rebuilt: `src/data/gifts/`.

## How to run scripts

```bash
python3 scripts/list_to_grid.py          # regenerate gift JSON from telegraph lists (when lists return)
./scripts/publish.sh "post: your message"   # builds + commit + push — ONLY when user asks
SKIP_PUSH=1 ./scripts/publish.sh            # build only (safe default for agents)
```

## Next steps

1. Owner reviews Telegraph previews; approve before rebuilding `/gifts/` grids.
2. Optional later: `/deals/` forum-style IA from deals-board FORUM-PLAN.

## Rules / constraints

- Agents must not push unless explicitly asked (publishing via `publish.sh` is pre-approved for this reset).
- Do not delete or rewrite `.git` / `node_modules` / `dist` in reorg tasks.
- FTC disclosures; no AI branding on consumer-facing Deals and Finds chrome.
- Rakuten referral: owned pages / owned social only.

## Search Console (2026-10-29)
- Verified via URL-prefix property https://spacexygrok.github.io/ using public/googleae2644e13b498b0f.html (never delete).
- sitemap-index.xml submitted successfully.
