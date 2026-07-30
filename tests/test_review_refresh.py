"""再収集で何が更新され、何が守られるかのテスト。

**分類器を直しても公開中のデータが変わらない**事故を2回踏んだ:
  - 「締切あり」タグを廃止したのに `tags: ['締切あり']` が2件残った
  - 種別をタイトル優先にしたのに `kind: 制度` `tags: ['随時']` が1件残った
どちらも手でデータを直して回復した。3回目を人の注意力で防ぐのは無理があるので、
仕組み（`ReviewQueue.CLASSIFIED`）とこのテストで止める。
"""
import dataclasses
import json
import pathlib
import shutil
import sys
import tempfile
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from collector.models import Event
from collector.review import ReviewQueue


def _ev(**kw) -> Event:
    d = dict(title="第37回さざんか祭り", prefecture="島根県", date_start=None,
             date_end=None, url="https://example.lg.jp/a/1", source="hamada_city")
    d.update(kw)
    return Event(**d)


def _reingest(old: Event, new: Event) -> Event:
    """approved.json に old を置いて new を取り込み、保存後の姿を返す。"""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="iwami-refresh-"))
    try:
        q = ReviewQueue(tmp)
        (tmp / "approved.json").write_text(
            json.dumps([old.to_dict()], ensure_ascii=False), encoding="utf-8")
        q.ingest([new], auto_approve=False)
        got = q.approved
        assert len(got) == 1, f"件数が変わった: {len(got)}（uid が不安定）"
        return got[0]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_kind_is_refreshed():
    """再収集で kind が更新される（ハンモックの回帰）。"""
    got = _reingest(_ev(kind="制度", review_state="approved"), _ev(kind="催し"))
    assert got.kind == "催し", f"kind が更新されない: {got.kind}"


def test_tags_are_refreshed_even_when_emptied():
    """**空になったタグも反映される。** ここが「締切あり」の回帰。

    `if not new_v: continue` で守ると、廃止したタグが永久に残る。
    分類器は必ず答えを返すので、空欄は「タグは無い」という答えそのもの。
    """
    got = _reingest(_ev(tags=["締切あり", "要申込"], review_state="approved"),
                    _ev(tags=["要申込"]))
    assert got.tags == ["要申込"], f"廃止したタグが残っている: {got.tags}"

    got = _reingest(_ev(tags=["随時"], review_state="approved"), _ev(tags=[]))
    assert got.tags == [], f"タグを空にできていない: {got.tags}"


def test_category_and_score_are_refreshed():
    got = _reingest(_ev(category="学び・講座", score=2, review_state="approved"),
                    _ev(category="祭り・市・マルシェ", score=7))
    assert got.category == "祭り・市・マルシェ", f"カテゴリが古い: {got.category}"
    assert got.score == 7, f"score が古い: {got.score}"


def test_human_decisions_are_never_overwritten():
    """承認と中止は人が下した判断。機械が上書きしてはいけない。"""
    got = _reingest(_ev(review_state="approved", status="中止", kind="催し"),
                    _ev(review_state="pending", status="開催予定", kind="募集"))
    assert got.review_state == "approved", "承認が上書きされた"
    assert got.status == "中止", "中止が上書きされた"
    assert got.kind == "募集", "機械が導く値は更新されるべき"


def test_extracted_dates_are_kept_when_extraction_fails():
    """抽出は失敗しうる。取れなかったら既存を消さない（分類とは性質が違う）。"""
    got = _reingest(_ev(date_start=date(2026, 8, 22), review_state="approved"),
                    _ev(date_start=None))
    assert got.date_start == date(2026, 8, 22), "取れなかったのに日付が消えた"


def test_every_event_field_is_categorised():
    """**Event に項目を足したら、必ずどれかに分類する。**

    分類し忘れると「更新されない項目」が黙って増える。それが `kind` と
    `tags` で2回起きた。ここで気づけるようにしておく。
    """
    fields = {f.name for f in dataclasses.fields(Event)}
    known = (set(ReviewQueue.ENRICHABLE) | set(ReviewQueue.REFRESHABLE)
             | set(ReviewQueue.CLASSIFIED) | set(ReviewQueue.FROM_SOURCE)
             | set(ReviewQueue.HUMAN_DECIDED))
    missing = fields - known
    assert not missing, (
        f"Event の項目が分類されていません: {sorted(missing)}\n"
        "  collector/review.py の ENRICHABLE / CLASSIFIED / FROM_SOURCE /\n"
        "  HUMAN_DECIDED のどれかに入れてください。"
        "「機械が導く値」なら更新される側です。")
    stale = known - fields
    assert not stale, f"Event に無い項目が並んでいます: {sorted(stale)}"
    # REFRESHABLE は ENRICHABLE の部分集合（埋めずに上書きだけ、はあり得ない）
    assert set(ReviewQueue.REFRESHABLE) <= set(ReviewQueue.ENRICHABLE)
    # 人の判断はどこにも混ざらない（review.py の assert と同じ内容を外からも見る）
    machine = (set(ReviewQueue.ENRICHABLE) | set(ReviewQueue.CLASSIFIED)
               | set(ReviewQueue.FROM_SOURCE))
    assert not (set(ReviewQueue.HUMAN_DECIDED) & machine), "人の判断が機械側に入っている"


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
