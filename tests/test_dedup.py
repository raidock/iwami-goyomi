"""重複事故の回帰テスト（v1.5で実際に起きた）。

原因: uid に開催日を含めていたため、日付抽出で開催日が埋まった瞬間に
      uid が変わり、同じイベントが2枚並んだ。
      逆に締切だけ取れたものは「既知」と判定され、抽出結果が捨てられた。
"""
import sys, pathlib, shutil, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from datetime import date

from collector.models import Event
from collector.review import ReviewQueue

URL = "https://www.city.hamada.shimane.jp/www/contents/1783496689810/index.html"


def _ev(**kw):
    base = dict(title="バックステージツアーが開催されます", prefecture="島根県",
                date_start=None, date_end=None, url=URL, source="hamada_city")
    base.update(kw)
    e = Event(**{k: v for k, v in base.items()
                 if k in Event.__dataclass_fields__})
    for k, v in kw.items():
        if k not in base:
            setattr(e, k, v)
    return e


def test_uid_does_not_change_when_date_is_filled():
    """開催日が後から埋まってもIDは変わらない。"""
    assert _ev().uid == _ev(date_start=date(2026, 8, 23)).uid


def test_uid_differs_for_different_urls():
    a, b = _ev(), _ev()
    b.url = URL.replace("1783496689810", "9999999999999")
    assert a.uid != b.uid


def _queue():
    d = pathlib.Path(tempfile.mkdtemp())
    return ReviewQueue(d), d


def test_no_duplicate_when_date_appears_later():
    """1回目は日付なし、2回目に日付ありで来ても1件のまま。"""
    q, d = _queue()
    try:
        first = _ev(); first.review_state = "auto"
        q.ingest([first])
        second = _ev(date_start=date(2026, 8, 23)); second.review_state = "auto"
        q.ingest([second])
        total = len(q.approved) + len(q.pending)
        assert total == 1, f"{total}件に増えている（重複）"
    finally:
        shutil.rmtree(d)


def test_known_item_receives_the_new_deadline():
    """既知でも、後から取れた締切はちゃんと反映される（Go-Conで捨てられた不具合）。"""
    q, d = _queue()
    try:
        first = _ev(); first.review_state = "auto"
        q.ingest([first])
        second = _ev(); second.review_state = "auto"
        second.deadline = date(2026, 8, 3)
        second.deadline_source = "見出し「提出期限」"
        stats = q.ingest([second])
        got = q.approved[0]
        assert got.deadline == date(2026, 8, 3), "締切が反映されていない"
        assert stats["updated"] == 1
    finally:
        shutil.rmtree(d)


def test_human_decision_is_never_overwritten():
    """人が却下したものが、再収集で勝手に復活しない。"""
    q, d = _queue()
    try:
        e = _ev(); e.review_state = "review"
        q.ingest([e])
        q.decide(q.pending[0].uid, approve=False)
        assert len(q.rejected) == 1
        again = _ev(date_start=date(2026, 8, 23)); again.review_state = "auto"
        q.ingest([again])
        assert len(q.approved) == 0, "却下したものが復活している"
        assert len(q.rejected) == 1
        assert q.rejected[0].date_start == date(2026, 8, 23), "却下側にも日付は追記される"
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
