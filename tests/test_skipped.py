"""除外記録（data/skipped.json）のテスト。

`is_finished()` で黙って除外された記事は、`known_uids()` に一度も入らないため
情報源に残り続けるかぎり毎日詳細ページを無駄に再取得していた
（2026-08-08 measurements/is-finished-permanent-drop.md）。
除外を記録し、次回は詳細ページの再取得を避けるようにした。**却下（rejected）
とは別枠**（却下は人の判断、こちらは機械の判定）。
"""
import pathlib
import shutil
import sys
import tempfile
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from collector.models import Event
from collector.review import ReviewQueue

TODAY = date(2026, 8, 8)


def _ev(**kw) -> Event:
    d = dict(title="毎週土曜の天体観察会", prefecture="島根県",
             date_start=date(2025, 6, 7), date_end=None,
             url="https://example.jp/a/1", source="oda_kanko")
    d.update(kw)
    return Event(**d)


def _queue() -> tuple[ReviewQueue, pathlib.Path]:
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="iwami-skipped-"))
    return ReviewQueue(tmp), tmp


def test_finished_event_is_recorded_in_skipped():
    """分かっている日付が全部過去の初見記事は、skipped.json に記録される。"""
    q, tmp = _queue()
    try:
        stats = q.ingest([_ev()], auto_approve=False, today=TODAY)
        assert stats["finished"] == 1
        assert q.pending == [] and q.approved == [] and q.rejected == []
        skipped = q.skipped
        assert len(skipped) == 1, f"skipped.json に記録されていない: {skipped}"
        assert skipped[0].review_state == "skipped"
        assert skipped[0].uid not in q.known_uids(), (
            "skipped は known_uids() に混ぜてはいけない（人の判断ではないため）")
        assert skipped[0].uid in q.skipped_uids()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_skipped_is_separate_from_rejected():
    """却下は人の判断、除外記録は機械の判定。混ぜてはいけない。"""
    q, tmp = _queue()
    try:
        q.ingest([_ev()], auto_approve=False, today=TODAY)
        assert q.skipped and not q.rejected, (
            "機械の除外が rejected.json に混ざっている")
        # 却下は別の経路（decide）でしか起きない
        assert q.skipped[0].uid not in {e.uid for e in q.rejected}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_repeated_ingest_does_not_duplicate_skipped_entries():
    """毎日の収集で同じ記事が何度も『初見』扱いされても、記録は1件のまま。"""
    q, tmp = _queue()
    try:
        q.ingest([_ev()], auto_approve=False, today=TODAY)
        q.ingest([_ev()], auto_approve=False, today=TODAY)
        q.ingest([_ev(date_start=date(2025, 6, 14))], auto_approve=False, today=TODAY)
        assert len(q.skipped) == 1, f"重複して増えている: {q.skipped}"
        assert q.skipped[0].date_start == date(2025, 6, 14), "最新の抽出結果に更新されていない"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_prune_skipped_removes_entries_past_max_age():
    """情報源側が max_age_days を超えた記事を返さなくなるのに合わせて記録も消す。"""
    q, tmp = _queue()
    try:
        old = _ev(url="https://example.jp/old", date_start=date(2024, 1, 1),
                  source="misato_kanko")
        fresh = _ev(url="https://example.jp/fresh", date_start=date(2026, 7, 1),
                   source="misato_kanko")
        q.ingest([old, fresh], auto_approve=False, today=TODAY)
        assert len(q.skipped) == 2

        removed = q.prune_skipped({"misato_kanko": 400}, 400, TODAY)
        assert removed == 1, f"古いほうだけ消えるはず: removed={removed}"
        remaining = {e.url for e in q.skipped}
        assert remaining == {"https://example.jp/fresh"}, remaining
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_prune_skipped_uses_default_when_source_has_no_override():
    """`max_age_by_source` に無い情報源は、渡された既定値で判定する。"""
    # 経過585日（2025-01-01 → 2026-08-08）
    old = _ev(url="https://example.jp/old", date_start=date(2025, 1, 1),
              source="unknown_source")

    q, tmp = _queue()
    try:
        q.ingest([old], auto_approve=False, today=TODAY)
        # 既定1000日なら585日は超えないので残る
        assert q.prune_skipped({}, 1000, TODAY) == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    q2, tmp2 = _queue()
    try:
        q2.ingest([old], auto_approve=False, today=TODAY)
        # 既定400日なら585日は超えるので消える
        assert q2.prune_skipped({}, 400, TODAY) == 1
    finally:
        shutil.rmtree(tmp2, ignore_errors=True)


def main() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    bad = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            print(f"FAIL {fn.__name__}: {e}")
            bad += 1
    print(f"\n{len(fns) - bad}/{len(fns)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
