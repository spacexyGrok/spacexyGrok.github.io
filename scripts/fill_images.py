#!/usr/bin/env python3
"""Fill missing product images in telegraph-pages/lists/*.md from retailer pages.

For each ### product block without a markdown image, resolve the retailer URL
(following amzlink / earn.linktr.ee redirects when needed), fetch the product
page, and extract og:image / twitter:image / JSON-LD Product.image (with
site-specific fallbacks that still come from the product page). Write:

  ![alt](https://...)

in the same format as the Son list. Never invent stock or AI images.

Usage:
  python3 scripts/fill_images.py
  python3 scripts/fill_images.py --dry-run
  python3 scripts/fill_images.py --src ../telegraph-pages/lists --only coffee

After filling, re-run list_to_grid.py then npm run build.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)

IMG_RE = re.compile(r"!\[([^\]]*)\]\((https?://[^)]+)\)")
FIELD_RE = re.compile(
    r"^\*\*(URL|Alt|Shop[^:]*|Tracked[^:]*):\*\*\s*(.+)$",
    re.MULTILINE | re.IGNORECASE,
)
SHOP_MD_RE = re.compile(r"\[Shop\]\((https?://[^)]+)\)")
SKIP_NAMES = {
    "quick budget map",
    "everyday high-interest stores",
    "holiday big deal reveal spotlight",
    "terms note (what we follow)",
    "how the welcome bonus works",
}

LOGO_HINTS = (
    "logo",
    "og-image-logo",
    "sephora_logo",
    "loading-scren",
    "loading-screen",
    "placeholder",
    "sprite",
    "favicon",
    "default_og",
    "facebook-share",
)

# Category / search / hub pages — not a single product PDP
NON_PDP_HINTS = (
    "/s?",
    "/c/",
    "/collections/",
    "/shop/gifts",
    "/shop/us/mens-",
    "/shop/us/womens-",
    "searchTerm=",
    "/women-shoes",
    "/men-shoes",
    "tab=shop",
    "linktr.ee/chadd",
)

# Path patterns that look like search hubs (not Nordstrom PDP /s/name/id)
SEARCH_PATH_RE = re.compile(r"/s(?:earch)?(?:/|$|\?)", re.I)

CTX = ssl.create_default_context()


def http_get(url: str, ua: str = UA_DESKTOP, timeout: int = 25) -> tuple[int, str, str]:
    """Return (status, final_url, body_text). Body may be empty on error."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as resp:
            raw = resp.read()
            # handle gzip if urllib didn't
            if raw[:2] == b"\x1f\x8b":
                import gzip

                raw = gzip.decompress(raw)
            charset = "utf-8"
            ctype = resp.headers.get("Content-Type", "")
            if "charset=" in ctype.lower():
                charset = ctype.split("charset=")[-1].split(";")[0].strip() or "utf-8"
            return resp.status, resp.geturl(), raw.decode(charset, "replace")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        return e.code, url, body
    except Exception as e:
        return 0, url, f"__ERR__{type(e).__name__}:{e}"


def head_ok_image(url: str) -> bool:
    """HTTP 200 and image/* content-type (GET with Range if needed)."""
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "User-Agent": UA_DESKTOP,
            "Range": "bytes=0-1023",
            "Accept": "image/*,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20, context=CTX) as resp:
            code = resp.status
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if code not in (200, 206):
                return False
            if ctype.startswith("image/"):
                return True
            # some CDNs omit type on Range; sniff magic
            chunk = resp.read(16)
            if chunk.startswith(b"\xff\xd8\xff") or chunk.startswith(b"\x89PNG"):
                return True
            if chunk[:4] == b"RIFF" or chunk.startswith(b"GIF8"):
                return True
            if b"webp" in chunk[:16].lower():
                return True
            return False
    except Exception:
        return False


def looks_like_logo(url: str) -> bool:
    low = url.lower()
    return any(h in low for h in LOGO_HINTS)


def is_non_pdp(url: str) -> bool:
    low = url.lower()
    if "linktr.ee/chadd" in low and "earn.linktr" not in low:
        return True
    parsed = urllib.parse.urlparse(url)
    if parsed.path in ("", "/"):
        return True
    # Amazon/Target-style search query pages
    if "amazon." in parsed.netloc and ("/s?" in low or parsed.path.rstrip("/") == "/s"):
        return False  # handled by amazon-search resolver
    if "searchterm=" in low or "st=" in urllib.parse.parse_qs(parsed.query):
        if "bestbuy.com" in low or "target.com" in low:
            return True
    # Nordstrom /s/name/id is a PDP — allow
    if "nordstrom.com" in low and re.search(r"/s/[^/]+/\d+", low):
        return False
    for h in NON_PDP_HINTS:
        if h in low:
            return True
    return False


def decode_earn_linktree(url: str) -> str | None:
    """Extract destination retailer URL from earn.linktr.ee/clicks/v2?b64=..."""
    try:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        b64 = qs.get("b64", [None])[0]
        if not b64:
            return None
        pad = "=" * (-len(b64) % 4)
        data = json.loads(base64.urlsafe_b64decode(b64 + pad))
        inner = data.get("url") or ""
        # Impact/adidas wrap often has u= final product URL
        inner_qs = urllib.parse.parse_qs(urllib.parse.urlparse(inner).query)
        if "u" in inner_qs:
            return urllib.parse.unquote(inner_qs["u"][0])
        # Or path may already be the product
        if "adidas.com" in inner or "http" in inner:
            # sometimes url field is the nji redirect with u=
            m = re.search(r"[?&]u=(https?[^&]+)", inner)
            if m:
                return urllib.parse.unquote(m.group(1))
            if inner.startswith("http") and "nji" not in inner:
                return inner
        return None
    except Exception:
        return None


def unwrap_amzlink(url: str) -> str | None:
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    btn = qs.get("btn_url", [None])[0]
    if btn:
        return urllib.parse.unquote(btn)
    return None


def amazon_asin(url: str) -> str | None:
    m = re.search(r"/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})", url, re.I)
    if m:
        return m.group(1).upper()
    m = re.search(r"[?&]asin=([A-Z0-9]{10})", url, re.I)
    return m.group(1).upper() if m else None


def sephora_product_id(url: str) -> str | None:
    m = re.search(r"(P\d{5,})", url, re.I)
    return m.group(1).upper() if m else None


def extract_meta_images(html: str) -> list[str]:
    """og:image, twitter:image, JSON-LD Product.image — in priority order."""
    found: list[str] = []

    patterns = [
        r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image(?::secure_url)?["\']',
        r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image(?::src)?["\']',
    ]
    for pat in patterns:
        for m in re.finditer(pat, html, re.I):
            u = html_unescape(m.group(1).strip())
            if u.startswith("//"):
                u = "https:" + u
            if u.startswith("http") and u not in found:
                found.append(u)

    # JSON-LD
    for m in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.I | re.S,
    ):
        raw = m.group(1).strip()
        try:
            data = json.loads(raw)
        except Exception:
            continue
        for img in iter_ld_images(data):
            if img not in found:
                found.append(img)

    return found


def iter_ld_images(data) -> list[str]:
    out: list[str] = []

    def add(val):
        if isinstance(val, str) and val.startswith("http"):
            out.append(val)
        elif isinstance(val, list):
            for x in val:
                add(x)
        elif isinstance(val, dict):
            if "url" in val:
                add(val["url"])

    def walk(obj):
        if isinstance(obj, dict):
            t = obj.get("@type")
            types = t if isinstance(t, list) else [t] if t else []
            types_l = [str(x).lower() for x in types]
            if any("product" in x for x in types_l) or "image" in obj:
                if "image" in obj:
                    add(obj["image"])
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for x in obj:
                walk(x)

    walk(data)
    return out


def html_unescape(s: str) -> str:
    return (
        s.replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )


def amazon_page_images(html: str) -> list[str]:
    """Product images embedded in Amazon mobile/desktop HTML (from the PDP)."""
    scored: list[tuple[int, str]] = []
    for m in re.finditer(
        r"(https://m\.media-amazon\.com/images/I/[A-Za-z0-9+\-_]+)\.(_AC_[^\"'\s>]+\.)?jpe?g",
        html,
        re.I,
    ):
        base = m.group(1)
        # Prefer large SL variants matching Son list style
        url = base + "._AC_SL1000_.jpg"
        score = 2
        full = m.group(0)
        if "SL1500" in full or "SL1000" in full:
            url = full if full.startswith("http") else url
            score = 3
        elif "UF" in full:
            score = 1
        scored.append((score, url))
    # unique preserving best score
    best: dict[str, tuple[int, str]] = {}
    for score, url in scored:
        # key by image id
        mid = re.search(r"/I/([^.]+)", url)
        key = mid.group(1).split("._")[0] if mid else url
        if key not in best or score > best[key][0]:
            best[key] = (score, url)
    # order by score desc; first is usually main hero among early matches
    # Prefer appearance order of first SL1500 in HTML
    first_sl = re.search(
        r"https://m\.media-amazon\.com/images/I/[A-Za-z0-9+\-_]+._AC_SL(?:1000|1500)_.jpg",
        html,
    )
    ordered = []
    if first_sl:
        ordered.append(first_sl.group(0).replace("_AC_SL1500_", "_AC_SL1000_"))
    for score, url in sorted(best.values(), key=lambda x: -x[0]):
        if url not in ordered:
            ordered.append(url)
    return ordered


def sephora_api_image(product_id: str) -> str | None:
    api = f"https://api.sephora.com/v3/catalog/products/{product_id}"
    code, _, body = http_get(api, ua=UA_DESKTOP)
    if code != 200 or not body.strip().startswith("{"):
        return None
    try:
        data = json.loads(body)
    except Exception:
        return None
    sku = data.get("currentSku") or {}
    imgs = sku.get("skuImages") or {}
    for key in ("imageUrl", "image450", "image250"):
        u = imgs.get(key)
        if u and u.startswith("http") and not looks_like_logo(u):
            return u
    return None


def pick_image(candidates: list[str]) -> str | None:
    for u in candidates:
        if not u or not u.startswith("http"):
            continue
        if looks_like_logo(u):
            continue
        # normalize
        u = html_unescape(u.split("?")[0] + (("?" + u.split("?", 1)[1]) if "?" in u else ""))
        if head_ok_image(u):
            return u
    return None


def resolve_fetch_url(fields: dict[str, str]) -> str | None:
    """Pick the best retailer URL to fetch images from."""
    candidates = []
    for key in ("url", "alt", "tracked", "shop", "shop_md"):
        if fields.get(key):
            candidates.append(fields[key])
    resolved = []
    for u in candidates:
        if "r.amzlink.to" in u or "amzlink.to" in u:
            inner = unwrap_amzlink(u)
            if inner:
                resolved.append(inner)
                continue
        if "earn.linktr.ee" in u:
            inner = decode_earn_linktree(u)
            if inner:
                resolved.append(inner)
                continue
        resolved.append(u)

    # Prefer known PDPs over linktree / search
    def score(u: str) -> int:
        if is_non_pdp(u):
            return -10
        host = urllib.parse.urlparse(u).netloc.lower()
        s = 0
        if "amazon." in host:
            s += 5
        if "/dp/" in u or "/gp/" in u:
            s += 3
        if "/product/" in u or "/products/" in u or "/p/" in u:
            s += 3
        if "sephora." in host or "target." in host or "adidas." in host:
            s += 2
        return s

    resolved = sorted(set(resolved), key=score, reverse=True)
    return resolved[0] if resolved else None



def first_asin_from_amazon_search(search_url: str) -> str | None:
    """Follow an Amazon search URL and return the first organic product ASIN.

    The image is later fetched from that ASIN's product page (not invented).
    """
    for ua in (UA_MOBILE, UA_DESKTOP):
        code, _, html = http_get(search_url, ua=ua)
        if code != 200 or len(html) < 1000:
            time.sleep(0.6)
            continue
        if "captcha" in html.lower()[:3000]:
            time.sleep(1.0)
            continue
        for m in re.finditer(r'data-asin="([A-Z0-9]{10})"', html):
            asin = m.group(1)
            if asin and asin != "0000000000":
                return asin
        for m in re.finditer(r"/dp/([A-Z0-9]{10})", html):
            return m.group(1)
        time.sleep(0.5)
    return None


def fetch_product_image(url: str, cache: dict[str, str]) -> tuple[str | None, str]:
    """Return (image_url_or_None, reason)."""
    if (
        url in cache
        and "linktr.ee/chadd" not in url
        and not url.rstrip("/").endswith("barkbox.com")
    ):
        # Trust cache entries (including amazon search→PDP resolutions we seeded)
        return cache[url], "cache"

    # Amazon search → first result PDP (image still taken from that product page)
    if "amazon." in url and ("/s?" in url or "/s/" in url):
        asin = first_asin_from_amazon_search(url)
        if asin:
            return fetch_product_image(f"https://www.amazon.com/dp/{asin}", cache)
        return None, "amazon-search-no-asin"

    if is_non_pdp(url):
        return None, "non-pdp-url"

    # Sephora API (HTML often 403)
    sid = sephora_product_id(url)
    if sid and "sephora.com" in url:
        img = sephora_api_image(sid)
        if img and head_ok_image(img):
            cache[url] = img
            return img, "sephora-api"

    # Amazon mobile PDP
    asin = amazon_asin(url)
    if asin and ("amazon." in url or "amzn." in url or "amazon.com" in url):
        mobile = f"https://www.amazon.com/gp/aw/d/{asin}"
        code, _, html = http_get(mobile, ua=UA_MOBILE)
        if code == 200 and "captcha" not in html.lower()[:3000]:
            cands = extract_meta_images(html) + amazon_page_images(html)
            img = pick_image(cands)
            if img:
                cache[url] = img
                return img, "amazon-mobile"
        return None, "amazon-fetch-failed"

    # Generic HTML fetch
    code, final, html = http_get(url, ua=UA_DESKTOP)
    if code == 403:
        code, final, html = http_get(url, ua=UA_MOBILE)
    if code != 200 or html.startswith("__ERR__") or len(html) < 500:
        return None, f"http-{code}"

    if "captcha" in html.lower()[:4000] or "validatecaptcha" in html.lower():
        return None, "captcha"

    cands = extract_meta_images(html)
    # Amazon-shaped pages
    if "media-amazon.com" in html:
        cands = cands + amazon_page_images(html)

    img = pick_image(cands)
    if img:
        cache[url] = img
        return img, "html-meta"
    return None, "no-image-meta"


def parse_heading_name(first_line: str) -> str:
    name = re.sub(r"^###\s+(?:Bonus[^:]*:\s+)?(?:\d+\.\s+)?", "", first_line.strip())
    # Only split price on em/en dash — ASCII hyphen appears in product names
    name = re.sub(r"\s*[—–]\s*.+$", "", name).strip()
    return name


def fields_from_block(block: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for fm in FIELD_RE.finditer(block):
        key = fm.group(1).strip().lower()
        if key.startswith("shop"):
            key = "shop"
        elif key.startswith("tracked"):
            key = "tracked"
        fields[key] = fm.group(2).strip()
    m = SHOP_MD_RE.search(block)
    if m:
        fields["shop_md"] = m.group(1)
    return fields


def insert_image(block: str, alt: str, image_url: str) -> str:
    """Insert ![alt](url) after the heading line (Son format)."""
    lines = block.splitlines(keepends=True)
    if not lines:
        return block
    # heading is first line
    out = [lines[0]]
    # ensure blank line then image then blank line
    rest = "".join(lines[1:])
    # drop leading blank lines before inserting
    rest_stripped = rest.lstrip("\n")
    out.append("\n")
    out.append(f"![{alt}]({image_url})\n")
    out.append("\n")
    out.append(rest_stripped)
    return "".join(out)


def process_file(
    path: Path,
    cache: dict[str, str],
    dry_run: bool,
    delay: float,
) -> dict:
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"(?=^### )", text, flags=re.MULTILINE)
    preamble = parts[0] if parts and not parts[0].strip().startswith("###") else ""
    blocks = [p for p in parts if p.strip().startswith("###")]

    filled = 0
    skipped_has = 0
    missing: list[str] = []
    new_blocks: list[str] = []

    for block in blocks:
        first = block.strip().splitlines()[0]
        name = parse_heading_name(first)
        low = name.lower()
        if low.startswith("post ") or low in SKIP_NAMES or "stretch gift" in low:
            new_blocks.append(block)
            continue
        if low.startswith("needs-add") or low.startswith("needs:") or "needs-add" in low:
            # Placeholder SKUs — leave blank until a real PDP URL exists
            missing.append(f"{name} [needs-add-placeholder]")
            new_blocks.append(block)
            continue
        if IMG_RE.search(block):
            skipped_has += 1
            new_blocks.append(block)
            continue

        fields = fields_from_block(block)
        url = resolve_fetch_url(fields)
        if not url:
            missing.append(f"{name} (no URL)")
            new_blocks.append(block)
            continue

        img, reason = fetch_product_image(url, cache)
        time.sleep(delay)
        if not img:
            missing.append(f"{name} [{reason}] {url[:90]}")
            new_blocks.append(block)
            continue

        alt = re.sub(r"\s+", " ", name)[:80]
        if dry_run:
            print(f"  DRY {name[:50]} -> {img[:90]} ({reason})")
        else:
            block = insert_image(block, alt, img)
            print(f"  OK  {name[:50]} -> {img[:90]} ({reason})")
        filled += 1
        new_blocks.append(block)

    if not dry_run and filled:
        path.write_text(preamble + "".join(new_blocks), encoding="utf-8")

    return {
        "file": path.name,
        "filled": filled,
        "already": skipped_has,
        "missing": missing,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--src",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "telegraph-pages" / "lists",
    )
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", help="Substring filter on filename")
    ap.add_argument("--delay", type=float, default=0.4)
    ap.add_argument(
        "--cache",
        type=Path,
        default=Path(__file__).resolve().parent / "image_url_cache.json",
        help="Persistent URL->image cache (also seed hard sites here)",
    )
    ap.add_argument(
        "--skip-son",
        action="store_true",
        default=True,
        help="Skip the Son list (already has images)",
    )
    args = ap.parse_args()

    cache: dict[str, str] = {}
    if args.cache.exists():
        try:
            cache = json.loads(args.cache.read_text())
        except Exception:
            cache = {}

    # Built-in seeds from known retailer PDPs (real page images)
    seeds = {
        "https://www.adidas.com/us/unisex-trefoil-beanie/JL1080.html": (
            "https://assets.adidas.com/images/h_840,f_auto,q_auto,fl_lossy,c_fill,g_auto/"
            "77a8b4fd403549e19a257b72131b2c61_9366/Unisex_Trefoil_Beanie_Black_JL1080_01_standard.jpg"
        ),
        "https://www.adidas.com/us/unisex-originals-comfort-2.0-3-pack-crew/KL3579.html": (
            "https://assets.adidas.com/images/h_840,f_auto,q_auto,fl_lossy,c_fill,g_auto/"
            "3d8b9a240b8845ce8106e85f07dbcfd5_9366/Unisex_Originals_Comfort_2.0_3-Pack_Crew_Grey_KL3579_01_standard.jpg"
        ),
    }
    for k, v in seeds.items():
        cache.setdefault(k, v)

    results = []
    files = sorted(args.src.glob("*.md"))
    for path in files:
        if args.only and args.only.lower() not in path.name.lower():
            continue
        if args.skip_son and "your-son" in path.name:
            print(f"SKIP {path.name} (son list)")
            continue
        if path.name.startswith("rakuten"):
            print(f"SKIP {path.name} (not product grid)")
            continue
        print(f"=== {path.name}")
        results.append(process_file(path, cache, args.dry_run, args.delay))

    if not args.dry_run:
        args.cache.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")

    print("\n===== SUMMARY =====")
    total_filled = 0
    all_missing: list[str] = []
    for r in results:
        total_filled += r["filled"]
        print(f"{r['file']}: filled {r['filled']}, already had image {r['already']}, still missing {len(r['missing'])}")
        for m in r["missing"]:
            print(f"  MISSING: {m}")
            all_missing.append(f"{r['file']}: {m}")

    report = {
        "filled_total": total_filled,
        "per_list": {r["file"]: {"filled": r["filled"], "missing": r["missing"]} for r in results},
    }
    report_path = Path(__file__).resolve().parent / "fill_images_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nTotal filled: {total_filled}")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
