"""種別（催し／募集／制度）の判定・日付抽出・並び順のテスト。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from datetime import date

from collector.classify import detect_kind
from collector.models import Event, extract_deadline, extract_held_date
from collector.publish import to_public_site

TODAY = date(2026, 7, 27)

KIND_CASES = [
    # 制度は催しの語を含んでいても制度（判定順序のテスト）
    ("出前講座をご利用ください", "制度"),
    ("移動図書館の貸出について", "制度"),
    # 催しの名詞があれば催し。「参加者募集」でも本体は祭り
    ("第37回さざんか祭り　アトラクション参加者募集について", "催し"),
    ("一斉相談会（法律相談）のお知らせ", "催し"),
    ("令和8年度山陰浜田港お魚料理教室の開催日程", "催し"),
    ("救命講習定期開催のお知らせ", "催し"),
    # 催しの名詞がなく募集語があれば募集
    ("地域おこし協力隊を募集します", "募集"),
    ("江津市ビジネスプランコンテスト「Go-Con2026」", "募集"),
    ("石央文化ホール「2026　DANCE　CONTEST」出場者大募集！！", "募集"),
    ("令和8年度島根県統計グラフコンクール作品募集について", "募集"),
]


def test_kind_detection():
    for title, expect in KIND_CASES:
        got = detect_kind(title)
        assert got == expect, f"{title[:30]} → {got}（期待 {expect}）"


def test_year_inferred_from_publication_date():
    """年の推定は今日ではなく掲載日が基準。

    1月に出た「3/8開催」は、いま7月でも2026年3月8日を指す。
    """
    assert extract_held_date("3/8（日）開催婚活イベント", date(2026, 1, 26)) == date(2026, 3, 8)
    assert extract_held_date("8月9日開催のつわの蚤の市", date(2026, 7, 24)) == date(2026, 8, 9)


def test_deadline_patterns():
    ref = date(2026, 7, 9)
    assert extract_deadline("参加者募集 8月10日まで", ref) == date(2026, 8, 10)
    assert extract_deadline("締切：9月1日", ref) == date(2026, 9, 1)
    assert extract_deadline("8月20日必着", ref) == date(2026, 8, 20)
    assert extract_deadline("第37回さざんか祭り", ref) is None


def _ev(title, kind, deadline=None, start=None):
    e = Event(title=title, prefecture="島根県", date_start=start, date_end=None,
              url="https://example.jp/x", source="t", city="浜田市")
    e.kind, e.deadline, e.published_at = kind, deadline, date(2026, 7, 1)
    return e


def test_boshu_promoted_when_deadline_is_near():
    """締切が近いものがあるとき、募集ブロックが催しより上に来る。"""
    evs = [_ev("催しA", "催し", start=date(2026, 9, 1)),
           _ev("募集B", "募集", deadline=date(2026, 8, 3))]   # あと7日
    html = to_public_site(evs, "石見", TODAY)
    assert html.index("募集・締切のあるもの") < html.index("これからの催し")


def test_moyoshi_first_when_no_urgent_deadline():
    """締切が遠いときは、ふだんどおり催しが先頭。"""
    evs = [_ev("催しA", "催し", start=date(2026, 9, 1)),
           _ev("募集B", "募集", deadline=date(2026, 12, 1))]  # まだ先
    html = to_public_site(evs, "石見", TODAY)
    assert html.index("これからの催し") < html.index("募集・締切のあるもの")


def test_boshu_sorted_by_deadline_ascending():
    """募集は締切が近い順（催しとは逆に、急ぐものが上）。"""
    evs = [_ev("遅い", "募集", deadline=date(2026, 10, 1)),
           _ev("早い", "募集", deadline=date(2026, 8, 5))]
    html = to_public_site(evs, "石見", TODAY)
    assert html.index("早い") < html.index("遅い")


def test_countdown_and_seido_display():
    html = to_public_site(
        [_ev("募集X", "募集", deadline=date(2026, 8, 3)), _ev("制度Y", "制度")],
        "石見", TODAY)
    assert "あと7日" in html
    assert "随時" in html
    assert "いつでも使えるもの" in html


def test_event_with_deadline_shows_note():
    """催しに申込締切があるときは、開催日とは別に注記が出る。"""
    html = to_public_site([_ev("写真教室", "催し", deadline=date(2026, 8, 1))],
                          "石見", TODAY)
    assert "申込締切 8/1" in html and "あと5日" in html




# --- 過去のものを「これから」に出さない（2026-07 実画面で発覚）-----------------
from collector.publish import is_past


def test_past_event_is_not_upcoming():
    """7/18の催しは、7/27時点では終了扱い。"""
    assert is_past(_ev("岡見花火", "催し", start=date(2026, 7, 18)), TODAY)


def test_future_event_is_upcoming():
    assert not is_past(_ev("GO GOTSU フェス", "催し", start=date(2026, 8, 2)), TODAY)


def test_long_running_period_is_not_past():
    """年間通しの定期公演（4月〜翌3月）を、開始日が過去でも消さない。"""
    e = _ev("石見神楽定期公演", "催し", start=date(2026, 4, 1))
    e.date_end = date(2027, 3, 31)
    assert not is_past(e, TODAY)


def test_unknown_date_is_never_past():
    """日付が分からないものを勝手に終了扱いにしない。"""
    assert not is_past(_ev("日程未定の催し", "催し"), TODAY)


def test_expired_deadline_is_past():
    assert is_past(_ev("締切ぎれ", "募集", deadline=date(2026, 7, 20)), TODAY)
    assert not is_past(_ev("まだ間に合う", "募集", deadline=date(2026, 8, 3)), TODAY)


def test_seido_never_expires():
    assert not is_past(_ev("出前講座", "制度"), TODAY)


def test_past_events_move_to_collapsed_section():
    """終わったものは消さず、畳んだ節に残す。"""
    evs = [_ev("終わった花火", "催し", start=date(2026, 7, 18)),
           _ev("これからのフェス", "催し", start=date(2026, 8, 2))]
    html = to_public_site(evs, "石見", TODAY)
    assert "終わった催し" in html, "終了節が出ていない"
    assert "終わった花火" in html, "終わったものが消えてしまっている"
    # 「これからの催し」より後ろにあること
    assert html.index("これからの催し") < html.index("終わった催し")
    # これから側の件数に終わったものが混ざっていないこと
    assert "催し 1" in html, "件数表示に終了分が混ざっている"



# --- 時差の扱い（2026-07 本番で発覚）------------------------------------------
# GitHub Actions は UTC で動くため、日本時間の 0時〜9時 は日付が1日前になる。
# 地域の暦なので、必ず日本時間で判定する。

def test_uses_japan_time_not_utc():
    from datetime import datetime, timezone
    from collector.models import now_jst, today_jst
    n = now_jst()
    assert str(n.tzinfo) == "Asia/Tokyo", n.tzinfo
    # UTCとの差は常に9時間
    diff = n.utcoffset().total_seconds() / 3600
    assert diff == 9, diff
    # 日付も日本時間のもの
    assert today_jst() == n.date()


def test_utc_early_morning_would_be_previous_day():
    """UTCで判定すると1日ずれることの確認（この差が実害だった）。"""
    from datetime import datetime, timezone
    from collector.models import JST
    # 日本時間 2026-07-28 の朝8時 = UTC では 7/27 の23時
    jst_morning = datetime(2026, 7, 28, 8, 0, tzinfo=JST)
    assert jst_morning.astimezone(timezone.utc).date().day == 27
    assert jst_morning.date().day == 28


def test_past_judgement_uses_given_today():
    """当日の催しは、その日のうちは「これから」に残る。"""
    from datetime import date
    e = _ev("今日の催し", "催し", start=date(2026, 7, 28))
    assert not is_past(e, date(2026, 7, 28))
    assert is_past(e, date(2026, 7, 29))


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
