"""公開ページの共有表示とブランド資産が欠けないためのテスト。"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from collector.about import to_about_page
from collector.publish import to_public_site


SITE = {
    "title": "石見暦",
    "url": "https://raidock.github.io/iwami-goyomi/",
    "tagline": "石見の催しと締切を、ひとつの暦に。",
}


def _assert_shared_brand(html: str, page_url: str):
    assert 'rel="icon" href="assets/iwami-goyomi-mark.svg"' in html
    assert 'rel="apple-touch-icon" href="assets/apple-touch-icon.png"' in html
    assert f'property="og:url" content="{page_url}"' in html
    assert ('property="og:image" content="https://raidock.github.io/iwami-goyomi/'
            'assets/iwami-goyomi-og.png"') in html
    assert 'name="twitter:card" content="summary_large_image"' in html


def test_home_has_brand_mark_and_shared_image_metadata():
    html = to_public_site([], site=SITE)
    _assert_shared_brand(html, SITE["url"])
    assert 'class="brand-mark"' in html


def test_about_has_page_url_and_shared_image_metadata():
    html = to_about_page(SITE, [])
    _assert_shared_brand(html, SITE["url"] + "about.html")


if __name__ == "__main__":
    import traceback

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    ok = 0
    for fn in fns:
        try:
            fn(); print(f"PASS {fn.__name__}"); ok += 1
        except Exception:
            print(f"FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{ok}/{len(fns)} passed")
    sys.exit(0 if ok == len(fns) else 1)
