"""手で足す掲載（data/manual.json）の回帰テスト。

きっかけは石州浜っ子夏まつり（2026-08-01。浜田市最大の祭り）が載らなかったこと。
告知が記事ではなくランディングページで、記事カテゴリRSSには**永久に乗らない**。
大きな催しほど専用ページが作られるので、規模と検出率が反比例していた。

ここで守るのは3つ:
  1. 手動の1件が公開データに出る
  2. 収集を回しても消えない・上書きされない
  3. 同じURLが自動収集で来たときの挙動（**手動が勝つ**）
"""
import json
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from datetime import date

from collector.manual import HAND_TYPED, MANUAL_SOURCE, load_manual, merge_for_build
from collector.models import Event
from collector.publish import to_public_site
from collector.review import ReviewQueue

URL = "https://kankou-hamada.or.jp/lp/hamakko-natsumaturi/"
ENTRY = {
    "title": "2026石州浜っ子夏まつり",
    "url": URL,
    "city": "浜田市",
    "kind": "催し",
    "category": "祭り・市・マルシェ",
    "date_start": "2026-08-01",
    "venue": "浜田漁港一帯（浜田市原井町）",
}


def _dir(entries=None):
    d = pathlib.Path(tempfile.mkdtemp())
    if entries is not None:
        (d / "manual.json").write_text(
            json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    return d


def _collected(**kw):
    """自動収集が同じURLを拾ってきた場合のイベント。"""
    base = dict(title="【夏まつり】交通規制のお知らせ", prefecture="島根県",
                date_start=None, date_end=None, url=URL, source="hamanavi")
    base.update(kw)
    e = Event(**base)
    e.review_state = "auto"
    return e


# --- 1. 手動の1件が公開データに出る ----------------------------------------

def test_manual_entry_reaches_the_public_page():
    d = _dir([ENTRY])
    try:
        events = merge_for_build([], ReviewQueue(d).manual)
        assert len(events) == 1, f"{len(events)}件（1件のはず）"
        html = to_public_site(events, today=date(2026, 8, 1))
        assert "2026石州浜っ子夏まつり" in html, "画面に出ていない"
        assert "これからの催し" in html, "終わった扱いになっている"
        assert URL in html, "一次情報リンクが出ていない"
    finally:
        shutil.rmtree(d)


def test_minimum_fields_are_title_and_url():
    """最低限これだけで載る、という形を守る。"""
    d = _dir([{"title": "手で足した催し", "url": "https://example.com/a"}])
    try:
        got = ReviewQueue(d).manual
        assert len(got) == 1
        assert got[0].kind == "催し" and got[0].prefecture == "島根県"
    finally:
        shutil.rmtree(d)


def test_origin_is_recorded():
    """出どころが追えること。**根拠が追えないものは公開しない。**"""
    d = _dir([dict(ENTRY, deadline="2026-07-25")])
    try:
        ev = ReviewQueue(d).manual[0]
        assert ev.source == MANUAL_SOURCE, ev.source
        assert ev.date_source == HAND_TYPED, ev.date_source
        assert ev.deadline_source == HAND_TYPED, ev.deadline_source
        assert ev.review_state == "approved"
    finally:
        shutil.rmtree(d)


def test_machine_only_fields_cannot_be_forged():
    """source を手で書いても、手動であることは隠せない。"""
    d = _dir([dict(ENTRY, source="hamada_city", date_source="見出し「日時」",
                   review_state="pending", score=9)])
    try:
        ev = ReviewQueue(d).manual[0]
        assert ev.source == MANUAL_SOURCE
        assert ev.date_source == HAND_TYPED
        assert ev.review_state == "approved" and ev.score == 0
    finally:
        shutil.rmtree(d)


# --- 2. 収集を回しても消えない・上書きされない ------------------------------

def test_collect_does_not_touch_the_manual_file():
    """ingest は manual.json を1バイトも書き換えない。"""
    d = _dir([ENTRY])
    try:
        before = (d / "manual.json").read_bytes()
        ReviewQueue(d).ingest([_collected(date_start=date(2026, 9, 30))])
        assert (d / "manual.json").read_bytes() == before, "手動の値が書き換えられた"
    finally:
        shutil.rmtree(d)


def test_manual_values_win_over_extraction():
    """機械が別の日付を取ってきても、手で入れた値が勝つ。"""
    d = _dir([ENTRY])
    try:
        q = ReviewQueue(d)
        q.ingest([_collected(date_start=date(2026, 9, 30))])
        ev = merge_for_build([e for e in q.approved
                              if e.review_state == "approved"], q.manual)[0]
        assert ev.date_start == date(2026, 8, 1), ev.date_start
        assert ev.title == "2026石州浜っ子夏まつり", ev.title
    finally:
        shutil.rmtree(d)


# --- 3. 同じURLが自動収集で来たときの挙動 -----------------------------------

def test_same_url_is_not_queued_again():
    """人が書いた1件を、もう一度人に判断させない。"""
    d = _dir([ENTRY])
    try:
        q = ReviewQueue(d)
        stats = q.ingest([_collected()])
        assert stats["manual"] == 1, stats
        assert len(q.approved) == 0 and len(q.pending) == 0, "キューに入っている"
    finally:
        shutil.rmtree(d)


def test_already_approved_duplicate_is_dropped_at_build():
    """manual.json を書く前に自動収集が承認済みだった場合、公開は1枚だけ。

    ingest で止めるのは**これから来るもの**だけなので、出口でも要る。
    """
    d = _dir([ENTRY])
    try:
        q = ReviewQueue(d)
        old = _collected()
        old.review_state = "approved"
        q._save(q.approved_path, [old])
        events = merge_for_build([e for e in q.approved
                                  if e.review_state == "approved"], q.manual)
        assert len(events) == 1, f"{len(events)}枚並んでいる（重複）"
        assert events[0].source == MANUAL_SOURCE
    finally:
        shutil.rmtree(d)


def test_manual_uid_is_the_url():
    """uid は URL 基準（設計判断2）。手動でも同じ規則で並ぶ。"""
    d = _dir([ENTRY])
    try:
        assert ReviewQueue(d).manual[0].uid == _collected().uid
    finally:
        shutil.rmtree(d)


# --- 書き間違いで公開を止めない ---------------------------------------------
# 1件の打ち間違いで暦全体が出なくなるほうが痛い。警告して、その1件だけ飛ばす。

def test_broken_json_does_not_stop_the_build():
    d = _dir()
    try:
        (d / "manual.json").write_text("[{壊れている}]", encoding="utf-8")
        assert load_manual(d / "manual.json") == []
    finally:
        shutil.rmtree(d)


def test_bad_entry_is_skipped_but_others_survive():
    d = _dir([{"url": "https://example.com/no-title"},
              {"title": "こちらは正しい", "url": "https://example.com/ok"},
              {"title": "日付が変", "url": "https://example.com/x",
               "date_start": "2026年8月1日"}])
    try:
        got = load_manual(d / "manual.json")
        assert [e.title for e in got] == ["こちらは正しい", "日付が変"], \
            [e.title for e in got]
        assert got[1].date_start is None, "読めない日付が入っている"
    finally:
        shutil.rmtree(d)


def test_unknown_kind_falls_back_to_moyoshi():
    """種別の打ち間違いで、催しが画面から消えないこと。"""
    d = _dir([dict(ENTRY, kind="イベント")])
    try:
        assert load_manual(d / "manual.json")[0].kind == "催し"
    finally:
        shutil.rmtree(d)


def test_duplicate_urls_inside_the_file():
    d = _dir([ENTRY, dict(ENTRY, title="同じURLの2件目")])
    try:
        got = load_manual(d / "manual.json")
        assert len(got) == 1 and got[0].title == "2026石州浜っ子夏まつり"
    finally:
        shutil.rmtree(d)


def test_missing_file_is_normal():
    d = _dir()
    try:
        assert ReviewQueue(d).manual == []
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
