# Content affiliate static site (Astro)

Primary SEO home for **Deals and Finds** gift/deal lists (older AI tools post URL kept). Affiliate links use `rel="sponsored nofollow"`.

**Live:** https://spacexygrok.github.io/  
**Repo:** https://github.com/spacexyGrok/spacexyGrok.github.io

## Status (reset 2026-10-29)

All gift/deal list pages under `/gifts/` were removed. Gift JSON is archived at `archive/2026-10-29/gifts/`. The `/gifts/` hub shows “New guides coming soon.” New lists ship only after Telegraph preview approval (see `../telegraph-pages/PREVIEW-LOG.md`).

## Local

```bash
npm install
npm run dev
SITE_URL=https://spacexygrok.github.io npm run build
```

## Publish (one command)

```bash
./scripts/publish.sh "post: your message"
```

Builds with `SITE_URL=https://spacexygrok.github.io`, commits if dirty, pushes `main`. GitHub Actions deploys Pages.

`SKIP_PUSH=1 ./scripts/publish.sh` builds only.

## Content

- Posts: `src/content/posts/*.md`
- Gift grids: `src/pages/gifts/` (data from `src/data/gifts/`; regenerate with `python3 scripts/list_to_grid.py` when lists return)
- Disclosure / privacy: `src/pages/disclosure.astro`, `privacy.astro`
- After adding affiliate URLs, wrap them in HTML: `<a href="..." rel="sponsored nofollow">...</a>`

## Project notes

See [`PROJECT-NOTES.md`](PROJECT-NOTES.md) and the index folder [`../blog-site/`](../blog-site/) for status, Search Console, and publish rules. Strategy/article ideas: [`../PLATFORM-PLAN.md`](../PLATFORM-PLAN.md).
