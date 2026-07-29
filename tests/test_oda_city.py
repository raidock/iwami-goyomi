"""大田市アダプターのテスト。

大田市の `/feed/` はサイト全体の目次で、掲載日を1件も持たない。
掲載日が無いと年の推定が「今日」に落ち、2月に出た「【３月７日～８日開催】
石見銀山フェスin名古屋」が翌年の2027-03-07になる（下調べで実際に踏んだ）。
そこで新着一覧HTMLから掲載日を補う。ここはその回帰テスト。

HTMLは実ページ（2026-07-30 取得）の構造をそのまま写したもの。
"""
import sys
import pathlib
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from collector.models import extract_held_date            # noqa: E402
from collector.sources.oda_city import OdaCityRSS         # noqa: E402

# 実際の /update_info/ の並び。連番と名前つきスラッグが混ざる
LIST_HTML = """
<ul class="top1-inner-ul">
  <li class="top1-inner-ul-item">
    <span class="date">2026.07.27</span>
    <span class="title"><a href="/update_info/11137">令和９年「大田市二十歳のつどい」代表者募集！</a>
    <span class="new">New</span></span>
  </li>
  <li class="top1-inner-ul-item">
    <span class="date">2026.02.16</span>
    <span class="title"><a href="/update_info/10001">【３月７日～８日開催】石見銀山フェスin名古屋</a></span>
  </li>
  <li class="top1-inner-ul-item">
    <span class="date">2026.07.02</span>
    <span class="title"><a href="/update_info/guidebook">石見銀山まるわかりガイドを作成しました！</a></span>
  </li>
  <li class="top1-inner-ul-item">
    <span class="date">2026.06.24</span>
    <span class="title"><a href="/update_info/">更新情報の一覧へ</a></span>
  </li>
</ul>
"""

# 実際の /feed/ の形。サイト全体の目次なので <pubDate> が無く、
# 固定ページ（トップ・組織案内）も同じ並びに入っている
FEED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>大田市</title><link>https://www.city.oda.lg.jp/</link>
  <item><title>トップ</title><link>https://www.city.oda.lg.jp/</link></item>
  <item><title>更新情報</title><link>https://www.city.oda.lg.jp/update_info/</link></item>
  <item><title>令和９年「大田市二十歳のつどい」代表者募集！</title>
        <link>https://www.city.oda.lg.jp/update_info/11137</link></item>
  <item><title>【３月７日～８日開催】石見銀山フェスin名古屋</title>
        <link>https://www.city.oda.lg.jp/update_info/10001</link></item>
  <item><title>石見銀山まるわかりガイドを作成しました！</title>
        <link>https://www.city.oda.lg.jp/update_info/guidebook</link></item>
</channel></rss>
"""


def _src():
    s = OdaCityRSS(key="oda_city", site="https://www.city.oda.lg.jp",
                   municipality="大田市",
                   feed_url="https://www.city.oda.lg.jp/feed/",
                   url_include=r"/update_info/.")
    s.get = lambda url: LIST_HTML if url.endswith("/update_info/") else FEED_XML
    return s


def test_publication_dates_come_from_the_listing():
    evs = {e.url: e for e in _src().collect()}
    assert len(evs) == 3, f"件数が違う: {sorted(evs)}"
    assert evs["https://www.city.oda.lg.jp/update_info/11137"].published_at \
        == date(2026, 7, 27)
    assert evs["https://www.city.oda.lg.jp/update_info/10001"].published_at \
        == date(2026, 2, 16)


def test_named_slugs_also_get_a_date():
    """URLが連番でない記事もある。数字に限定すると実データで4件漏れた。"""
    evs = {e.url: e for e in _src().collect()}
    got = evs["https://www.city.oda.lg.jp/update_info/guidebook"].published_at
    assert got == date(2026, 7, 2), got


def test_index_page_is_not_collected():
    """`url_include: '/update_info/.'` の末尾の `.` が索引ページを外す。

    末尾に1文字以上を要求することで `/update_info/` そのものを落としている。
    `.` を削ると更新情報の索引ページが催しとして流れてくる。
    """
    urls = [e.url for e in _src().collect()]
    assert "https://www.city.oda.lg.jp/update_info/" not in urls
    assert "https://www.city.oda.lg.jp/" not in urls


def test_year_does_not_slip_when_the_date_is_known():
    """掲載日があれば年が正しく決まる。無いと1年先になる（下調べで踏んだ実例）。"""
    evs = {e.url: e for e in _src().collect()}
    fes = evs["https://www.city.oda.lg.jp/update_info/10001"]
    text = f"{fes.title} {fes.description}"
    assert extract_held_date(text, fes.published_at) == date(2026, 3, 7)
    # 掲載日を渡さないと today_jst() 基準になり、7月時点では翌年に飛ぶ
    assert extract_held_date(text, date(2026, 7, 30)) == date(2027, 3, 7)


def test_missing_listing_does_not_lose_events():
    """一覧が取れなくても記事は捨てない（警告は出す）。"""
    s = _src()

    def only_feed(url):
        if url.endswith("/update_info/"):
            raise OSError("timeout")
        return FEED_XML
    s.get = only_feed
    evs = s.collect()
    assert len(evs) == 3, "一覧の失敗で記事を落とした"
    assert all(e.published_at is None for e in evs)


def test_listing_is_fetched_through_get_so_the_delay_applies():
    """一覧の取得も Source.get() 経由（大田市は Crawl-delay: 5）。"""
    s = _src()
    seen = []
    real = s.get
    s.get = lambda url: (seen.append(url), real(url))[1]
    s.collect()
    assert "https://www.city.oda.lg.jp/update_info/" in seen, seen


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
