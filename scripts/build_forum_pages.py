#!/usr/bin/env python3
"""Build Forumotion paste-ready HTML plus GitHub-hosted catalog, CSS, and JS.

Reads gift list JSON under src/data/gifts/, writes:
  public/data/catalog.json
  public/assets/df.css
  public/assets/df.js
  /workspace/forum-pages/*.html  (ready to paste into Forumotion ACP)

Usage:
  python3 scripts/build_forum_pages.py
  python3 scripts/build_forum_pages.py --out /workspace/forum-pages

Do not put spaced ASCII hyphens as asides in comments (use ': ').
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GIFTS_DIR = ROOT / "src" / "data" / "gifts"
PUBLIC = ROOT / "public"
DEFAULT_FORUM_OUT = Path("/workspace/forum-pages")
SITE_URL = "https://spacexygrok.github.io"
FORUM_URL = "https://dealsandfindshq.forumotion.com"
BRAND_MD = ROOT.parent / "x-rebrand" / "brand.md"
SODA_PREVIEW = (
    ROOT.parent
    / "telegraph-pages"
    / "lists"
    / "previews"
    / "rev2"
    / "pepsi-coke-deals-by-store-week-of-2026-10-29.md"
)

DISCLOSURE = (
    "This site uses ads and affiliate links and may earn a commission. "
    "This is a catalogue, not a shop. Every item opens a link to a different store's website."
)

SLOGAN_FALLBACK = "Price drops · gift deals · tool discounts"


def load_slogan() -> str:
    if not BRAND_MD.is_file():
        return SLOGAN_FALLBACK
    text = BRAND_MD.read_text(encoding="utf-8")
    # Prefer the header subtitle line from visual identity.
    m = re.search(r'subtitle\s+[""]([^""]+)[""]', text, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"subtitle\s+[\"']([^\"']+)[\"']", text, re.I)
    if m:
        return m.group(1).strip()
    if "Price drops" in text and "gift deals" in text:
        return SLOGAN_FALLBACK
    return SLOGAN_FALLBACK


def parse_money(raw: str | None) -> float | None:
    if not raw:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # Ranges: "From $99 to $110" or "$99-$110"
    from_m = re.search(
        r"(?i)from\s*\$?\s*([\d,]+(?:\.\d+)?)\s*(?:to|-|–)\s*\$?\s*([\d,]+(?:\.\d+)?)",
        s,
    )
    if from_m:
        return float(from_m.group(1).replace(",", ""))
    # "$45+" style list prices: take the number
    nums = re.findall(r"\$?\s*([\d,]+(?:\.\d+)?)", s.replace(",", ""))
    if not nums:
        # bare number
        m = re.search(r"([\d]+(?:\.\d+)?)", s.replace(",", ""))
        return float(m.group(1)) if m else None
    return float(nums[0].replace(",", ""))


def parse_range(raw: str | None) -> tuple[float | None, float | None]:
    if not raw:
        return None, None
    s = str(raw).strip()
    from_m = re.search(
        r"(?i)from\s*\$?\s*([\d,]+(?:\.\d+)?)\s*(?:to|-|–)\s*\$?\s*([\d,]+(?:\.\d+)?)",
        s,
    )
    if from_m:
        return (
            float(from_m.group(1).replace(",", "")),
            float(from_m.group(2).replace(",", "")),
        )
    n = parse_money(s)
    return n, None


def money_fmt(n: float | None) -> str | None:
    if n is None:
        return None
    if abs(n - round(n)) < 1e-9:
        return f"${int(round(n))}"
    return f"${n:.2f}"


def shop_label(retailer: str, url: str) -> str:
    r = (retailer or "").strip()
    if r.lower() == "amazon":
        return "Shop amazon.com"
    if r:
        domain = r.lower().replace(" ", "")
        if "." not in domain:
            domain = f"{domain}.com"
        return f"Shop {domain}"
    # fallback from URL
    m = re.search(r"https?://(?:www\.)?([^/]+)", url or "")
    if m:
        return f"Shop {m.group(1)}"
    return "Shop store"


def load_soda_card() -> dict:
    """Build Weekly Soda Deal card from preview markdown if present."""
    card = {
        "id": "weekly-soda",
        "kind": "feature",
        "title": "Weekly Soda Deal",
        "status": "coming_soon",
        "summary": "Coming soon",
        "store": None,
        "link": None,
        "image": None,
        "now_price": None,
        "old_price": None,
        "savings_dollars": None,
        "savings_percent": None,
        "date": None,
    }
    if not SODA_PREVIEW.is_file():
        return card
    text = SODA_PREVIEW.read_text(encoding="utf-8")
    # Detect Target Circle offer
    if "Target Circle" not in text and "40% off" not in text:
        return card
    end = None
    m = re.search(r"through\s+(\d{4}-\d{2}-\d{2})", text)
    if m:
        end = m.group(1)
    pepsi = re.search(
        r"Pepsi \(Target Circle.*?Price per can:\*\*\s*about\s*\$([0-9.]+)",
        text,
        re.S,
    )
    coke = re.search(
        r"Coca-Cola \(Target Circle.*?Price per can:\*\*\s*about\s*\$([0-9.]+)",
        text,
        re.S,
    )
    link_m = re.search(r"\[Shop target\.com\]\((https://www\.target\.com[^)]+)\)", text)
    parts = ["Target Circle: 40% off when you buy 3 soda 12-packs"]
    if end:
        parts.append(f"(through {end})")
    detail = []
    if pepsi:
        detail.append(f"Pepsi about ${pepsi.group(1)} per can after the offer")
    if coke:
        detail.append(f"Coca-Cola about ${coke.group(1)} per can after the offer")
    summary = " ".join(parts) + "."
    if detail:
        summary += " " + "; ".join(detail) + "."
    card.update(
        {
            "status": "active",
            "summary": summary,
            "store": "Target",
            "link": link_m.group(1) if link_m else "https://www.target.com/c/soda-grocery/-/N-5xsz1",
            "date": end,
            "category": "Soda",
        }
    )
    return card


def product_to_item(prod: dict, page: dict) -> dict:
    now_lo, now_hi = parse_range(prod.get("price"))
    old = parse_money(prod.get("listPrice") or "")
    # For ranges, treat "now" display as range; savings only when single now + old
    now_price = now_lo
    savings_dollars = None
    savings_percent = None
    if now_price is not None and old is not None and old > now_price and now_hi is None:
        savings_dollars = round(old - now_price, 2)
        savings_percent = round(100.0 * (old - now_price) / old, 1)

    price_display = prod.get("price") or ""
    # Normalize display helpers for HTML
    is_range = now_hi is not None
    return {
        "type": "item",
        "name": prod.get("name") or "",
        "slug": f"{page['slug']}#{prod.get('anchor') or ''}",
        "page_slug": page["slug"],
        "page_title": page["title"],
        "category": page.get("category") or page.get("topic") or "",
        "store": prod.get("retailer") or "",
        "now_price": now_price,
        "now_price_high": now_hi,
        "old_price": old,
        "price_raw": price_display,
        "list_price_raw": prod.get("listPrice") or "",
        "is_range": is_range,
        "savings_dollars": savings_dollars,
        "savings_percent": savings_percent,
        "image": prod.get("image"),
        "image_alt": prod.get("imageAlt") or prod.get("name") or "",
        "link": prod.get("url") or "",
        "shop_label": shop_label(prod.get("retailer") or "", prod.get("url") or ""),
        "date": prod.get("priceCheckedDate") or page.get("lastUpdated"),
        "note": prod.get("note") or "",
        "badge": prod.get("badge") or "",
        "anchor": prod.get("anchor") or "",
        "status": prod.get("status") or "active",
    }


def infer_category(slug: str, title: str) -> str:
    s = (slug + " " + title).lower()
    if "hardware" in s or "computer" in s:
        return "Computer Hardware"
    if "video" in s or "game" in s:
        return "Video Games"
    return title.split("(")[0].strip() or "Deals"


def build_catalog() -> dict:
    index_path = GIFTS_DIR / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    pages = []
    items = []
    for entry in index:
        if entry.get("status") != "active":
            continue
        slug = entry["slug"]
        data_path = GIFTS_DIR / f"{slug}.json"
        if not data_path.is_file():
            print(f"WARN: missing {data_path}", file=sys.stderr)
            continue
        data = json.loads(data_path.read_text(encoding="utf-8"))
        category = infer_category(slug, data.get("title") or entry.get("title") or "")
        page = {
            "type": "page",
            "title": data.get("title") or entry.get("title"),
            "slug": slug,
            "category": category,
            "description": data.get("description") or entry.get("description") or "",
            "intro": data.get("intro") or "",
            "disclosure": data.get("disclosure") or DISCLOSURE,
            "date": data.get("lastUpdated") or entry.get("lastUpdated"),
            "valid_until": data.get("validUntil") or entry.get("validUntil"),
            "item_count": len(data.get("products") or []),
            "forum_path": forum_path_for(slug),
            "image": data.get("ogImage"),
            "status": "active",
        }
        page_items = []
        for prod in data.get("products") or []:
            if prod.get("status") == "expired":
                continue
            it = product_to_item(prod, page)
            page_items.append(it)
            items.append(it)
        # Page-level biggest saving
        sav = [i["savings_dollars"] for i in page_items if i.get("savings_dollars") is not None]
        page["biggest_saving_dollars"] = max(sav) if sav else None
        page["items"] = page_items
        pages.append(page)

    soda = load_soda_card()
    # Top deal of the week: max savings_dollars
    top_deal = None
    for it in items:
        sd = it.get("savings_dollars")
        if sd is None:
            continue
        if top_deal is None or sd > top_deal["savings_dollars"]:
            top_deal = it

    # Store-wide sale: none detected in current gift data
    storewide = {
        "id": "storewide",
        "kind": "feature",
        "title": "Best Store-wide Saving Deal",
        "status": "coming_soon",
        "summary": "Coming soon",
        "store": None,
        "link": None,
        "savings_dollars": None,
        "savings_percent": None,
    }

    catalog = {
        "generated": date.today().isoformat(),
        "site_url": SITE_URL,
        "forum_url": FORUM_URL,
        "slogan": load_slogan(),
        "disclosure": DISCLOSURE,
        "pages": pages,
        "items": items,
        "features": {
            "weekly_soda": soda,
            "top_deal_of_week": (
                {
                    "id": "top-deal",
                    "kind": "feature",
                    "title": "Top Deal of the Week",
                    "status": "active" if top_deal else "coming_soon",
                    "summary": (
                        f"{top_deal['name']}: save {money_fmt(top_deal['savings_dollars'])}"
                        if top_deal
                        else "Coming soon"
                    ),
                    "item": top_deal,
                }
                if True
                else None
            ),
            "storewide": storewide,
        },
    }
    return catalog


def forum_path_for(slug: str) -> str:
    mapping = {
        "top-5-computer-hardware-picks-november-2026": "/h2-computer-hardware",
        "top-10-video-game-deals-november-2026": "/h3-video-game-deals",
    }
    return mapping.get(slug, f"/h-{slug}")


def css_text() -> str:
    return """/* Deals and Finds: shared Forumotion / GitHub card styles */
:root {
  --df-bg: #0f1419;
  --df-surface: #1a222c;
  --df-surface-2: #232d3a;
  --df-border: #3a4656;
  --df-text: #e8eef5;
  --df-muted: #9aa8b8;
  --df-accent: #2bb5a0;
  --df-accent-2: #e86b5a;
  --df-link: #6ec9ff;
  --df-radius: 12px;
  --df-gap: 1rem;
  --df-font: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
}
*, *::before, *::after { box-sizing: border-box; }
html { font-size: 16px; }
body.df-body {
  margin: 0;
  padding: 0;
  font-family: var(--df-font);
  background: var(--df-bg);
  color: var(--df-text);
  line-height: 1.5;
}
.df-wrap {
  max-width: 1100px;
  margin: 0 auto;
  padding: 1.25rem 1rem 3rem;
}
.df-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 1.25rem;
  align-items: center;
  margin-bottom: 1rem;
  font-size: 0.95rem;
}
.df-nav a {
  color: var(--df-link);
  text-decoration: none;
}
.df-nav a:hover { text-decoration: underline; }
.df-title {
  font-size: clamp(1.85rem, 4vw, 2.5rem);
  font-weight: 750;
  letter-spacing: -0.02em;
  margin: 0 0 0.35rem;
  line-height: 1.15;
}
.df-slogan {
  font-size: clamp(1.05rem, 2.2vw, 1.25rem);
  color: var(--df-muted);
  margin: 0 0 0.65rem;
  font-weight: 500;
}
.df-disclosure {
  font-size: 0.8rem;
  color: var(--df-muted);
  margin: 0 0 1.25rem;
  max-width: 62ch;
}
.df-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: var(--df-gap);
  margin-bottom: 1.5rem;
}
.df-card {
  background: var(--df-surface);
  border: 1px solid var(--df-border);
  border-radius: var(--df-radius);
  padding: 1rem 1.05rem;
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
  min-height: 100%;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.df-card:hover {
  border-color: #5a6a7e;
  box-shadow: 0 4px 18px rgba(0,0,0,0.25);
}
.df-card h2, .df-card h3 {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 650;
}
.df-card .df-meta {
  font-size: 0.8rem;
  color: var(--df-muted);
}
.df-card .df-summary {
  font-size: 0.92rem;
  color: var(--df-text);
  flex: 1;
}
.df-card a.df-cta {
  display: inline-block;
  margin-top: 0.25rem;
  color: var(--df-link);
  font-weight: 600;
  text-decoration: none;
  font-size: 0.92rem;
}
.df-card a.df-cta:hover { text-decoration: underline; }
.df-badge {
  display: inline-block;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 0.15rem 0.45rem;
  border-radius: 999px;
  background: var(--df-surface-2);
  border: 1px solid var(--df-border);
  color: var(--df-accent);
  width: fit-content;
}
.df-badge--soon {
  color: var(--df-muted);
}
.df-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  align-items: center;
  justify-content: space-between;
  margin: 0.5rem 0 1rem;
}
.df-search {
  flex: 1 1 220px;
  min-width: 180px;
}
.df-search input, .df-sort select {
  width: 100%;
  padding: 0.55rem 0.7rem;
  border-radius: 8px;
  border: 1px solid var(--df-border);
  background: var(--df-surface);
  color: var(--df-text);
  font: inherit;
}
.df-sort {
  flex: 0 1 200px;
}
.df-sort label {
  display: block;
  font-size: 0.75rem;
  color: var(--df-muted);
  margin-bottom: 0.2rem;
}
.df-section-title {
  font-size: 1.25rem;
  margin: 0.5rem 0 0.75rem;
  font-weight: 700;
}
.df-product-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: var(--df-gap);
}
.df-product {
  background: var(--df-surface);
  border: 1px solid var(--df-border);
  border-radius: var(--df-radius);
  padding: 0.85rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.df-product img {
  width: 100%;
  max-height: 180px;
  object-fit: contain;
  background: #0a0e12;
  border-radius: 8px;
  border: 1px solid var(--df-border);
}
.df-product h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: 650;
  line-height: 1.3;
}
.df-prices {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.45rem;
}
.df-now {
  font-size: 1.35rem;
  font-weight: 750;
  color: var(--df-accent);
}
.df-old {
  font-size: 0.95rem;
  color: var(--df-muted);
  text-decoration: line-through;
}
.df-save {
  font-size: 0.82rem;
  color: var(--df-accent-2);
  font-weight: 600;
}
.df-note {
  font-size: 0.85rem;
  color: var(--df-muted);
}
.df-intro {
  font-size: 1rem;
  margin: 0 0 1rem;
  max-width: 70ch;
}
.df-fm-credit {
  margin-top: 2.5rem;
  font-size: 0.75rem;
  color: var(--df-muted);
  text-align: center;
}
.df-fm-credit a { color: var(--df-muted); }
.df-hidden { display: none !important; }
.df-empty {
  color: var(--df-muted);
  font-size: 0.95rem;
  padding: 1rem 0;
}
@media (max-width: 560px) {
  .df-wrap { padding: 1rem 0.75rem 2rem; }
  .df-now { font-size: 1.2rem; }
}
"""


def js_text() -> str:
    return r"""/* Deals and Finds: search and sort for Forumotion HTML pages */
(function () {
  "use strict";

  var CATALOG_URL = "https://spacexygrok.github.io/data/catalog.json";

  function qs(sel, root) {
    return (root || document).querySelector(sel);
  }
  function qsa(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function money(n) {
    if (n == null || isNaN(n)) return "";
    if (Math.abs(n - Math.round(n)) < 1e-9) return "$" + Math.round(n);
    return "$" + Number(n).toFixed(2);
  }

  function fetchCatalog() {
    return fetch(CATALOG_URL, { credentials: "omit", mode: "cors" }).then(function (r) {
      if (!r.ok) throw new Error("catalog " + r.status);
      return r.json();
    });
  }

  function initHome(catalog) {
    var listEl = qs("[data-df-topics]");
    var searchEl = qs("[data-df-search]");
    var sortEl = qs("[data-df-sort]");
    var resultsEl = qs("[data-df-search-results]");
    if (!listEl) return;

    var pages = (catalog.pages || []).slice();

    function renderTopics(list) {
      listEl.innerHTML = "";
      if (!list.length) {
        listEl.innerHTML = '<p class="df-empty">No topic lists match.</p>';
        return;
      }
      list.forEach(function (p) {
        var a = document.createElement("a");
        a.className = "df-card";
        a.href = p.forum_path || "#";
        a.setAttribute("data-title", p.title || "");
        a.setAttribute("data-items", String(p.item_count || 0));
        a.setAttribute("data-saving", String(p.biggest_saving_dollars || 0));
        a.setAttribute("data-date", p.date || "");
        var saveLine =
          p.biggest_saving_dollars != null
            ? "Biggest listed saving: " + money(p.biggest_saving_dollars)
            : "Savings vary by item";
        a.innerHTML =
          "<h3>" +
          escapeHtml(p.title) +
          "</h3>" +
          '<div class="df-meta">' +
          escapeHtml(p.category || "") +
          " · " +
          (p.item_count || 0) +
          " items · Updated " +
          escapeHtml(p.date || "") +
          "</div>" +
          '<div class="df-summary">' +
          escapeHtml((p.description || "").replace(/#ad/g, "").trim()) +
          "</div>" +
          '<div class="df-meta">' +
          escapeHtml(saveLine) +
          "</div>" +
          '<span class="df-cta">Open list</span>';
        listEl.appendChild(a);
      });
    }

    function sortPages(mode) {
      var list = pages.slice();
      if (mode === "items") {
        list.sort(function (a, b) {
          return (b.item_count || 0) - (a.item_count || 0);
        });
      } else if (mode === "saving") {
        list.sort(function (a, b) {
          return (b.biggest_saving_dollars || 0) - (a.biggest_saving_dollars || 0);
        });
      } else if (mode === "az") {
        list.sort(function (a, b) {
          return (a.title || "").localeCompare(b.title || "");
        });
      } else {
        list.sort(function (a, b) {
          return (b.date || "").localeCompare(a.date || "");
        });
      }
      return list;
    }

    function apply() {
      var mode = sortEl ? sortEl.value : "newest";
      var q = searchEl ? searchEl.value.trim().toLowerCase() : "";
      var list = sortPages(mode);
      if (q) {
        list = list.filter(function (p) {
          var hay =
            (p.title || "") +
            " " +
            (p.category || "") +
            " " +
            (p.description || "");
          return hay.toLowerCase().indexOf(q) !== -1;
        });
      }
      renderTopics(list);

      if (resultsEl) {
        if (!q) {
          resultsEl.className = "df-hidden";
          resultsEl.innerHTML = "";
          return;
        }
        var hits = (catalog.items || []).filter(function (it) {
          var hay =
            (it.name || "") +
            " " +
            (it.store || "") +
            " " +
            (it.category || "") +
            " " +
            (it.page_title || "");
          return hay.toLowerCase().indexOf(q) !== -1;
        }).slice(0, 12);
        resultsEl.className = "df-product-grid";
        resultsEl.innerHTML = hits
          .map(function (it) {
            var price = formatPrice(it);
            var href = (it.page_slug && pageForumPath(it.page_slug, catalog)) || it.link || "#";
            return (
              '<article class="df-product">' +
              (it.image
                ? '<img src="' +
                  escapeAttr(it.image) +
                  '" alt="' +
                  escapeAttr(it.image_alt || it.name) +
                  '" loading="lazy" />'
                : "") +
              "<h3>" +
              escapeHtml(it.name) +
              "</h3>" +
              '<div class="df-prices">' +
              price +
              "</div>" +
              '<div class="df-meta">' +
              escapeHtml(it.page_title || "") +
              "</div>" +
              '<a class="df-cta" href="' +
              escapeAttr(href) +
              '">View on list</a>' +
              "</article>"
            );
          })
          .join("");
        if (!hits.length) {
          resultsEl.innerHTML = '<p class="df-empty">No items match that search.</p>';
        }
      }
    }

    if (sortEl) sortEl.addEventListener("change", apply);
    if (searchEl) searchEl.addEventListener("input", apply);
    apply();
  }

  function pageForumPath(slug, catalog) {
    var pages = catalog.pages || [];
    for (var i = 0; i < pages.length; i++) {
      if (pages[i].slug === slug) return pages[i].forum_path;
    }
    return null;
  }

  function formatPrice(it) {
    if (it.is_range && it.now_price != null && it.now_price_high != null) {
      return (
        '<span class="df-now">From ' +
        money(it.now_price) +
        " to " +
        money(it.now_price_high) +
        "</span>"
      );
    }
    var html = "";
    if (it.now_price != null) {
      html += '<span class="df-now">Now ' + money(it.now_price) + "</span>";
    } else if (it.price_raw) {
      html += '<span class="df-now">' + escapeHtml(it.price_raw) + "</span>";
    }
    if (it.old_price != null) {
      html += '<span class="df-old">' + money(it.old_price) + "</span>";
    }
    if (it.savings_dollars != null) {
      html +=
        '<span class="df-save">Save ' +
        money(it.savings_dollars) +
        (it.savings_percent != null ? " (" + it.savings_percent + "%)" : "") +
        "</span>";
    }
    return html;
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function escapeAttr(s) {
    return escapeHtml(s).replace(/'/g, "&#39;");
  }

  function initListSort() {
    var grid = qs("[data-df-products]");
    var sortEl = qs("[data-df-list-sort]");
    if (!grid || !sortEl) return;
    sortEl.addEventListener("change", function () {
      var cards = qsa(".df-product", grid);
      var mode = sortEl.value;
      cards.sort(function (a, b) {
        if (mode === "saving") {
          return (
            parseFloat(b.getAttribute("data-saving") || "0") -
            parseFloat(a.getAttribute("data-saving") || "0")
          );
        }
        if (mode === "price") {
          return (
            parseFloat(a.getAttribute("data-price") || "0") -
            parseFloat(b.getAttribute("data-price") || "0")
          );
        }
        if (mode === "az") {
          return (a.getAttribute("data-name") || "").localeCompare(
            b.getAttribute("data-name") || ""
          );
        }
        return 0;
      });
      cards.forEach(function (c) {
        grid.appendChild(c);
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initListSort();
    if (!qs("[data-df-topics]")) return;
    fetchCatalog()
      .then(initHome)
      .catch(function (err) {
        var listEl = qs("[data-df-topics]");
        if (listEl) {
          listEl.innerHTML =
            '<p class="df-empty">Topic lists are embedded below. Live catalog search needs a network fetch of catalog.json.</p>';
        }
        console.warn("DF catalog fetch failed", err);
      });
  });

  window.DF = { fetchCatalog: fetchCatalog, formatPrice: formatPrice };
})();
"""


def price_html(item: dict) -> str:
    if item.get("is_range") and item.get("now_price") is not None and item.get("now_price_high") is not None:
        return (
            f'<div class="df-prices"><span class="df-now">From {money_fmt(item["now_price"])} '
            f'to {money_fmt(item["now_price_high"])}</span></div>'
        )
    parts = ['<div class="df-prices">']
    if item.get("now_price") is not None:
        parts.append(f'<span class="df-now">Now {money_fmt(item["now_price"])}</span>')
    elif item.get("price_raw"):
        parts.append(f'<span class="df-now">{esc(item["price_raw"])}</span>')
    if item.get("old_price") is not None:
        parts.append(f'<span class="df-old">{money_fmt(item["old_price"])}</span>')
    if item.get("savings_dollars") is not None:
        pct = item.get("savings_percent")
        pct_s = f" ({pct}%)" if pct is not None else ""
        parts.append(
            f'<span class="df-save">Save {money_fmt(item["savings_dollars"])}{pct_s}</span>'
        )
    parts.append("</div>")
    return "".join(parts)


def esc(s: str) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def nav_html(active: str = "home") -> str:
    links = [
        ("home", "/", "Home"),
        ("hardware", "/h2-computer-hardware", "Computer Hardware"),
        ("games", "/h3-video-game-deals", "Video Game Deals"),
        ("forum", "/forum", "Forum boards"),
        ("search", "/h1-deals-and-finds#search", "Search"),
    ]
    bits = []
    for key, href, label in links:
        bits.append(f'<a href="{href}">{esc(label)}</a>')
    return '<nav class="df-nav" aria-label="Main">' + "".join(bits) + "</nav>"


def fm_credit() -> str:
    return (
        '<p class="df-fm-credit">Hosted with '
        '<a href="https://www.forumotion.com/" rel="nofollow">Forumotion</a>'
        " · Free forum</p>"
    )


def head_block(title: str, inline_css: bool, css_body: str) -> str:
    """External CSS preferred. Inline fallback kept for paste if external is blocked."""
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8" />',
        '<meta name="viewport" content="width=device-width, initial-scale=1" />',
        f"<title>{esc(title)}</title>",
        f'<link rel="stylesheet" href="{SITE_URL}/assets/df.css" />',
    ]
    if inline_css:
        parts.append(f"<style>\n{css_body}\n</style>")
        parts.append(
            "<!-- FALLBACK NOTE: style above is inlined in case external CSS is blocked. "
            "Prefer the link tag when Forumotion allows it. -->"
        )
    parts.append("</head>")
    return "\n".join(parts)


def script_block(inline_js: bool, js_body: str) -> str:
    parts = [
        f'<script src="{SITE_URL}/assets/df.js" defer></script>',
    ]
    if inline_js:
        # Guard so inline copy does not double-bind if external df.js already loaded.
        parts.append(
            "<script>\n"
            "if (!window.DF) {\n"
            + js_body
            + "\n} else {\n"
            "  /* external df.js already loaded; skipped inline fallback */\n"
            "}\n"
            "</script>"
        )
        parts.append(
            "<!-- FALLBACK NOTE: inline script runs only if external df.js did not define window.DF. "
            "Classic script tags do not need CORS; fetch(catalog.json) needs ACAO (GitHub Pages sends *). -->"
        )
    return "\n".join(parts)


def feature_card_html(feat: dict, kind: str) -> str:
    title = feat.get("title") or kind
    status = feat.get("status") or "coming_soon"
    if status == "coming_soon" or not feat.get("summary") or feat.get("summary") == "Coming soon":
        return (
            f'<article class="df-card">'
            f'<span class="df-badge df-badge--soon">Coming soon</span>'
            f"<h2>{esc(title)}</h2>"
            f'<p class="df-summary">Coming soon</p>'
            f"</article>"
        )
    if kind == "soda":
        link = feat.get("link") or "#"
        return (
            f'<article class="df-card">'
            f'<span class="df-badge">Weekly</span>'
            f"<h2>{esc(title)}</h2>"
            f'<p class="df-summary">{esc(feat.get("summary") or "")}</p>'
            f'<a class="df-cta" href="{esc(link)}" rel="sponsored nofollow noopener" target="_blank">'
            f"Shop target.com</a>"
            f"</article>"
        )
    if kind == "top":
        item = feat.get("item") or {}
        link = item.get("link") or "#"
        label = item.get("shop_label") or "Shop store"
        img = ""
        if item.get("image"):
            img = (
                f'<img src="{esc(item["image"])}" alt="{esc(item.get("image_alt") or item.get("name") or "")}" '
                f'loading="lazy" style="max-height:120px;object-fit:contain;border-radius:8px;" />'
            )
        save = money_fmt(item.get("savings_dollars"))
        return (
            f'<article class="df-card">'
            f'<span class="df-badge">Top deal</span>'
            f"<h2>{esc(title)}</h2>"
            f"{img}"
            f'<p class="df-summary"><strong>{esc(item.get("name") or "")}</strong>. '
            f"Save {esc(save or '')} "
            f'(Now {esc(money_fmt(item.get("now_price")) or "")}'
            f'{(", was " + esc(money_fmt(item.get("old_price")) or "")) if item.get("old_price") else ""}).</p>'
            f'<a class="df-cta" href="{esc(link)}" rel="sponsored nofollow noopener" target="_blank">'
            f"{esc(label)}</a>"
            f"</article>"
        )
    return (
        f'<article class="df-card">'
        f'<span class="df-badge df-badge--soon">Coming soon</span>'
        f"<h2>{esc(title)}</h2>"
        f'<p class="df-summary">Coming soon</p>'
        f"</article>"
    )


def topic_cards_static(pages: list[dict]) -> str:
    """Static fallback topic cards so homepage works before JS fetch."""
    cards = []
    for p in pages:
        save = p.get("biggest_saving_dollars")
        save_line = (
            f"Biggest listed saving: {money_fmt(save)}"
            if save is not None
            else "Savings vary by item"
        )
        desc = (p.get("description") or "").replace("#ad", "").strip()
        cards.append(
            f'<a class="df-card" href="{esc(p.get("forum_path") or "#")}" '
            f'data-title="{esc(p.get("title") or "")}" '
            f'data-items="{p.get("item_count") or 0}" '
            f'data-saving="{save or 0}" data-date="{esc(p.get("date") or "")}">'
            f'<h3>{esc(p.get("title") or "")}</h3>'
            f'<div class="df-meta">{esc(p.get("category") or "")} · '
            f'{p.get("item_count") or 0} items · Updated {esc(p.get("date") or "")}</div>'
            f'<div class="df-summary">{esc(desc)}</div>'
            f'<div class="df-meta">{esc(save_line)}</div>'
            f'<span class="df-cta">Open list</span></a>'
        )
    return "\n".join(cards)


def product_card_html(item: dict) -> str:
    img = ""
    if item.get("image"):
        img = (
            f'<img src="{esc(item["image"])}" alt="{esc(item.get("image_alt") or item.get("name") or "")}" '
            f'loading="lazy" />'
        )
    note = item.get("note") or ""
    # Keep note short on cards: first sentence-ish
    return (
        f'<article class="df-product" id="{esc(item.get("anchor") or "")}" '
        f'data-name="{esc(item.get("name") or "")}" '
        f'data-price="{item.get("now_price") or 0}" '
        f'data-saving="{item.get("savings_dollars") or 0}">'
        f"{img}"
        f'<h3>{esc(item.get("name") or "")}</h3>'
        f"{price_html(item)}"
        f'<p class="df-note">{esc(note)}</p>'
        f'<a class="df-cta" href="{esc(item.get("link") or "#")}" '
        f'rel="sponsored nofollow noopener" target="_blank">'
        f'{esc(item.get("shop_label") or "Shop store")}</a>'
        f"</article>"
    )


def build_homepage(catalog: dict, css: str, js: str) -> str:
    slogan = catalog.get("slogan") or SLOGAN_FALLBACK
    feats = catalog.get("features") or {}
    soda = feats.get("weekly_soda") or {}
    top = feats.get("top_deal_of_week") or {}
    storewide = feats.get("storewide") or {}
    pages = catalog.get("pages") or []

    body = f"""<body class="df-body">
<div class="df-wrap">
{nav_html("home")}
<h1 class="df-title">Deals and Finds</h1>
<p class="df-slogan">{esc(slogan)}</p>
<p class="df-disclosure">{esc(DISCLOSURE)}</p>

<section class="df-grid" aria-label="Featured deals">
{feature_card_html(soda, "soda")}
{feature_card_html(top, "top")}
{feature_card_html(storewide, "storewide")}
</section>

<h2 class="df-section-title" id="lists">Topic lists</h2>
<div class="df-toolbar" id="search">
  <div class="df-search">
    <label class="df-meta" for="df-search-input">Search items and pages</label>
    <input id="df-search-input" type="search" placeholder="Search deals, stores, lists" data-df-search autocomplete="off" />
  </div>
  <div class="df-sort">
    <label for="df-sort-select">Sort by</label>
    <select id="df-sort-select" data-df-sort>
      <option value="newest">Newest</option>
      <option value="items">Most items</option>
      <option value="saving">Biggest saving</option>
      <option value="az">A to Z</option>
    </select>
  </div>
</div>
<div data-df-search-results class="df-hidden" aria-live="polite"></div>
<div class="df-grid" data-df-topics>
{topic_cards_static(pages)}
</div>
{fm_credit()}
</div>
{script_block(True, js)}
</body>
</html>
"""
    return head_block("Deals and Finds", True, css) + "\n" + body


def list_intro(page: dict) -> str:
    intro = (page.get("intro") or "").strip()
    if intro:
        return intro
    title = page.get("title") or "this list"
    return (
        f"{title} gathers current price drops we are watching. "
        f"Each card links out to the retailer's own store page. "
        f"Prices change, so confirm the live tag before you buy."
    )


def build_list_page(page: dict, css: str, js: str) -> str:
    items_html = "\n".join(product_card_html(it) for it in page.get("items") or [])
    title = page.get("title") or "Deal list"
    body = f"""<body class="df-body">
<div class="df-wrap">
{nav_html("list")}
<h1 class="df-title">{esc(title)}</h1>
<p class="df-disclosure">{esc(DISCLOSURE)}</p>
<p class="df-intro">{esc(list_intro(page))}</p>
<div class="df-toolbar">
  <div class="df-sort">
    <label for="df-list-sort">Sort by</label>
    <select id="df-list-sort" data-df-list-sort>
      <option value="default">As listed</option>
      <option value="saving">Biggest saving</option>
      <option value="price">Lowest price</option>
      <option value="az">A to Z</option>
    </select>
  </div>
</div>
<div class="df-product-grid" data-df-products>
{items_html}
</div>
{fm_credit()}
</div>
{script_block(True, js)}
</body>
</html>
"""
    return head_block(title, True, css) + "\n" + body


def build_test_page(css: str, js: str) -> str:
    body = f"""<body class="df-body">
<div class="df-wrap">
{nav_html("test")}
<h1 class="df-title">Forumotion asset test</h1>
<p class="df-slogan">Checks external CSS, JS, and catalog.json fetch</p>
<p class="df-disclosure">{esc(DISCLOSURE)}</p>
<section class="df-grid">
  <article class="df-card">
    <span class="df-badge">CSS</span>
    <h2>Stylesheet</h2>
    <p class="df-summary">If this card has a thin border, rounded corners, and dark theme, external or inlined CSS loaded.</p>
  </article>
  <article class="df-card">
    <span class="df-badge">JS</span>
    <h2>Script</h2>
    <p class="df-summary" id="df-js-status">Waiting for script…</p>
  </article>
  <article class="df-card">
    <span class="df-badge">JSON</span>
    <h2>Catalog fetch</h2>
    <p class="df-summary" id="df-json-status">Waiting for fetch…</p>
  </article>
</section>
{fm_credit()}
</div>
{script_block(True, js)}
<script>
document.addEventListener("DOMContentLoaded", function () {{
  var jsEl = document.getElementById("df-js-status");
  if (jsEl) jsEl.textContent = window.DF ? "df.js loaded (window.DF present)." : "Inline or external JS ran, but window.DF missing.";
  var jsonEl = document.getElementById("df-json-status");
  if (!window.DF || !window.DF.fetchCatalog) {{
    if (jsonEl) jsonEl.textContent = "fetchCatalog unavailable.";
    return;
  }}
  window.DF.fetchCatalog().then(function (c) {{
    if (jsonEl) jsonEl.textContent = "OK: " + (c.pages || []).length + " pages, " + (c.items || []).length + " items.";
  }}).catch(function (e) {{
    if (jsonEl) jsonEl.textContent = "Fetch failed: " + e;
  }});
}});
</script>
</body>
</html>
"""
    return head_block("Forumotion asset test", True, css) + "\n" + body


def write_admin_notes(out_dir: Path, catalog: dict) -> None:
    """Admin steps for the owner (not pasted into Forumotion pages)."""
    text = f"""# Forumotion admin steps (create pages yourself)

Forum: {FORUM_URL}
ACP HTML pages: Admin panel → Modules → HTML
(ModernBB path often looks like /admin/?modules&sub=html)

## Field names (create / edit HTML page)

1. **Title** of the HTML page (becomes part of the URL slug).
2. **Do you wish to use your forum header and footer ?** → Yes / No
3. **Use this page as homepage ?** → Yes / No
4. Content box: paste the HTML from the matching file under this folder.

## Recommended settings

| Page | Suggested title (URL) | Header/footer | Homepage | Paste file |
|------|----------------------|---------------|----------|------------|
| Homepage | deals-and-finds → `/h1-deals-and-finds` | **No** (own chrome) | **Yes** | `01-homepage.html` |
| Hardware | computer-hardware → `/h2-computer-hardware` | No (or Yes if you want FM chrome) | No | `02-computer-hardware.html` |
| Video games | video-game-deals → `/h3-video-game-deals` | No | No | `03-video-game-deals.html` |
| Asset test | asset-test → `/h4-asset-test` | No | No | `04-asset-test.html` |

Notes:
- Exact `/hN-slug` numbers depend on creation order. First page is often `/h1-…`, second `/h2-…`. If your numbers differ, edit the nav links inside each HTML file (or re-run the builder after updating `forum_path_for` in the script).
- When header/footer = **No**, Forumotion requires a visible link to forumotion.com. Each generated file includes one in `.df-fm-credit`.
- When header/footer = **Yes**, paste only the inner content if the ACP wraps a full document for you; prefer **No** + full document for this design.
- Page size limit is about **64,000–65,000 characters** (including spaces). These files stay under that by design; CSS/JS are also linked from GitHub.

## Homepage as forum index

Set **Use this page as homepage ?** to **Yes** on the homepage HTML page.
Link back to the classic board index with `/forum` (not `/`), or visitors bounce to the HTML homepage again.
Sources: https://help.forumotion.com/t151505-display-only-image-and-background-in-portal
and https://help.forumotion.com/t141029-html-page-redirect

## External assets

- CSS: {SITE_URL}/assets/df.css
- JS: {SITE_URL}/assets/df.js
- Catalog: {SITE_URL}/data/catalog.json
GitHub Pages sends `Access-Control-Allow-Origin: *`, so `fetch(catalog.json)` from the forum origin should work.
Classic `<script src>` / `<link rel="stylesheet">` do not need CORS.
Each HTML file also inlines CSS and JS as a fallback (see HTML comments).

## Placeholders

- Best Store-wide Saving Deal: Coming soon (no store-wide sale in current gift JSON).
- Weekly Soda Deal: filled from telegraph Pepsi/Coke preview when present; otherwise Coming soon.
- Top Deal of the Week: computed as max savings_dollars across catalog items.

Generated: {catalog.get("generated")}
Slogan: {catalog.get("slogan")}
"""
    (out_dir / "ADMIN-STEPS.md").write_text(text, encoding="utf-8")


def write_research(out_dir: Path) -> None:
    text = """# Forumotion custom HTML research (public docs only)

## Can an HTML page drop the forum header and footer?

Yes. On create/edit: **Do you wish to use your forum header and footer ?** → **No** yields a blank page; **Yes** keeps logo, nav, and footer.
Source: https://help.forumotion.com/t13528-creating-an-html-page

## External script / link tags and CORS fetch

- Forumotion staff guidance: you may link an external `.css` from the page `<head>` (`<link rel="stylesheet" href="https://…">`). The file must be pure CSS.
  Source: https://help.forumotion.com/t163198-is-it-possible-for-me-to-create-a-css-page-file-to-use-it-as-reference-somewhere-in-the-forum
- External stylesheets work when the host allows them; CORS is mentioned for stylesheet hosts.
  Source: https://help.forumotion.com/t151485-multiple-css
- Classic `<script src="https://…">` is not a CORS request; module scripts are. `fetch()` to another origin needs ACAO headers.
  General web behavior (Stack Overflow / HTML Standard), plus live check: spacexygrok.github.io already returns `access-control-allow-origin: *`.

## Page size limit

About **64,000–65,000 characters** including spaces for an HTML page. Split across multiple pages if needed.
Sources: https://help.forumotion.com/t95746-html-code-too-long
https://help.forumotion.com/t154999-characters-remaining-changes-from-positive-to-negative-after-submitting-html-and-javascript-in-admin-panel
(limits thread referenced: https://help.forumotion.com/t1709-some-limits-of-forumotion-forum)

## URL pattern

`/h1-slug`, `/h2-slug`, … (number is assignment order; slug follows the title).
Example cited in help: `/h1-movies`
Source: https://help.forumotion.com/t132670-html-pages-management

## Homepage / redirect

Yes: **Use this page as homepage ?** → **Yes**.
If header/footer is No, a visible Forumotion link is required (and for homepage specifically).
Board index remains reachable at `/forum`.
Sources: https://help.forumotion.com/t151505-display-only-image-and-background-in-portal
https://help.forumotion.com/t141029-html-page-redirect
https://help.forumotion.com/t150479-html-solution-on-wii-u-solution-solved

## JS restrictions

- JS can be placed in HTML pages inside `<script>` tags (staff guidance).
  Source: https://help.forumotion.com/t145512-host-css-in-a-html-page
- Separate JS modules exist under the admin JS area; external hosting (e.g. GitHub) is a common pattern.
  Source: https://help.forumotion.com/t163895-css-files-js-files-hosting
- Do not hide Forumotion ads (ToS). Keep the required Forumotion credit link when not using header/footer.

## Admin path on this forum

Recorded earlier for dealsandfindshq: HTML pages = `modules&sub=html` under ACP.
"""
    (out_dir / "FORUMOTION-RESEARCH.md").write_text(text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_FORUM_OUT,
        help="Directory for paste-ready HTML (default: /workspace/forum-pages)",
    )
    args = ap.parse_args()
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    catalog = build_catalog()
    css = css_text()
    js = js_text()

    data_dir = PUBLIC / "data"
    assets_dir = PUBLIC / "assets"
    data_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    # Catalog for public API: flatten items without nesting full page.items duplication weight
    public_catalog = {
        "generated": catalog["generated"],
        "site_url": catalog["site_url"],
        "forum_url": catalog["forum_url"],
        "slogan": catalog["slogan"],
        "disclosure": catalog["disclosure"],
        "pages": [
            {k: v for k, v in p.items() if k != "items"}
            for p in catalog["pages"]
        ],
        "items": [
            {
                "name": it["name"],
                "slug": it["slug"],
                "page_slug": it["page_slug"],
                "page_title": it["page_title"],
                "category": it["category"],
                "store": it["store"],
                "now_price": it["now_price"],
                "now_price_high": it.get("now_price_high"),
                "old_price": it["old_price"],
                "price_raw": it["price_raw"],
                "is_range": it["is_range"],
                "savings_dollars": it["savings_dollars"],
                "savings_percent": it["savings_percent"],
                "image": it["image"],
                "image_alt": it["image_alt"],
                "link": it["link"],
                "shop_label": it["shop_label"],
                "date": it["date"],
            }
            for it in catalog["items"]
        ],
        "features": catalog["features"],
    }

    (data_dir / "catalog.json").write_text(
        json.dumps(public_catalog, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (assets_dir / "df.css").write_text(css, encoding="utf-8")
    (assets_dir / "df.js").write_text(js, encoding="utf-8")

    home = build_homepage(catalog, css, js)
    (out_dir / "01-homepage.html").write_text(home, encoding="utf-8")

    slug_to_file = {
        "top-5-computer-hardware-picks-november-2026": "02-computer-hardware.html",
        "top-10-video-game-deals-november-2026": "03-video-game-deals.html",
    }
    for page in catalog["pages"]:
        fname = slug_to_file.get(page["slug"])
        if not fname:
            fname = f"list-{page['slug']}.html"
        (out_dir / fname).write_text(build_list_page(page, css, js), encoding="utf-8")

    (out_dir / "04-asset-test.html").write_text(build_test_page(css, js), encoding="utf-8")
    write_admin_notes(out_dir, catalog)
    write_research(out_dir)

    # Sanity: char counts vs Forumotion limit
    for p in sorted(out_dir.glob("*.html")):
        n = len(p.read_text(encoding="utf-8"))
        flag = " OK" if n < 64000 else " OVER LIMIT"
        print(f"{p.name}: {n} chars{flag}")

    print(f"Wrote catalog → {data_dir / 'catalog.json'}")
    print(f"Wrote CSS/JS → {assets_dir}")
    print(f"Wrote HTML → {out_dir}")
    print(f"Pages: {len(catalog['pages'])}, items: {len(catalog['items'])}")
    top = (catalog.get("features") or {}).get("top_deal_of_week") or {}
    print(f"Top deal: {top.get('summary')}")
    soda = (catalog.get("features") or {}).get("weekly_soda") or {}
    print(f"Soda: {soda.get('status')} · {soda.get('summary')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
