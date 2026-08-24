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


# --- 日付の更新（2026-07 追加）----------------------------------------------
# 埋めるだけにしていたため、複数回ある催し（救命講習は年6回）で次回が過ぎた
# 瞬間に古い日付が残り、残りの回があるのに is_past() で永久に畳まれていた。
# 抽出由来の値は毎回の抽出結果で上書きする。

def test_known_item_date_is_refreshed_not_frozen():
    """次回が過ぎたら、次の回に進む。古い日付が凍りつかない。"""
    q, d = _queue()
    try:
        first = _ev(date_start=date(2026, 9, 12)); first.review_state = "auto"
        first.date_source = "表「講習日時」の列（全6回・次回）"
        first.session_count = 6
        q.ingest([first])
        later = _ev(date_start=date(2026, 11, 18)); later.review_state = "auto"
        later.date_source = "表「講習日時」の列（全6回・次回）"
        later.session_count = 6
        stats = q.ingest([later])
        assert q.approved[0].date_start == date(2026, 11, 18), \
            f"古い日付が残っている: {q.approved[0].date_start}"
        assert stats["updated"] == 1
    finally:
        shutil.rmtree(d)


def test_missing_new_date_does_not_erase_the_old_one():
    """抽出器が None を返した回で、既存の日付を消さない。"""
    q, d = _queue()
    try:
        first = _ev(date_start=date(2026, 9, 12)); first.review_state = "auto"
        q.ingest([first])
        blank = _ev(); blank.review_state = "auto"      # 今回は取れなかった
        q.ingest([blank])
        assert q.approved[0].date_start == date(2026, 9, 12), "既存の日付が消えた"
    finally:
        shutil.rmtree(d)


def test_title_derived_date_is_also_refreshable():
    """date_source が空（タイトル由来）でも凍結しない。

    main.py の extract_held_date はタイトルから日付を取るとき date_source を
    設定しない。更新条件に date_source を使うと、この経路が永久に凍る。
    """
    q, d = _queue()
    try:
        pinned_today = date(2026, 8, 1)  # 固定しないと日付が過ぎるたびに is_finished() で弾かれる
        first = _ev(date_start=date(2026, 8, 22)); first.review_state = "auto"
        assert first.date_source == "", "前提が変わっている"
        q.ingest([first], today=pinned_today)
        later = _ev(date_start=date(2026, 8, 23)); later.review_state = "auto"
        q.ingest([later], today=pinned_today)
        assert q.approved[0].date_start == date(2026, 8, 23)
    finally:
        shutil.rmtree(d)


def test_human_judgement_is_not_in_the_refresh_lists():
    """review_state と status は上書き対象に入れない（人の判断だから）。"""
    fields = set(ReviewQueue.ENRICHABLE) | set(ReviewQueue.REFRESHABLE)
    assert "review_state" not in fields
    assert "status" not in fields


def test_venue_is_filled_but_not_overwritten():
    """会場は空欄のときだけ埋める。日付と違って抽出のたびに変わる値ではない。"""
    q, d = _queue()
    try:
        first = _ev(); first.review_state = "auto"; first.venue = "石央文化ホール"
        q.ingest([first])
        other = _ev(); other.review_state = "auto"; other.venue = "浜田市消防本部"
        q.ingest([other])
        assert q.approved[0].venue == "石央文化ホール", "会場が上書きされた"
    finally:
        shutil.rmtree(d)


def test_rejected_item_dates_refresh_without_resurrecting():
    """却下済みでも日付は追記・更新されるが、判断は却下のまま。"""
    q, d = _queue()
    try:
        e = _ev(); e.review_state = "review"
        q.ingest([e])
        q.decide(q.pending[0].uid, approve=False)
        again = _ev(date_start=date(2026, 9, 12)); again.review_state = "auto"
        q.ingest([again])
        assert len(q.approved) == 0 and len(q.rejected) == 1
        assert q.rejected[0].review_state == "rejected", "人の判断が変わった"
        assert q.rejected[0].date_start == date(2026, 9, 12)
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
