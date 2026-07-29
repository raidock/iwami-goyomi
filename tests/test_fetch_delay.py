"""取得間隔（fetch_delay_sec）のテスト。

大田市（ginzan-wm.jp）が robots.txt で `Crawl-delay: 5` を宣言していた。
間隔が全情報源で共通だと、守れば他の4情報源まで5秒待つことになり、
守らなければ設計判断12（情報源への礼儀）に反する。
**相手が宣言した値は、その相手にだけ効かせる。**

実時間で待つテストは遅くて不安定なので、time を差し替えて「何秒待とうとしたか」
を見る。待った長さそのものではなく、間隔の決め方が正しいかを確かめる。
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import collector.sources.base as base                     # noqa: E402
from collector.sources.base import DEFAULT_FETCH_DELAY_SEC, Pacer  # noqa: E402
from main import build_sources, fetch_delay_for           # noqa: E402

CFG = {
    "fetch_delay_sec": 1.0,
    "municipalities": [
        {"key": "hamada_city", "municipality": "浜田市",
         "site": "https://www.city.hamada.shimane.jp"},
        # robots.txt に Crawl-delay: 5 を宣言している想定の情報源
        {"key": "ohda_city", "municipality": "大田市",
         "site": "https://www.city.ohda.lg.jp", "fetch_delay_sec": 5},
    ],
    "tourism": [
        {"key": "hamanavi", "municipality": "浜田市",
         "site": "https://kankou-hamada.or.jp", "trust": "high"},
    ],
}


class FakeClock:
    """time.monotonic / time.sleep の差し替え。眠らずに時計だけ進める。"""

    def __init__(self):
        self.now = 100.0
        self.slept = []

    def monotonic(self):
        return self.now

    def sleep(self, sec):
        self.slept.append(round(sec, 3))
        self.now += sec

    def advance(self, sec):
        self.now += sec


def _patched(fn):
    """base モジュールの time を差し替えて実行する。"""
    clock = FakeClock()
    real = base.time
    base.time = clock
    try:
        fn(clock)
    finally:
        base.time = real


def test_source_delay_falls_back_to_global_default():
    assert fetch_delay_for({"key": "hamada_city"}, CFG) == 1.0
    assert fetch_delay_for({"key": "hamanavi"}, CFG) == 1.0


def test_source_delay_can_be_overridden_per_source():
    assert fetch_delay_for({"key": "ohda_city", "fetch_delay_sec": 5}, CFG) == 5.0


def test_delay_defaults_when_config_says_nothing():
    """config に fetch_delay_sec が無くても 0 秒にはしない。"""
    assert fetch_delay_for({}, {}) == DEFAULT_FETCH_DELAY_SEC


def test_adapters_get_their_own_delay():
    """config の値がアダプターまで届いていること。"""
    got = {src.name: src.pacer.delay for src, _ in build_sources(CFG)}
    assert got == {"hamada_city": 1.0, "ohda_city": 5.0, "hamanavi": 1.0}, got


def test_first_fetch_does_not_wait():
    def body(clock):
        p = Pacer(5)
        p.wait()
        assert clock.slept == [], clock.slept
    _patched(body)


def test_waits_the_remainder_only():
    """前回の応答からの経過分は差し引く。取得に時間がかかった分は待たない。"""
    def body(clock):
        p = Pacer(5)
        p.mark()
        clock.advance(2.0)          # 他の情報源を取りにいっていた2秒
        p.wait()
        assert clock.slept == [3.0], clock.slept
    _patched(body)


def test_no_wait_when_enough_time_has_passed():
    def body(clock):
        p = Pacer(5)
        p.mark()
        clock.advance(9.0)
        p.wait()
        assert clock.slept == [], clock.slept
    _patched(body)


def test_each_source_keeps_its_own_clock():
    """遅い情報源が他の情報源を巻き込まないこと。

    間隔を1つの時計で持っていたときは、大田市の5秒が浜田市の取得にも
    そのまま効いていた。
    """
    def body(clock):
        hamada, ohda = Pacer(1), Pacer(5)
        hamada.mark()
        ohda.mark()
        clock.advance(1.2)
        hamada.wait()               # 1秒経っているので待たない
        assert clock.slept == [], clock.slept
        ohda.wait()                 # こちらはあと3.8秒待つ
        assert clock.slept == [3.8], clock.slept
    _patched(body)


def test_failed_fetch_still_counts_as_a_visit():
    """失敗しても相手のサーバは叩いている。次の間隔を詰めない。"""
    class Boom(base.Source):
        def collect(self):
            return []

    def body(clock):
        s = Boom(fetch_delay_sec=5)
        s.session.get = lambda *a, **k: (_ for _ in ()).throw(OSError("timeout"))
        for _ in range(2):
            try:
                s.get("https://example.jp/x")
            except OSError:
                pass
        assert clock.slept == [5.0], clock.slept
    _patched(body)


def test_discovery_requests_are_spaced():
    """自動発見は1サイトに何度も当てる（FALLBACK_PATHS は最大7回）。

    間隔を呼ぶ側に任せていたときは、この経路だけ素通りしていた。
    """
    class Fake(base.Source):
        def collect(self):
            return []

    def body(clock):
        s = Fake(fetch_delay_sec=2)

        class Resp:
            status_code, text, encoding, apparent_encoding = 200, "ok", "utf-8", "utf-8"

            def raise_for_status(self):
                return None

        s.session.get = lambda *a, **k: Resp()
        for _ in range(3):
            s.get("https://example.jp/rss.xml")
        assert clock.slept == [2.0, 2.0], clock.slept
    _patched(body)


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
