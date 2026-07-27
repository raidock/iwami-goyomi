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


def test_category_prefers_title_over_description():
    """説明文の「石見神楽」に引っ張られない（実画面で ぶどうまつり が神楽になった）。"""
    from collector.classify import classify
    v = classify("ぶどうまつり", "石見神楽の上演もあります")
    assert v.category == "祭り・市・マルシェ", v.category
    v2 = classify("今月のお知らせ", "陶芸教室を開催します")
    assert v2.category is not None


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
