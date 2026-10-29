#!/usr/bin/env python3
"""Convert telegraph-pages/lists/*.md into JSON for Astro /gifts/ grid pages.

Usage:
  python3 scripts/list_to_grid.py
  python3 scripts/list_to_grid.py --src ../telegraph-pages/lists --out src/data/gifts

LOCAL ONLY — does not commit, push, or publish.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

HEADING_RE = re.compile(
    r"^###\s+(?:Bonus\s+under-\$\d+:\s+)?(?:\d+\.\s+)?(.+?)\s*—\s*(~?\$?.+)$",
    re.MULTILINE,
)
IMG_RE = re.compile(r"!\[([^\]]*)\]\((https?://[^)]+)\)")
SHOP_RE = re.compile(r"\[Shop\]\((https?://[^)]+)\)")
PRICE_NOTE_RE = re.compile(r"^\*\*(~?\$[^*]+)\*\*\s*[—–-]\s*(.+)$", re.MULTILINE)
FIELD_RE = re.compile(
    r"^\*\*(Retailer|Why|URL|Alt|Shop \(raw card[^*]*\)):\*\*\s*(.+)$",
    re.MULTILINE | re.IGNORECASE,
)
TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def slug_from_stem(stem: str) -> str:
    return stem.strip().lower()


def split_blocks(text: str) -> list[str]:
    """Split on ### headings; keep heading line with its body."""
    parts = re.split(r"(?=^### )", text, flags=re.MULTILINE)
    return [p for p in parts if p.strip().startswith("###")]


def parse_heading(line: str) -> tuple[str, str] | None:
    m = HEADING_RE.match(line.strip())
    if not m:
        # Fallback: ### N. Name without em-dash price
        m2 = re.match(r"^###\s+(?:Bonus[^:]*:\s+)?(?:\d+\.\s+)?(.+)$", line.strip())
        if not m2:
            return None
        name = m2.group(1).strip()
        # Try trailing price in name
        pm = re.search(r"\s*[—–-]\s*(~?\$?.+)$", name)
        if pm:
            price = pm.group(1).strip()
            name = name[: pm.start()].strip()
            return name, price
        return name, ""
    return m.group(1).strip(), m.group(2).strip()


def parse_product_block(block: str) -> dict | None:
    lines = block.strip().splitlines()
    if not lines:
        return None
    parsed = parse_heading(lines[0])
    if not parsed:
        return None
    name, price = parsed
    body = "\n".join(lines[1:])

    image = None
    image_alt = name
    img = IMG_RE.search(body)
    if img:
        image_alt = img.group(1) or name
        image = img.group(2)

    url = None
    shop = SHOP_RE.search(body)
    if shop:
        url = shop.group(1)

    note = ""
    pn = PRICE_NOTE_RE.search(body)
    if pn:
        # Prefer price from bold line if heading price empty/odd
        if pn.group(1).strip():
            price = pn.group(1).strip()
        note = pn.group(2).strip()

    fields: dict[str, str] = {}
    for fm in FIELD_RE.finditer(body):
        key = fm.group(1).strip().lower()
        if key.startswith("shop"):
            key = "shop"
        fields[key] = fm.group(2).strip()

    if not note and fields.get("why"):
        note = fields["why"]
    if not url and fields.get("url"):
        url = fields["url"]
    if not url and fields.get("shop"):
        url = fields["shop"]
    if not url and fields.get("alt"):
        url = fields["alt"]

    retailer = fields.get("retailer", "")

    # Skip non-product section headings (e.g. Quick budget map, social posts)
    skip_names = {
        "quick budget map",
        "everyday high-interest stores",
        "holiday big deal reveal spotlight",
        "post a — x / short",
        "post b — instagram / carousel caption",
        "post c — tiktok / reel script (~20s)",
        "terms note (what we follow)",
        "how the welcome bonus works",
    }
    low = name.lower()
    if low.startswith("post ") or low in skip_names:
        return None
    if low.startswith("everyday ") or low.startswith("holiday big"):
        return None
    if "terms note" in low or "how the welcome" in low:
        return None
    if low.startswith("stretch gift") or low.startswith("optional stretch"):
        return None

    if not url and not note and not image:
        # Likely a section heading without product fields
        if not price:
            return None

    return {
        "name": name,
        "price": price,
        "note": note,
        "image": image,
        "imageAlt": image_alt,
        "url": url or "https://linktr.ee/chadd990?tab=shop",
        "retailer": retailer,
    }


def intro_and_disclosure(text: str) -> tuple[str, str]:
    """Extract disclosure paragraph and short intro before first ###."""
    pre = text.split("###", 1)[0]
    disclosure = ""
    intro_lines: list[str] = []
    for line in pre.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("---"):
            continue
        if "affiliate disclosure" in s.lower() or "referral disclosure" in s.lower():
            disclosure = re.sub(r"^\*\*[^:]+:\*\*\s*", "", s)
            continue
        if s.startswith("**Shop:**") or s.startswith("**CTA:**"):
            continue
        if s.startswith("|") or s.startswith("Per ["):
            continue
        intro_lines.append(s)
    intro = " ".join(intro_lines).strip()
    # Keep intro reasonably short for meta
    if len(intro) > 320:
        intro = intro[:317].rsplit(" ", 1)[0] + "…"
    return disclosure, intro


def meta_description(title: str, intro: str, products: list[dict]) -> str:
    if intro:
        base = intro
    elif products:
        names = ", ".join(p["name"] for p in products[:3])
        base = f"{title}: {names}, and more."
    else:
        base = f"{title} — curated deals with affiliate disclosure."
    if len(base) > 158:
        base = base[:155].rsplit(" ", 1)[0] + "…"
    return base


def parse_list_file(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    tm = TITLE_RE.search(text)
    if not tm:
        return None
    title = tm.group(1).strip()
    slug = slug_from_stem(path.stem)

    # Rakuten page is special: treat as single CTA card list from referral CTAs
    if slug == "rakuten-trending-deals":
        disclosure, intro = intro_and_disclosure(text)
        products = [
            {
                "name": "Join Rakuten (Refer-A-Friend)",
                "price": "$50 referrer bonus*",
                "note": "Sign up via this owned-page referral link, then shop through Rakuten for Cash Back. Qualifying spend rules apply; confirm live terms.",
                "image": None,
                "imageAlt": "Rakuten",
                "url": "https://www.rakuten.com/r/VIETNA290?eeid=28187",
                "retailer": "Rakuten",
            }
        ]
        # Pull a few store names as text-only cards if present
        for m in re.finditer(r"^\*\*([^*]+)\*\*\s*[—–-]\s*(.+)$", text, re.MULTILINE):
            store = m.group(1).strip()
            blurb = m.group(2).strip()
            if store.lower().startswith("how ") or "referral" in store.lower():
                continue
            if len(products) >= 8:
                break
            products.append(
                {
                    "name": store,
                    "price": "via Rakuten",
                    "note": blurb[:180],
                    "image": None,
                    "imageAlt": store,
                    "url": "https://www.rakuten.com/r/VIETNA290?eeid=28187",
                    "retailer": "Rakuten",
                }
            )
        return {
            "slug": slug,
            "title": title,
            "description": meta_description(title, intro, products),
            "intro": intro
            or "Rakuten Cash Back referral page for owned channels only.",
            "disclosure": disclosure
            or "This page uses a Rakuten Refer-A-Friend link. I may earn a referral bonus if you join and complete qualifying spend.",
            "products": products,
            "ogImage": None,
            "source": path.name,
            "kind": "rakuten",
        }

    products: list[dict] = []
    for block in split_blocks(text):
        # Stop at Quick budget / footer style sections that aren't products
        first = block.splitlines()[0]
        if re.match(r"^###\s+Quick\b", first, re.I):
            break
        prod = parse_product_block(block)
        if prod:
            products.append(prod)

    disclosure, intro = intro_and_disclosure(text)
    og = next((p["image"] for p in products if p.get("image")), None)

    return {
        "slug": slug,
        "title": title,
        "description": meta_description(title, intro, products),
        "intro": intro
        or f"Curated gift and deal picks: {title}.",
        "disclosure": disclosure
        or "Some links are affiliate / partner links. If you buy through them, I may earn a commission at no extra cost to you. As an Amazon Associate I earn from qualifying purchases.",
        "products": products,
        "ogImage": og,
        "source": path.name,
        "kind": "gift-list",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--src",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "telegraph-pages" / "lists",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "src" / "data" / "gifts",
    )
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    index: list[dict] = []
    files = sorted(args.src.glob("*.md"))
    if not files:
        print(f"ERROR: no markdown lists in {args.src}", flush=True)
        return 1

    for path in files:
        data = parse_list_file(path)
        if not data:
            print(f"SKIP (no title): {path.name}")
            continue
        out_path = args.out / f"{data['slug']}.json"
        out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tile_image = data.get("ogImage")
        index.append(
            {
                "slug": data["slug"],
                "title": data["title"],
                "description": data["description"],
                "productCount": len(data["products"]),
                "image": tile_image,
                "kind": data["kind"],
            }
        )
        print(f"OK {path.name} → {out_path.name} ({len(data['products'])} products)")

    index_path = args.out / "index.json"
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote index: {index_path} ({len(index)} lists)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
