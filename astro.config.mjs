// @ts-check
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

// Live GitHub Pages user site (root). Override with SITE_URL for previews.
const SITE = process.env.SITE_URL || 'https://spacexygrok.github.io';

// https://astro.build/config
export default defineConfig({
  site: SITE,
  // No `base` — user site deploys at https://spacexygrok.github.io/
  integrations: [sitemap()],
  markdown: {
    shikiConfig: { theme: 'github-light' },
  },
});
