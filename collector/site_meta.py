"""公開ページに共通するブランド資産と共有用メタデータ。"""
from __future__ import annotations

import html as _html
from urllib.parse import urljoin


# 公開物は out/ だけで完結する。パスを各テンプレートに重ねて書かない。
MARK_PATH = "assets/iwami-goyomi-mark.svg"
APPLE_TOUCH_ICON_PATH = "assets/apple-touch-icon.png"
OG_IMAGE_PATH = "assets/iwami-goyomi-og.png"


def public_url(site: dict, path: str = "") -> str:
    """config.yaml の公開URLを基点に、共有用の絶対URLを組み立てる。"""
    base = (site.get("url") or "").strip()
    if not base:
        return ""
    return urljoin(base if base.endswith("/") else base + "/", path)


def brand_meta(site: dict, title: str, description: str, path: str = "") -> str:
    """favicon と OGP を全公開ページで同じ定義から出す。"""
    canonical_url = public_url(site, path)
    image_url = public_url(site, OG_IMAGE_PATH)
    site_name = site.get("title") or "石見暦"

    tags = [
        f'<link rel="icon" href="{MARK_PATH}" type="image/svg+xml">',
        f'<link rel="apple-touch-icon" href="{APPLE_TOUCH_ICON_PATH}">',
        '<meta name="theme-color" content="#eae6dc">',
        '<meta property="og:type" content="website">',
        f'<meta property="og:title" content="{_html.escape(title)}">',
        f'<meta property="og:description" content="{_html.escape(description)}">',
        f'<meta property="og:site_name" content="{_html.escape(site_name)}">',
        '<meta property="og:locale" content="ja_JP">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{_html.escape(title)}">',
        f'<meta name="twitter:description" content="{_html.escape(description)}">',
    ]
    if canonical_url:
        escaped_url = _html.escape(canonical_url)
        tags.extend((
            f'<link rel="canonical" href="{escaped_url}">',
            f'<meta property="og:url" content="{escaped_url}">',
        ))
    if image_url:
        escaped_image = _html.escape(image_url)
        tags.extend((
            f'<meta property="og:image" content="{escaped_image}">',
            '<meta property="og:image:width" content="1200">',
            '<meta property="og:image:height" content="630">',
            '<meta property="og:image:type" content="image/png">',
            f'<meta name="twitter:image" content="{escaped_image}">',
        ))
    return "\n".join(tags)
