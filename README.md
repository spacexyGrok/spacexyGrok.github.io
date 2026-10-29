# Content affiliate static site (Astro)

Primary SEO home for free AI tool lists and gift/deal guides. Affiliate links use `rel="sponsored nofollow"`.

**Live:** https://spacexygrok.github.io/  
**Repo:** https://github.com/spacexyGrok/spacexyGrok.github.io

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
- Disclosure / privacy: `src/pages/disclosure.astro`, `privacy.astro`
- After adding affiliate URLs, wrap them in HTML: `<a href="..." rel="sponsored nofollow">...</a>`
