"""【92】audit --check-links のテスト。

2026-08-07、益田市の記事が404になっていたのを見つけたのがきっかけ。
その後の測定で、江津市・津和野町観光協会あわせて6件、さらに手動掲載
（吉賀町）も1件404だったことが分かった。**手動掲載は自動収集の対象外なので、
これまで気づく手段が一つも無かった。** approved.json と manual.json の
両方を対象にするのはそのため。

守ることは4つ:
  1. 404のURLが一覧に出ること
  2. **自動では却下しないこと**（設計判断3。一覧に出すだけ）
  3. manual.json のURLも対象になること
  4. 情報源ごとの間隔（fetch_delay_for）が守られること
"""
import json
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import collector.sources.base as base                      # noqa: E402
from collector.review import ReviewQueue                    # noqa: E402
from main import find_broken_links                          # noqa: E402

CFG = {
    "fetch_delay_sec": 1.0,
    "municipalities": [
        {"key": "masuda_city", "municipality": "益田市",
         "site": "https://www.city.masuda.lg.jp"},
        # robots.txt の Crawl-delay: 5 を宣言している想定
        {"key": "oda_city", "municipality": "大田市",
         "site": "https://www.city.oda.lg.jp", "fetch_delay_sec": 5},
    ],
    "tourism": [],
}

APPROVED_ALIVE = {
    "title": "生きているページ", "prefecture": "島根県", "url": "https://www.city.masuda.lg.jp/a",
    "source": "masuda_city", "city": "益田市", "review_state": "approved",
}
APPROVED_DEAD = {
    "title": "消えたページ", "prefecture": "島根県", "url": "https://www.city.masuda.lg.jp/dead",
    "source": "masuda_city", "city": "益田市", "review_state": "approved",
}
MANUAL_DEAD = {
    "title": "手動掲載の消えたページ", "url": "https://www.town.yoshika.lg.jp/dead",
    "city": "吉賀町",
}


def _dir(approved=None, manual=None):
    d = pathlib.Path(tempfile.mkdtemp())
    if approved is not None:
        (d / "approved.json").write_text(
            json.dumps(approved, ensure_ascii=False), encoding="utf-8")
    if manual is not None:
        (d / "manual.json").write_text(
            json.dumps(manual, ensure_ascii=False), encoding="utf-8")
    return d


class FakeResponse:
    def __init__(self, ok):
        self.ok = ok

    def raise_for_status(self):
        if not self.ok:
            raise Exception("404 Client Error: Not Found")


class FakeSession:
    """`requests.Session` の代わり。broken に入っている URL だけ失敗させる。"""

    def __init__(self, broken: set):
        self.headers = {}
        self.broken = broken
        self.calls: list[str] = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        return FakeResponse(ok=url not in self.broken)


def test_broken_url_appears_in_the_list():
    d = _dir(approved=[APPROVED_ALIVE, APPROVED_DEAD])
    try:
        sess = FakeSession(broken={APPROVED_DEAD["url"]})
        broken = find_broken_links(CFG, ReviewQueue(d), session=sess)
        assert [ev.url for ev, _ in broken] == [APPROVED_DEAD["url"]], broken
    finally:
        shutil.rmtree(d)


def test_healthy_urls_are_not_reported():
    d = _dir(approved=[APPROVED_ALIVE])
    try:
        sess = FakeSession(broken=set())
        broken = find_broken_links(CFG, ReviewQueue(d), session=sess)
        assert broken == [], broken
    finally:
        shutil.rmtree(d)


def test_does_not_change_any_data():
    """自動では却下しない。approved.json は1バイトも変わらない。"""
    d = _dir(approved=[APPROVED_ALIVE, APPROVED_DEAD])
    try:
        before = (d / "approved.json").read_text(encoding="utf-8")
        sess = FakeSession(broken={APPROVED_DEAD["url"]})
        find_broken_links(CFG, ReviewQueue(d), session=sess)
        after = (d / "approved.json").read_text(encoding="utf-8")
        assert before == after, "却下せずデータを変更してはいけない"
        q = ReviewQueue(d)
        assert len(q.approved) == 2, "件数が変わってはいけない"
        assert all(e.review_state == "approved" for e in q.approved)
    finally:
        shutil.rmtree(d)


def test_manual_urls_are_checked_too():
    d = _dir(approved=[APPROVED_ALIVE], manual=[MANUAL_DEAD])
    try:
        sess = FakeSession(broken={MANUAL_DEAD["url"]})
        broken = find_broken_links(CFG, ReviewQueue(d), session=sess)
        assert [ev.url for ev, _ in broken] == [MANUAL_DEAD["url"]], broken
    finally:
        shutil.rmtree(d)


class FakeClock:
    def __init__(self):
        self.now = 100.0
        self.slept = []

    def monotonic(self):
        return self.now

    def sleep(self, sec):
        self.slept.append(round(sec, 3))
        self.now += sec


def test_interval_is_kept_per_host():
    """大田市（Crawl-delay: 5）を待つあいだ、益田市の間隔は巻き込まれない。"""
    d = _dir(approved=[
        {**APPROVED_ALIVE, "url": "https://www.city.masuda.lg.jp/a"},
        {**APPROVED_ALIVE, "title": "b", "url": "https://www.city.masuda.lg.jp/b"},
        {**APPROVED_ALIVE, "title": "c", "url": "https://www.city.oda.lg.jp/c",
         "source": "oda_city"},
        {**APPROVED_ALIVE, "title": "d", "url": "https://www.city.oda.lg.jp/d",
         "source": "oda_city"},
    ])
    clock = FakeClock()
    real = base.time
    base.time = clock
    try:
        sess = FakeSession(broken=set())
        find_broken_links(CFG, ReviewQueue(d), session=sess)
        # 益田市は1秒間隔、大田市は5秒間隔。同じホストの2件目だけ待つ
        # （初回はどちらも待たない）。
        assert 1.0 in clock.slept, clock.slept
        assert 5.0 in clock.slept, clock.slept
    finally:
        base.time = real
        shutil.rmtree(d)


def test_failing_url_is_retried_once_not_twice():
    """1回だけ取り直す（設計判断12。2回に増やさない）。"""
    d = _dir(approved=[APPROVED_DEAD])
    try:
        sess = FakeSession(broken={APPROVED_DEAD["url"]})
        find_broken_links(CFG, ReviewQueue(d), session=sess)
        assert sess.calls == [APPROVED_DEAD["url"]] * 2, sess.calls
    finally:
        shutil.rmtree(d)


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
