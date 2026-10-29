# Content affiliate static site (Astro)

Primary SEO home for free AI tool lists and gift/deal guides. Affiliate links use `rel="sponsored nofollow"`.

## Local

```bash
npm install
npm run dev
SITE_URL=https://YOURUSER.github.io npm run build
# or
./scripts/publish.sh
```

## Deploy (user)

Do **not** expect this folder to auto-deploy. Recommended free hosts:

1. **GitHub Pages** (vault already has a GitHub account) — `USERNAME.github.io` or project pages.
2. **Cloudflare Pages** — connect the same repo; free custom domain later.
3. **Netlify** — same pattern; watch free bandwidth credits.

Set `SITE_URL` to the live origin before production builds so canonical tags and `robots.txt` sitemap match.

## Content

- Posts: `src/content/posts/*.md`
- Disclosure / privacy: `src/pages/disclosure.astro`, `privacy.astro`
- After adding affiliate URLs, wrap them in HTML: `<a href="..." rel="sponsored nofollow">...</a>`
