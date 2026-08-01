"""フィードの窓を広げる（`?paged=N`）と、終わったものを取り込まない規則。

きっかけは浜っ子夏まつり。**フィードには窓がある。**
はまナビの event フィードは10件しか出さず、投稿が多いので約2週間分しか見えない。
記事（7/2投稿）は石見暦の初版（7/28）の時点で既に窓の外だった。

> 大きな催しほど早くから告知される。早く告知されるほど、窓から落ちる。

窓を広げると終わった催しがまとめて入る（はまナビは3ページで94件・うち74件が終了）。
そこで **初めて見るもので、もう終わっているものは取り込まない**。
"""
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from datetime import date

from collector.models import Event
from collector.review import ReviewQueue
from collector.sources.municipal_rss import MunicipalRSS

TODAY = date(2026, 8, 1)


def _ev(url="https://example.com/a", **kw):
    base = dict(title="第44回 夏まつり", prefecture="島根県", date_start=None,
                date_end=None, url=url, source="hamanavi")
    base.update({k: v for k, v in kw.items() if k in Event.__dataclass_fields__})
    e = Event(**base)
    e.review_state = kw.get("review_state", "auto")
    return e


def _queue():
    d = pathlib.Path(tempfile.mkdtemp())
    return ReviewQueue(d), d


# --- `?paged=N` の組み立て --------------------------------------------------

def test_paged_url_without_query():
    assert MunicipalRSS.paged_url(
        "https://kankou-hamada.or.jp/archives/category/event/feed/", 2) == \
        "https://kankou-hamada.or.jp/archives/category/event/feed/?paged=2"


def test_paged_url_keeps_existing_query():
    """大田市観光協会は ?post_type=events_post を持っている。消してはいけない。"""
    assert MunicipalRSS.paged_url(
        "https://www.ginzan-wm.jp/feed/?post_type=events_post", 2) == \
        "https://www.ginzan-wm.jp/feed/?post_type=events_post&paged=2"


class _FakeRSS(MunicipalRSS):
    """取得だけ差し替える。ネットには出ない。"""

    def __init__(self, pages, **kw):
        super().__init__(key="fake", site="https://example.com",
                         municipality="浜田市", feed_url="https://example.com/feed/",
                         **kw)
        self.pages = pages
        self.fetched = []

    def get(self, url):
        self.fetched.append(url)
        n = 1
        if "paged=" in url:
            n = int(url.split("paged=")[1])
        return self.pages[min(n, len(self.pages)) - 1]


def _feed(*titles):
    items = "".join(
        f"<item><title>{t}</title><link>https://example.com/{t}</link>"
        f"<pubDate>Mon, 21 Jul 2026 00:00:00 +0900</pubDate></item>" for t in titles)
    return f"<?xml version='1.0'?><rss version='2.0'><channel>{items}</channel></rss>"


def test_pages_are_concatenated():
    s = _FakeRSS([_feed("a", "b"), _feed("c", "d"), _feed("e")], feed_pages=3)
    got = [e.title for e in s.collect()]
    assert got == ["a", "b", "c", "d", "e"], got
    assert len(s.fetched) == 3


def test_default_is_one_page():
    """**既定は1ページ。** 効く情報源だけ config で増やす。"""
    s = _FakeRSS([_feed("a"), _feed("b")])
    assert [e.title for e in s.collect()] == ["a"]
    assert len(s.fetched) == 1


def test_stops_when_the_cms_ignores_paged():
    """自治体3市は paged を解さず、同じ内容を返す（2026-08-01 実測）。

    気づかずに回すと同じページを何度も叩くだけになる（設計判断12）。
    """
    same = _feed("a", "b")
    s = _FakeRSS([same, same, same], feed_pages=3)
    assert [e.title for e in s.collect()] == ["a", "b"]
    assert len(s.fetched) == 2, f"打ち切っていない（{len(s.fetched)}回叩いた）"


def test_stops_on_empty_page():
    s = _FakeRSS([_feed("a"), _feed()], feed_pages=3)
    assert [e.title for e in s.collect()] == ["a"]
    assert len(s.fetched) == 2


# --- 情報源ごとの掲載日の足切り --------------------------------------------
# **繰り返しの催しは記事を作り直さない。** 毎週の天体観察会（2024-05 投稿）や
# 毎月の朝市は掲載日が何年も前のままで、既定の400日だと落ちる。
# 全体を伸ばすと浜田市の公式RSSに残っていた2022年のコロナ情報まで拾うので、
# **イベント専用のフィードにだけ**書く。

def _dated_feed(*pairs):
    items = "".join(
        f"<item><title>{t}</title><link>https://example.com/{t}</link>"
        f"<pubDate>{d}</pubDate></item>" for t, d in pairs)
    return f"<?xml version='1.0'?><rss version='2.0'><channel>{items}</channel></rss>"


_OLD = _dated_feed(("新しい記事", "Mon, 21 Jul 2026 00:00:00 +0900"),
                   ("毎週の天体観察会", "Thu, 02 May 2024 00:00:00 +0900"))


def test_default_cuts_off_the_old_article():
    s = _FakeRSS([_OLD])
    assert [e.title for e in s.collect()] == ["新しい記事"]


def test_per_source_max_age_keeps_it():
    s = _FakeRSS([_OLD], max_age_days=1200)
    got = [e.title for e in s.collect()]
    assert got == ["新しい記事", "毎週の天体観察会"], got


def test_config_reaches_the_adapter():
    """config.yaml の1行が実際にアダプターへ届くこと（配線の回帰）。"""
    import main
    cfg = {"municipalities": [], "tourism": [
        {"key": "a", "municipality": "大田市", "site": "https://example.com",
         "max_age_days": 1200},
        {"key": "b", "municipality": "浜田市", "site": "https://example.com"},
    ], "max_age_days": 400}
    got = {src.name: src.max_age_days for src, _ in main.build_sources(cfg)}
    assert got == {"a": 1200, "b": 400}, got


# --- 終わったものを取り込まない ---------------------------------------------

def test_finished_new_item_is_not_ingested():
    q, d = _queue()
    try:
        stats = q.ingest([_ev(date_start=date(2026, 6, 13))], today=TODAY)
        assert stats["finished"] == 1, stats
        assert len(q.approved) == 0 and len(q.pending) == 0
    finally:
        shutil.rmtree(d)


def test_upcoming_item_is_kept():
    q, d = _queue()
    try:
        q.ingest([_ev(date_start=date(2026, 8, 1))], today=TODAY)   # 本日開催
        assert len(q.approved) == 1
    finally:
        shutil.rmtree(d)


def test_no_date_is_never_treated_as_finished():
    """**日付が分からないものは勝手に捨てない**（設計判断4）。"""
    q, d = _queue()
    try:
        q.ingest([_ev()], today=TODAY)
        assert len(q.approved) == 1, "日付なしが捨てられた"
    finally:
        shutil.rmtree(d)


def test_period_is_judged_by_the_end():
    """期間ものは終わりの日で見る。開始が過去でも会期中なら取り込む。"""
    q, d = _queue()
    try:
        q.ingest([_ev(date_start=date(2026, 6, 6), date_end=date(2026, 12, 27))],
                 today=TODAY)
        assert len(q.approved) == 1, "会期中の企画展が捨てられた"
    finally:
        shutil.rmtree(d)


def test_past_deadline_with_future_date_is_kept():
    """申込は締切っても、催し自体はこれからある。"""
    q, d = _queue()
    try:
        q.ingest([_ev(date_start=date(2026, 8, 23), deadline=date(2026, 7, 20))],
                 today=TODAY)
        assert len(q.approved) == 1, "締切だけを見て捨てている"
    finally:
        shutil.rmtree(d)


def test_past_deadline_only_is_dropped():
    """締切しか無く、それが過ぎているなら終わり（募集）。"""
    q, d = _queue()
    try:
        stats = q.ingest([_ev(deadline=date(2026, 7, 20))], today=TODAY)
        assert stats["finished"] == 1 and len(q.pending) == 0
    finally:
        shutil.rmtree(d)


def test_known_item_is_not_dropped_when_it_ends():
    """**一度載ったものは畳んで残す**（設計判断4）。既知には適用しない。"""
    q, d = _queue()
    try:
        q.ingest([_ev(date_start=date(2026, 9, 1))], today=TODAY)
        assert len(q.approved) == 1
        # 次の収集では開催日が過去に変わった（同じURL＝既知）
        stats = q.ingest([_ev(date_start=date(2026, 7, 1))], today=TODAY)
        assert stats["finished"] == 0, "既知にも適用してしまっている"
        assert len(q.approved) == 1, "公開中のものが消えた"
        assert q.approved[0].date_start == date(2026, 7, 1)
    finally:
        shutil.rmtree(d)


def test_rejected_item_stays_rejected_not_finished():
    """却下済みは既知。終了判定より先に既知の枝へ入る。"""
    q, d = _queue()
    try:
        e = _ev(review_state="review")
        q.ingest([e], today=TODAY)
        q.decide(q.pending[0].uid, approve=False)
        stats = q.ingest([_ev(date_start=date(2026, 6, 13))], today=TODAY)
        assert stats["finished"] == 0
        assert len(q.rejected) == 1
    finally:
        shutil.rmtree(d)


def test_is_finished_does_not_replace_is_past():
    """publish.is_past とは基準が違う。混ぜないための覚え書き。"""
    from collector.publish import is_past
    seido = _ev(kind="制度")
    seido.kind = "制度"
    seido.deadline = date(2026, 7, 1)
    # 画面では制度は常に現役。取り込みでは「分かっている日付が全部過去」で終わり
    assert is_past(seido, TODAY) is False
    assert ReviewQueue.is_finished(seido, TODAY) is True


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
