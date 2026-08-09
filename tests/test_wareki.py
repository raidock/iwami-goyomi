"""和暦と、観光協会サイト（はまナビ）の【日時】形式のテスト。

はまナビは「令和7年11月8日（土）」のように和暦で書く。
西暦しか読めないと観光協会の日付が1件も取れない。
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from datetime import date

from collector.extract import extract_dates
from collector.models import wareki_to_seireki

# はまナビ「みすみフェスティバル2025」の構造（実サイトより）
HAMANAVI_FES = """
<div class="entry">
  <h1>みすみフェスティバル2025</h1>
  <p>浜田市三隅町の産業祭・みすみフェスティバルが2日間、三隅中央公園で開催されます。</p>
  <p>【日時】</p>
  <p>令和7年11月8日（土）・9日（日） 10：00～15：00 ※雨天決行</p>
  <p>【場所】</p>
  <p>三隅中央公園・三隅中央会館（浜田市三隅町古市場589）</p>
  <p>【主催・問合せ】</p>
  <p>浜田市観光協会 TEL 0855-24-1085</p>
</div>
"""

# 申込締切が【】の中にある形
HAMANAVI_KOSHU = """
<div class="entry">
  <h1>浜田の石見神楽講習会</h1>
  <p>【日時】</p>
  <p>令和8年9月20日（日）13：30～</p>
  <p>【申込締切】</p>
  <p>令和8年9月10日（木）</p>
</div>
"""


def test_wareki_conversion():
    assert wareki_to_seireki("令和7年11月8日") == "2025年11月8日"
    assert wareki_to_seireki("令和元年5月1日") == "2019年5月1日"
    assert wareki_to_seireki("平成31年4月30日") == "2019年4月30日"


def test_wareki_leaves_seireki_alone():
    assert wareki_to_seireki("2026年8月3日") == "2026年8月3日"


def test_hamanavi_bracket_label():
    """【日時】形式（見出しタグではない）から開催日を取る。"""
    got = extract_dates(HAMANAVI_FES, ref=date(2025, 10, 1))
    assert got.date_start == date(2025, 11, 8), got.date_start
    assert "日時" in got.date_source, got.date_source


def test_hamanavi_deadline_in_bracket():
    got = extract_dates(HAMANAVI_KOSHU, ref=date(2026, 8, 1))
    assert got.date_start == date(2026, 9, 20), got.date_start
    assert got.deadline == date(2026, 9, 10), got.deadline


def test_does_not_confuse_place_with_date():
    """【場所】に含まれる番地（589）を日付と誤読しない。"""
    got = extract_dates(HAMANAVI_FES, ref=date(2025, 10, 1))
    assert got.date_start == date(2025, 11, 8)



# --- 2026-07 実画面で見つかった追加ケース -----------------------------------

def test_era_abbreviation():
    """「R8.7.20」の略記。地域のチラシや投稿でよく使われる。"""
    assert wareki_to_seireki("夏祭り（R8.7.20）") == "夏祭り（2026年7月20日）"
    assert wareki_to_seireki("H31.4.30") == "2019年4月30日"   # 平成31年=2019年


def test_era_abbr_does_not_break_words():
    """ROOM8 のような英字の並びを日付と誤読しない。"""
    assert wareki_to_seireki("ROOM8.7.20") == "ROOM8.7.20"


def test_leading_date_in_title_is_held_date():
    """タイトル冒頭の日付は開催日とみなす。"""
    from collector.models import extract_held_date
    got = extract_held_date(
        "8月22日（土）有福温泉湯の町神楽殿　石見神楽定期公演休演のお知らせ",
        date(2026, 7, 8))
    assert got == date(2026, 8, 22), got


def test_leading_year_in_title_is_used_as_written():
    """タイトルに年が書いてあれば、掲載日から推し量らずその年を使う。

    年を捨てて月日だけ見ていたため、2026年7月に出た「2027年8月1日」の告知が
    2026年8月1日になっていた。掲載日から見ると未来なので、
    「あと○日」も終了判定も通ってしまい、画面を見ても気づけない。
    """
    from collector.models import extract_held_date
    ref = date(2026, 7, 29)
    assert extract_held_date("2027年8月1日（日）石見神楽大会", ref) == date(2027, 8, 1)
    # 過ぎた年もそのまま読む（勝手に来年へ繰り上げない）
    assert extract_held_date("2024年3月1日 卒業記念公演の記録", ref) == date(2024, 3, 1)
    # 令和表記も西暦に直したうえで同じ扱いになる
    assert extract_held_date("令和9年8月1日 神楽競演大会", ref) == date(2027, 8, 1)
    # 年が書いていないものは従来どおり掲載日基準
    assert extract_held_date("8月22日（土）有福温泉…", ref) == date(2026, 8, 22)
    # 書き間違いの日付で落ちない
    assert extract_held_date("2026年2月30日 なにか", ref) is None


def test_category_prefers_title_over_description():
    """説明文の「石見神楽」に引っ張られない（実画面で ぶどうまつり が神楽になった）。"""
    from collector.classify import classify
    v = classify("ぶどうまつり", "石見神楽の上演もあります")
    assert v.category == "祭り・市・マルシェ", v.category
    v2 = classify("今月のお知らせ", "陶芸教室を開催します")
    assert v2.category is not None


# --- タイトル頭の【…】に続く日付（2026-08 / 津和野町観光協会）---------------
# 8つ目の日付表記。津和野町観光協会は「【津和野盆踊り】8/15　409回目の夏」の形。
# 実データ153件で測って、当たるのは津和野の6件だけ・全部正しい。

def test_bracket_then_slash_date():
    from datetime import date
    from collector.models import extract_held_date
    cases = [
        ("【津和野町日本遺産センター】8/2〜9/27「津和野踊り企画展」開催",
         date(2026, 7, 30), date(2026, 8, 2)),
        ("【津和野盆踊り】8/15　409回目の夏　殿町盆踊り開催のお知らせ",
         date(2026, 7, 15), date(2026, 8, 15)),
        ("【鷺舞神事】7/20・7/27祇園祭弥栄神社の鷺舞神事催行のお知らせ",
         date(2026, 6, 15), date(2026, 7, 20)),
        ("【駅開業記念日】8/1(土)、津和野駅夜市を今年も開催します！",
         date(2026, 7, 1), date(2026, 8, 1)),
    ]
    for title, ref, want in cases:
        assert extract_held_date(title, ref) == want, title


def test_bracket_date_does_not_swallow_a_deadline():
    """**「まで」が続くなら開催日にしない。**

    後ろ向き言明だけでは足りない。`(?!\\d)` が無いと「8/31まで」の日を
    「3」に縮めて言明をすり抜け、8月3日になっていた。
    """
    from datetime import date
    from collector.models import extract_held_date
    for t in ("【募集】8/31まで作品を受け付けます", "【募集】8/9まで受付"):
        assert extract_held_date(t, date(2026, 7, 1)) is None, t


def test_bracket_without_a_date_is_untouched():
    """【】で始まるタイトルは実データに24件ある。日付が無いものを壊さない。"""
    from datetime import date
    from collector.models import extract_held_date
    for t in ("【要申込】夏休みこども木工教室",
              "【第57回浜田市美術展】　現代美術の部　事前相談を受け付けます",
              "【石見神楽】津和野夜神楽公演　次回9/19(土)公演",   # 冒頭ではない
              "【お知らせ】2026/8/1 サイトを更新しました"):       # 年つきは対象外
        assert extract_held_date(t, date(2026, 7, 1)) is None, t


# --- 【】の中にスラッシュ日付がある型（2026-08 / 川本町観光協会）-----------
# 10通り目の日付表記。承認者がタイトルの月日だけを見て2025年の記事を
# 今年の催しと誤認した事故（【12/20開催】島根フィルティーズ ファン感謝祭・
# 【11/14,15開催】弓ヶ峯八幡宮「秋の例大祭」）を受けて対応した。
# 8つ目（【】の後ろ）とは逆で、日付が【】の中にある。
# 実データ（approved/rejected/manual/skipped 全件）で測って34件ヒット、
# 他の情報源には無い（川本町観光協会のみ）。既に date_start があるもの
# （本文・見出しから取得ずみ）との食い違いは0件。

def test_bracket_inner_slash_date():
    from datetime import date
    from collector.models import extract_held_date
    cases = [
        ("【12/20開催】島根フィルティーズ　ファン感謝祭！！",
         date(2025, 12, 12), date(2025, 12, 20)),
        # カンマ区切りの複数日（初日だけを開催日にする）
        ("【11/14,15開催】弓ヶ峯八幡宮「秋の例大祭」",
         date(2025, 10, 21), date(2025, 11, 14)),
        # 「開催」の直後に他の語が続いても止まらない
        ("【1/12開催・町民向け】第4回川本町新春ふるさとカルタ大会",
         date(2025, 12, 4), date(2026, 1, 12)),
        # 曜日カッコが挟まっても取れる（天領さんと同型）
        ("【第44回 天領さん（久手会場）8/4（火）開催のお知らせ】",
         date(2026, 7, 1), date(2026, 8, 4)),
    ]
    for title, ref, want in cases:
        assert extract_held_date(title, ref) == want, title


def test_bracket_inner_date_needs_kaisai():
    """「開催」以外の語（更新日など）には当たらない。

    「イズモコバイモQ&A（よくある質問）【2/9更新】」で実際に確認した実例。
    「開催」を必須にしないと、更新日が開催日として拾われる。
    """
    from datetime import date
    from collector.models import extract_held_date
    for t in ("イズモコバイモQ&A（よくある質問）【2/9更新】",
              "【見頃終了】長江寺のイチョウ色づき情報【12/5更新終了】"):
        assert extract_held_date(t, date(2026, 2, 9)) is None, t


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
