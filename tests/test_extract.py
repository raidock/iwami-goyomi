"""詳細ページからの日付抽出テスト。

実際に取得したページの構造を再現している。
- 江津 Go-Con2026: 見出しで区切られ、1ページに日付が7個ある
- 浜田 石央ふれあい余芸大会: 見出しがなく流し込み
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from datetime import date

from collector.extract import (TITLE_SOURCE, Extracted, apply_extracted,
                               drop_reversed_period, extract_dates)
from collector.models import Event

# 江津市 Go-Con2026（2026年5月18日掲載）の構造。日付が7個ある。
GOTSU_GOCON = """
<article>
  <p>掲載日：2026年5月18日更新</p>
  <h2>江津市ビジネスプランコンテスト（通称：Go-Con）の応募を開始します</h2>
  <h3>Go-Conの概要</h3>
  <h4>募集テーマ</h4>
  <p>江津市の課題解決につながるプロダクトやサービス</p>
  <h3>申し込み方法</h3>
  <h4>提出期限</h4>
  <p>8月3日（月曜日）</p>
  <p>正午必着</p>
  <h3>選考スケジュール</h3>
  <h4>公募期間</h4>
  <p>5月18日（月曜日）～8月3日（月曜日）</p>
  <h4>一次審査結果の通知</h4>
  <p>8月末頃を予定しています。</p>
  <h4>ブラッシュアップ勉強会について</h4>
  <p>9月28日（月曜日） 10月19日（月曜日） 11月16日（月曜日）</p>
  <h4>最終審査会（公開プレゼンテーション）</h4>
  <p>12月6日（日曜日）</p>
</article>
"""

# 浜田市 石央ふれあい余芸大会（2026年6月19日掲載）。見出しなしの流し込み。
HAMADA_YOGEI = """
<div>
  <p>登録日：2026年6月19日</p>
  <p>石央ふれあい余芸大会に出演してみませんか？</p>
  <p>12月13日（日） 午後1時～</p>
  <p>石央文化ホール</p>
  <p>7月31日（金）までに浜田ライオンズクラブ事務局へ TEL:0855-22-3759</p>
</div>
"""

# 表組みで日時が書かれている、よくある形
TABLE_STYLE = """
<table>
  <tr><th>日時</th><td>2026年9月13日（日曜日）午前10時から</td></tr>
  <tr><th>会場</th><td>浜田市世界こども美術館</td></tr>
  <tr><th>申込締切</th><td>2026年8月29日（金曜日）</td></tr>
</table>
"""

# 日付が1つもないページ（拾えないことを確認する）
NO_DATE = "<div><p>出前講座をご利用ください。ご希望の団体は担当課へご連絡ください。</p></div>"

# 浜田市「救命講習定期開催のお知らせ」（2026年7月23日掲載）の表。
# 見出しセルが th ではなく td。日付は和暦。前2回はすでに終了している。
HAMADA_KYUMEI = """
<div>
  <p>登録日：2026年7月23日</p>
  <table>
    <tr><td>講習種別</td><td>講習日時</td><td>会場</td><td>定員</td><td>申込 状況</td><td>申込方法</td></tr>
    <tr><td>普通救命講習Ⅰ</td><td>令和8年5月16日（土） 9：30～12：30</td><td>消防本部</td><td>24人</td><td>終了</td><td>電話またはFAX</td></tr>
    <tr><td>普通救命講習Ⅰ</td><td>令和8年7月15日（水） 13：30～16：30</td><td>消防本部</td><td>24人</td><td>終了</td><td>電話またはFAX</td></tr>
    <tr><td>普通救命講習Ⅰ</td><td>令和8年9月12日（土） 9：30～12：30</td><td>消防本部</td><td>24人</td><td>〇</td><td>電話またはFAX</td></tr>
    <tr><td>普通救命講習Ⅰ</td><td>令和8年11月18日（水） 13：30～16：30</td><td>消防本部</td><td>24人</td><td>〇</td><td>電話またはFAX</td></tr>
    <tr><td>普通救命講習Ⅰ</td><td>令和9年1月16日（土） 9：30～12：30</td><td>消防本部</td><td>24人</td><td>〇</td><td>電話またはFAX</td></tr>
    <tr><td>普通救命講習Ⅰ</td><td>令和9年3月17日（水） 13：30～16：30</td><td>消防本部</td><td>24人</td><td>〇</td><td>電話またはFAX</td></tr>
  </table>
</div>
"""

# 浜田市「山陰浜田港お魚料理教室」（2026年7月22日掲載）の表。
# 年が書かれておらず、第1回は掲載日より前に終わっている。
HAMADA_OSAKANA = """
<div>
  <p>登録日：2026年7月22日</p>
  <table>
    <tr><td></td><td>開催日</td><td>時間</td><td>会場</td><td>申込期間</td><td>備考</td></tr>
    <tr><td>第1回</td><td>6月20日(土)</td><td>10:00～13:00</td><td>総合福祉センター</td><td>4月22日～5月22日</td><td></td></tr>
    <tr><td>第2回</td><td>7月18日(土)</td><td>16:00～19:00</td><td>いわみーる</td><td>5月20日～6月19日</td><td>特別講師</td></tr>
    <tr><td>第3回</td><td>8月22日(土)</td><td>10:00～13:00</td><td>総合福祉センター</td><td>6月19日～7月24日</td><td>親子料理教室</td></tr>
    <tr><td>第4回</td><td>9月16日(水)</td><td>10:00～13:00</td><td>総合福祉センター</td><td>7月22日～8月21日</td><td></td></tr>
    <tr><td>第5回</td><td>11月19日(木)</td><td>10:00～13:00</td><td>総合福祉センター</td><td>9月18日～10月23日</td><td></td></tr>
    <tr><td>第6回</td><td>12月19日(土)</td><td>9:00～13:00</td><td>総合福祉センター</td><td>10月21日～11月20日</td><td></td></tr>
    <tr><td>第7回</td><td>1月20日(水)</td><td>10:00～13:00</td><td>総合福祉センター</td><td>11月19日～12月18日</td><td></td></tr>
    <tr><td>第8回</td><td>2月18日(木)</td><td>10:00～13:00</td><td>総合福祉センター</td><td>12月22日～1月22日</td><td></td></tr>
  </table>
</div>
"""


def test_gotsu_picks_teishutsu_kigen_not_publication_date():
    """7個ある日付から「提出期限」の8月3日を選ぶ。掲載日5/18ではない。"""
    got = extract_dates(GOTSU_GOCON, ref=date(2026, 5, 18))
    assert got.deadline == date(2026, 8, 3), f"締切が違う: {got.deadline}"
    assert "提出期限" in got.deadline_source, got.deadline_source


def test_gotsu_does_not_pick_kenshu_dates_as_deadline():
    """勉強会(9/28)や結果通知(8月末)を締切と誤認しない。"""
    got = extract_dates(GOTSU_GOCON, ref=date(2026, 5, 18))
    assert got.deadline not in (date(2026, 9, 28), date(2026, 10, 19))


def test_hamada_flowing_text_gets_both():
    """見出しがない流し込みでも、開催日と締切を取り分ける。"""
    got = extract_dates(HAMADA_YOGEI, ref=date(2026, 6, 19))
    assert got.date_start == date(2026, 12, 13), f"開催日が違う: {got.date_start}"
    assert got.deadline == date(2026, 7, 31), f"締切が違う: {got.deadline}"


def test_table_style():
    got = extract_dates(TABLE_STYLE, ref=date(2026, 7, 1))
    assert got.date_start == date(2026, 9, 13), got.date_start
    assert got.deadline == date(2026, 8, 29), got.deadline


def test_table_columns_pick_next_session_not_the_first():
    """終わった回を飛ばして次回を選ぶ。5/16・7/15は終了済み。"""
    got = extract_dates(HAMADA_KYUMEI, ref=date(2026, 7, 23), today=date(2026, 7, 28))
    assert got.date_start == date(2026, 9, 12), f"次回が違う: {got.date_start}"
    assert got.session_count == 6, f"回数が違う: {got.session_count}"


def test_table_columns_do_not_set_date_end():
    """飛び石の6日間を「9月12日〜翌3月17日」と期間にしない（6か月続くと誤解される）。"""
    got = extract_dates(HAMADA_KYUMEI, ref=date(2026, 7, 23), today=date(2026, 7, 28))
    assert not hasattr(got, "date_end") or getattr(got, "date_end", None) is None


def test_table_columns_advance_as_sessions_pass():
    """今日が進めば次回も進む。全部過ぎたら最後の回を残す（勝手に消さない）。"""
    kw = dict(ref=date(2026, 7, 23))
    assert extract_dates(HAMADA_KYUMEI, today=date(2026, 9, 13), **kw).date_start \
        == date(2026, 11, 18)
    assert extract_dates(HAMADA_KYUMEI, today=date(2026, 9, 12), **kw).date_start \
        == date(2026, 9, 12), "当日は「次回」に含める"
    last = extract_dates(HAMADA_KYUMEI, today=date(2027, 6, 1), **kw)
    assert last.date_start == date(2027, 3, 17), "全部過ぎたら最後の回"


def test_table_without_year_reads_sessions_in_order():
    """年が無い列は「前の行より前に戻ったら翌年」と読む。

    掲載日基準の _to_date だけだと、掲載(7/22)より前に終わった第1回 6月20日を
    2027年と誤読し、回数も次回もずれる。
    """
    got = extract_dates(HAMADA_OSAKANA, ref=date(2026, 7, 22), today=date(2026, 7, 28))
    assert got.date_start == date(2026, 8, 22), f"次回が違う: {got.date_start}"
    assert got.session_count == 8, f"回数が違う: {got.session_count}"


def test_table_column_source_is_recorded():
    got = extract_dates(HAMADA_OSAKANA, ref=date(2026, 7, 22), today=date(2026, 7, 28))
    assert "開催日" in got.date_source and "全8回" in got.date_source, got.date_source


def test_vertical_table_still_uses_the_heading_path():
    """縦組みの表（th|td の2列）は従来どおり。回数は付けない。"""
    got = extract_dates(TABLE_STYLE, ref=date(2026, 7, 1), today=date(2026, 7, 1))
    assert got.date_start == date(2026, 9, 13)
    assert got.deadline == date(2026, 8, 29)
    assert got.session_count is None, "単発の催しに回数が付いた"


def test_multi_session_table_does_not_invent_a_deadline():
    """行ごとに違う「申込期間」を、催し全体の締切として取らない。

    お魚料理教室は回ごとに申込期間が別。列の最後（1月22日）を締切にすると、
    次回(8/22)の申込とは無関係の日付が出る。
    """
    got = extract_dates(HAMADA_OSAKANA, ref=date(2026, 7, 22), today=date(2026, 7, 28))
    assert got.deadline is None, f"無関係の締切を拾った: {got.deadline}（{got.deadline_source}）"


# はまナビ「どんちっちはまだ!スタンプラリー2026」（2026年7月21日掲載）。
# 【実施・応募期間】は、催しが8/1から12/15まで続き、応募もその日までという意味。
HAMANAVI_STAMP = """
<div>
  <p>スタンプ数に応じて抽選で総勢30名様に素敵な賞品が当たります！</p>
  <p>【実施・応募期間】 2026年8月1日（土）～12月15日（火）17：45まで</p>
  <p>【参加費】 無料</p>
  <p>【スタンプ設置施設】 全12ヶ所</p>
</div>
"""


# 浜田市の全ページ共通のフッター。32ページ中14ページで
# 「開庁時間」が日付を含む見出し節として拾われていた。
HAMADA_FOOTER = """
<div>
  <h3>開催日時</h3><p>2026年9月13日（日曜日）午前10時から</p>
  <div class="footer-content">
    <dl><dt>開庁時間</dt>
        <dd>月曜日～金曜日 （土曜日・日曜日・祝日及び12月29日～1月3日は閉庁）</dd></dl>
  </div>
  <div id="gnav"><a>12月1日 イベント一覧</a></div>
  <p class="footer-copyright">Copyright © Hamada City</p>
</div>
"""


def test_footer_and_nav_are_stripped_by_class():
    """枠の日付を拾わない。本文の日付は残る。"""
    got = extract_dates(HAMADA_FOOTER, ref=date(2026, 8, 1), today=date(2026, 8, 1))
    assert got.date_start == date(2026, 9, 13), f"本文の日付が消えた: {got.date_start}"
    assert got.deadline is None, f"枠から締切を拾った: {got.deadline}"


def test_stripping_matches_word_starts_not_substrings():
    """「innovation」を nav と読んで消さない（部分一致にしない）。"""
    html = ("<div class='innovation-section'>"
            "<h3>日時</h3><p>2026年9月13日（日曜日）</p></div>")
    got = extract_dates(html, ref=date(2026, 8, 1), today=date(2026, 8, 1))
    assert got.date_start == date(2026, 9, 13), "innovation を消してしまった"


def test_header_named_elements_are_kept():
    """header は除去しない。

    江津市の main_header には記事タイトルそのものが入る。タイトルに開催日を
    書く情報源があり（はまナビ「8月22日（土）有福温泉…」）、
    節の見出しを指す名前（section-header）も一般的。実測でも益がなかった。
    """
    html = ("<div class='main_header'><h1>夏祭りを開催します</h1></div>"
            "<div class='content_header'><h3>日時</h3><p>2026年9月13日</p></div>")
    got = extract_dates(html, ref=date(2026, 8, 1), today=date(2026, 8, 1))
    assert got.date_start == date(2026, 9, 13), "header を消して日付が取れなくなった"


# 大田市観光協会（ginzan-wm.jp）の実ページの構造。記事の下に「ほかの催し」の
# 一覧が div#sub_events_area で置かれ、他記事の見出しがそのまま入っている。
# 中の「【7月4日～8月30日まで】…」を締切として拾い、**全記事に同じ 2026-08-30**が
# 付いていた（4件中3件。残る1件は本文に本物の締切があり、そちらが先に当たっていた）。
GINZAN_SUB_EVENTS = """
<div id="main_content">
  <h1>島根の観光ビジネスを学ぶ！山陰ツーリズム人材育成塾</h1>
  <span><b>募集期間</b>：2026年6月25日（木）～ 7月17日（金）</span>
</div>
<div id="sub_events_area">
  <p class="events_order">※開催日順で掲載</p>
  <div class="event_box">
    <div class="txt">
      <p class="event_date">2026.7.4 - 8.30</p>
      <h3><a href="/events_post/kaigarashi-gurasuart/">【7月4日～8月30日まで】渚にほどける
          貝殻シーグラスアート作家 井上 麻菜美 個展</a></h3>
    </div>
  </div>
</div>
"""


def test_related_events_list_does_not_become_a_deadline():
    """関連記事一覧の日付を本文の日付と取り違えない。"""
    got = extract_dates(GINZAN_SUB_EVENTS, ref=date(2026, 6, 25), today=date(2026, 6, 25))
    assert got.deadline == date(2026, 7, 17), f"本物の締切が取れていない: {got.deadline}"
    assert got.deadline != date(2026, 8, 30), "ほかの催しの日付を締切にした"


def test_related_events_list_is_stripped_even_without_a_real_date():
    """本文に日付が無いページで、関連記事一覧から偽の締切を作らない。

    実際にはこちらが多数派だった（お知らせ記事に日付が無く、一覧だけがある）。
    """
    html = GINZAN_SUB_EVENTS.replace(
        "<span><b>募集期間</b>：2026年6月25日（木）～ 7月17日（金）</span>", "")
    got = extract_dates(html, ref=date(2026, 6, 25), today=date(2026, 6, 25))
    assert got.deadline is None, f"偽の締切が付いた: {got.deadline}"
    assert got.date_start is None, f"偽の開催日が付いた: {got.date_start}"


def test_sidebar_is_not_a_removal_word():
    """sidebar は除去語にしない。**入れると本文が丸ごと消える。**

    江津市観光協会は記事本文を包む div に `-sidebar-on` という状態クラスを
    付けている（サイドバー有りのレイアウト、の意）。実データで測ったところ、
    sidebar を除去語に足すと公開中の45件のうち5件で開催日が消えた。
    header を入れなかったのと同じ理由。**枠の名前と、枠の有無を示す名前は違う。**
    """
    html = ("<div class='l-container -sidebar-on'>"
            "<h3>日時</h3><p>2026年7月18日（土）10:00～</p></div>"
            "<aside class='l-sidebar'><p>2026年12月1日 バックナンバー</p></aside>")
    got = extract_dates(html, ref=date(2026, 6, 1), today=date(2026, 6, 1))
    assert got.date_start == date(2026, 7, 18), f"本文が消えた: {got.date_start}"


def test_fullwidth_space_in_the_label():
    """江津市観光協会は【日　時】と全角空白で字間を空ける。

    そのままだと「日時」に一致せず、開催日を1件も取れなかった。
    （江津駅前夜市場「夏祭り」。ページは（日）と書いているが2026-07-20は
    月曜＝海の日で、ページ側の曜日表記の誤り。日付はタイトルのR8.7.20と一致）
    """
    html = "<div><p>【日　時】2026年7月20日（日）17:00～21:00</p></div>"
    got = extract_dates(html, ref=date(2026, 6, 12), today=date(2026, 6, 12))
    assert got.date_start == date(2026, 7, 20), f"取れていない: {got.date_start}"


def test_kaisai_gappi_heading():
    """浜田市 一斉相談会の【開催月日】。「開催日」には部分一致しない。"""
    html = "<div><p>【開催月日】 2026年9月11日（金）</p><p>【場所と時間】浜田会場</p></div>"
    got = extract_dates(html, ref=date(2026, 7, 1), today=date(2026, 7, 1))
    assert got.date_start == date(2026, 9, 11), f"取れていない: {got.date_start}"


def test_jisshibi_heading():
    """浜田市 危険物取扱者保安講習の「対面講習の実施日・会場」。"""
    html = ("<div><h3>対面講習の実施日・会場</h3>"
            "<p>9月10日 (木)　浜田市下府町327番地114 島根県トラック協会</p></div>")
    got = extract_dates(html, ref=date(2026, 7, 16), today=date(2026, 7, 16))
    assert got.date_start == date(2026, 9, 10), f"取れていない: {got.date_start}"


def test_bare_kikan_is_an_event_period():
    """修飾語のない【期間】は開催期間（はまナビ 海開き）。"""
    html = ("<div><p>【期間】 2026年7月18日（土）～8月23日（日）</p>"
            "<p>【場所】 石見海浜公園 姉ヶ浜海水浴場</p></div>")
    got = extract_dates(html, ref=date(2026, 7, 14), today=date(2026, 7, 14))
    assert got.date_start == date(2026, 7, 18), f"開始が違う: {got.date_start}"
    assert got.date_end == date(2026, 8, 23), f"終わりが違う: {got.date_end}"


def test_qualified_kikan_is_still_not_an_event_period():
    """修飾語が付く「期間」は開催期間にしない。

    裸の「期間」だけを開催期間として扱う根拠は、実ページ32件で数えた結果
    応募の窓・雇用期間がすべて修飾語付きだったこと。ここが崩れると
    段階2で作った PERIOD_HEADS との区別も壊れる。
    """
    for label in ("募集期間", "公募期間", "申込期間", "雇用形態・期間"):
        html = f"<div><p>【{label}】 2026年7月1日～8月28日</p></div>"
        got = extract_dates(html, ref=date(2026, 6, 20), today=date(2026, 6, 20))
        assert got.date_start is None, f"「{label}」を開催日にした: {got.date_start}"


def test_kikan_is_not_added_to_held_heads():
    """「期間」を HELD_HEADS に入れると「募集期間」にも部分一致してしまう。"""
    from collector.extract import HELD_HEADS
    assert "期間" not in HELD_HEADS


def test_per_school_schedule_is_left_alone():
    """学校別の一覧は1つの日付に潰さない（段階1の複数日と同じ問題）。"""
    html = ("<div><h3>各小学校の健康診断日程</h3>"
            "<p>郷田小学校 10月22日(木曜日) 高角小学校 10月23日(金曜日)</p></div>")
    got = extract_dates(html, ref=date(2026, 7, 21), today=date(2026, 7, 21))
    assert got.date_start is None, f"学校別の日程を開催日にした: {got.date_start}"


# 浜田市「山陰浜田港お魚料理教室の開催について（受講者募集）」（2026年7月22日掲載）。
# 全角と半角が混ざり、締切の時刻に「分」まで書かれている。
# 締切として拾えず、開催日として自動公開されていた（2026-07 の実物で発見）。
HAMADA_OSAKANA_BOSHU = """
<div>
  <p>登録日：2026年7月22日</p>
  <p>◆日にち：令和８ 年９月１６日（水）</p>
  <p>◆時間：１０：００～１３：００</p>
  <p>◆申込締切：８ 月２1 日（金） 午後５時１５分まで</p>
</div>
"""

# 浜田市 世界こども美術館の企画展。「会期」は見出し要素として置かれている。
HAMADA_KAIKI = """
<div>
  <p>登録日：2026年6月30日</p>
  <strong>会期</strong>
  <p>7月4日（土）～９月27日（日）午前９時30分～午後5時
     休館日：毎週月曜日（但し7/20、8/10、9/21は開館）、7/21（火）、9/24（木）</p>
</div>
"""


def test_deadline_with_minutes_is_a_deadline_not_an_event_date():
    """「午後５時１５分まで」を締切として読む。

    分を許していなかったため締切に一致せず、代わりに _HELD_TAIL の
    「午後◯時」に当たって開催日として自動公開されていた。
    """
    got = extract_dates(HAMADA_OSAKANA_BOSHU, ref=date(2026, 7, 22),
                        today=date(2026, 7, 28))
    assert got.deadline == date(2026, 8, 21), f"締切が取れていない: {got.deadline}"
    assert got.date_start != date(2026, 8, 21), "締切を開催日にしている"


def test_kaiki_heading_is_an_event_period():
    """「会期」は催しが続く期間。始まりが開催日、終わりが date_end。"""
    got = extract_dates(HAMADA_KAIKI, ref=date(2026, 6, 30), today=date(2026, 7, 28))
    assert got.date_start == date(2026, 7, 4), f"会期の始まりが違う: {got.date_start}"
    assert got.date_end == date(2026, 9, 27), f"会期の終わりが違う: {got.date_end}"


def test_kaiki_survives_until_the_end_of_the_period():
    """会期の途中なら「これから」に残る（期間ものは終わりの日で見る）。"""
    from collector.models import Event
    from collector.publish import is_past
    got = extract_dates(HAMADA_KAIKI, ref=date(2026, 6, 30), today=date(2026, 7, 28))
    ev = _ev(date_start=got.date_start, date_end=got.date_end)
    ev.kind = "催し"
    assert not is_past(ev, date(2026, 7, 28)), "開催中なのに終了扱いになった"
    assert is_past(ev, date(2026, 9, 28)), "会期を過ぎても終了にならない"


def test_kaiki_is_not_left_in_period_event_words():
    """会期は PERIOD_EVENT_WORDS では一度も一致しない（死にコードだった）。"""
    from collector.extract import PERIOD_EVENT_WORDS, _is_event_period
    assert "会期" not in PERIOD_EVENT_WORDS
    assert _is_event_period("会期"), "会期が期間として扱われていない"


def test_period_heading_gives_both_the_start_and_the_deadline():
    """「実施・応募期間」から開始日と締切の両方を取る。

    if/elif で排他にしていたため、締切に消費されて開始日8/1が捨てられていた。
    """
    got = extract_dates(HAMANAVI_STAMP, ref=date(2026, 7, 21), today=date(2026, 7, 28))
    assert got.date_start == date(2026, 8, 1), f"開始日が取れていない: {got.date_start}"
    assert got.date_end == date(2026, 12, 15), f"終わりが違う: {got.date_end}"
    assert got.deadline == date(2026, 12, 15), f"締切が違う: {got.deadline}"


def test_koubo_kikan_is_not_an_event_period():
    """「公募期間」は応募の受付窓であって開催期間ではない。

    Go-Con の公募期間 5/18〜8/3 を開催日にすると、催しが5月に始まったことになる。
    """
    got = extract_dates(GOTSU_GOCON, ref=date(2026, 5, 18))
    assert got.date_start != date(2026, 5, 18), "公募期間の始まりを開催日にした"
    assert got.date_end is None, f"公募期間を開催期間にした: {got.date_end}"
    assert got.deadline == date(2026, 8, 3), "締切は従来どおり取れること"


def test_boshu_kikan_on_an_event_is_not_the_event_date():
    """種別が「催し」でも、募集期間の始まりは開催日ではない。

    さざんか祭り（開催10/31）に【募集期間】7/1〜8/28 があっても、
    date_start=7/1 にしてはいけない。日付の意味は見出しが決める。
    """
    html = ("<div><p>さざんか祭りを開催します</p>"
            "<p>【募集期間】 2026年7月1日～8月28日</p></div>")
    got = extract_dates(html, ref=date(2026, 6, 20), today=date(2026, 7, 28))
    assert got.date_start is None, f"募集期間を開催日にした: {got.date_start}"
    assert got.deadline == date(2026, 8, 28)


def test_deadline_note_is_hidden_when_it_equals_the_period_end():
    """期間の終わりと締切が同じ日なら、締切の注記を二重に出さない。"""
    from collector.publish import _deadline_note
    ev = _ev(date_start=date(2026, 8, 1), date_end=date(2026, 12, 15))
    ev.kind, ev.deadline = "催し", date(2026, 12, 15)
    assert _deadline_note(ev, date(2026, 7, 28)) == "", "締切が二重に出ている"
    ev.deadline = date(2026, 8, 20)          # 別の日なら出す
    assert "8/20" in _deadline_note(ev, date(2026, 7, 28))


def test_deadline_tag_is_hidden_when_it_equals_the_period_end():
    """「締切あり」タグも注記と同じ条件で出さない（判断の一貫性）。

    「渚にほどける…個展」の 8/30 はタイトルの「8月30日まで」由来で会期の終わり。
    7月4日〜8月30日と出ているカードに「締切あり」が付いていた。
    """
    from collector.publish import _card
    ev = _ev(date_start=date(2026, 7, 4), date_end=date(2026, 8, 30))
    ev.kind, ev.deadline, ev.tags = "催し", date(2026, 8, 30), ["締切あり"]
    assert "締切あり" not in _card(ev, date(2026, 7, 30)), "会期末に締切タグが付いている"
    ev.deadline = date(2026, 8, 1)            # 本当の申込締切なら出す
    assert "締切あり" in _card(ev, date(2026, 7, 30))
    ev.tags = ["要申込", "締切あり"]           # 他のタグは消さない
    ev.deadline = date(2026, 8, 30)
    assert "要申込" in _card(ev, date(2026, 7, 30))


def test_empty_category_does_not_leave_a_dot():
    """カテゴリが空のとき中黒を出さない（「大田市 ・掲載 …」と浮いていた）。"""
    from collector.publish import _card
    ev = _ev(date_start=date(2026, 8, 29))
    ev.city, ev.category, ev.published_at = "大田市", None, date(2026, 7, 22)
    html = _card(ev, date(2026, 7, 30))
    assert ">・掲載" not in html, "中黒が浮いている"
    assert "掲載 2026/07/22" in html
    ev.category = "学び・講座"                 # あるときは従来どおり
    assert "学び・講座・掲載 2026/07/22" in _card(ev, date(2026, 7, 30))


def _ev(**kw):
    base = dict(title="t", prefecture="島根県", date_start=None, date_end=None,
                url="https://example.invalid/x", source="hamanavi")
    base.update(kw)
    return Event(**base)


def test_title_date_is_not_overwritten_by_the_body():
    """タイトル由来の開催日は本文抽出に譲らない。

    タイトルの日付は書いた人が記事の主題として選んだもの。本文には関連する
    日付が何個も混ざる（Go-Conは1ページに7個）。設計判断10と同じ理屈。
    """
    ev = _ev(date_start=date(2026, 8, 22))
    ev.date_source = TITLE_SOURCE
    body = extract_dates(HAMADA_YOGEI, ref=date(2026, 6, 19))
    assert body.date_start == date(2026, 12, 13), "前提が変わっている"
    apply_extracted(ev, body)
    assert ev.date_start == date(2026, 8, 22), f"タイトルの日付が消えた: {ev.date_start}"
    assert ev.date_source == TITLE_SOURCE
    assert ev.deadline == date(2026, 7, 31), "締切は本文から取ってよい"


def test_body_date_is_used_when_the_title_had_none():
    """タイトルに日付が無ければ、従来どおり本文から取る。"""
    ev = _ev()
    apply_extracted(ev, extract_dates(HAMADA_YOGEI, ref=date(2026, 6, 19)))
    assert ev.date_start == date(2026, 12, 13)
    assert ev.date_source == "本文「…時〜/開催」"


def test_no_date_returns_nothing():
    got = extract_dates(NO_DATE, ref=date(2026, 7, 10))
    assert got.date_start is None and got.deadline is None


# ginzan-wm.jp 夏休みイベント第2弾の実ページ。終わりの「8月31（金）」は
# **日が抜けていて**日付として読めない。そのため同じ節の最後の日付である
# 注記の「8月17日」が終わりに採られ、公開画面に「8月18日（火）〜8月17日」と出た。
GINZAN_REVERSED_PERIOD = """
<div id="main_content">
  <h3><span style="font-family: arial;">■ 開催期間</span></h3>
  <ul><li><p><span style="font-family: arial;">2026年8月18日（火）～ 8月31（金）
    ※8月10日～8月17日の期間中は開催いたしませんのでご注意ください。</span></p></li></ul>
  <h3><span>■ イベント詳細</span></h3>
  <ul><li><p>受付時間 ：09:00 ～ 15:00　料金 ：1個 1,500円</p></li></ul>
</div>
"""


# 同じページ（ginzan-wm.jp 夏休みイベント第1弾）の2つの書き方。
# 人手の本文は第1弾・第2弾・注記を1つの節にまとめて書くので、節の最後の日付
# （注記の8月17日）を終わりに採ると8日ずれる。テンプレートが出す period_box は崩れない。
GINZAN_DECLARED_PERIOD = """
<div id="main_content">
  <div class="period_box"> <span>イベント期間</span>2026年07月18日(土) ～ 08月09日(日) </div>
  <h3><span style="font-family: arial;">■ 開催期間</span></h3>
  <ul>
    <li><p><span>2026年7月18日（土）～ 8月9日（日）第1弾</span></p></li>
    <li><p><span>2026年8月18日（火）～ 8月31日（月）第2弾<br/>
      ※8月10日～8月17日の期間中は開催いたしませんのでご注意ください。</span></p></li>
  </ul>
</div>
"""

# 江津市観光協会。<time datetime> は**記事の掲載日**であって催しの期間ではない。
# これを構造化された期間として読むと、7件すべての開催日が掲載日に化ける。
GOTSU_KANKO_POST_TIME = """
<div>
  <h1 class="c-postTitle">キッズフェス in GOTSU（2026.7.18開催）</h1>
  <time datetime="2026-07-08" class="c-postTitle__date u-thin">2026 7/08</time>
  <p>【日　時】2026年7月18日（土）10:00～15:00</p>
</div>
"""


# 大田市「第４４回「天領さん」」の実ページ。見出しタグも【】も使わず、
# <p> の中に「〇日　時」と記号つきの平文ラベルで書いている。
# 層1に届かず、大田市最大の夏祭りが「日程は詳細ページで」のまま公開された。
ODA_TENRYO = """
<div id="main_content">
  <p>第４４回「天領さん」は以下のとおり開催されます</p>
  <p>大田会場「大田会場チラシ」をダウンロードする（JPG：679kB）</p>
  <p>〇日　時　　2026年８月１日（土）　１３：００～２１：００<br>
     〇場　所　　大田市民会館駐車場<br>
     〇内　容　　１３：００　ウォーターサバゲー、屋台村</p>
  <p>久手会場（港まつり）</p>
  <p>〇日　時　　2026年８月４日（火）　１７：３０～２１：３０<br>
     〇場　所　　久手港周辺</p>
  <p>大森会場</p>
  <p>〇日　時　　2026年８月３０日（日）　１０：００～１５：００<br>
     〇場　所　　石見銀山世界遺産センター</p>
</div>
"""

# 浜田市「お魚料理教室（受講者募集）」の実ページ。◆ラベルで書かれている。
# 8月21日は**申込締切**であって開催日ではない（開催日は9月16日）。
# 以前ここで「午後５時１５分まで」を開催日として拾い、自動公開する事故を起こした。
HAMADA_SAKANA = """
<div>
  <p>◆日にち：2026年９月１６日（水）</p>
  <p>◆時間：１０：００～１３：００</p>
  <p>◆申込締切：８ 月２1 日（金） 午後５時１５分まで</p>
  <p>◆申込先・問合せ先：浜田市水産業振興協会</p>
</div>
"""


def test_marked_plain_label_is_read_as_a_section():
    """記号つきの平文ラベル「〇日　時」を見出しと同じに扱う。"""
    got = extract_dates(ODA_TENRYO, ref=date(2026, 6, 17), today=date(2026, 6, 17))
    assert got.date_start == date(2026, 8, 1), got.date_start
    assert "日時" in got.date_source, got.date_source


def test_repeated_labels_take_the_next_future_date():
    """同じラベルの節が複数あるなら、今日以降でいちばん早い日を採る。

    天領さんは3会場を「〇日 時」で3つ並べる（大田8/1・久手8/4・大森8/30）。
    先頭だけを採ると、8/2 には 8/1 が過去になって「終わった催し」に畳まれ、
    まだ残っている久手8/4・大森8/30 ごと消える。
    """
    ref = date(2026, 6, 17)
    for today, want in ((date(2026, 7, 30), date(2026, 8, 1)),
                        (date(2026, 8, 1), date(2026, 8, 1)),
                        (date(2026, 8, 2), date(2026, 8, 4)),
                        (date(2026, 8, 5), date(2026, 8, 30)),
                        (date(2026, 8, 31), date(2026, 8, 30))):   # 全部過ぎたら最後の日
        got = extract_dates(ODA_TENRYO, ref=ref, today=today)
        assert got.date_start == want, f"{today} で {got.date_start}（期待 {want}）"
    got = extract_dates(ODA_TENRYO, ref=ref, today=date(2026, 7, 30))
    assert "ほか" in got.date_source, got.date_source


def test_single_label_is_unchanged():
    """節が1つなら従来どおり（未来の日でなくてもその日を採る）。"""
    html = "<div><p>〇日　時　　2026年7月10日（金）　10：00～</p></div>"
    got = extract_dates(html, ref=date(2026, 6, 1), today=date(2026, 8, 1))
    assert got.date_start == date(2026, 7, 10), got.date_start
    assert "ほか" not in got.date_source, got.date_source


def test_period_sections_are_not_merged():
    """期間の節はこの経路に乗せない。注記の日付を拾ってしまうため。

    「■ 開催期間 …第1弾 …第2弾 ※8月10日～8月17日は開催しません」の節から
    最も早い未来の日を選ぶと、注記の 8/10 が開催日になる。
    """
    got = extract_dates(GINZAN_DECLARED_PERIOD, ref=date(2026, 6, 15),
                        today=date(2026, 7, 30))
    assert got.date_start == date(2026, 7, 18), got.date_start
    assert got.date_end == date(2026, 8, 9), got.date_end


def test_marked_label_requires_a_known_head():
    """記号だけでは節にしない。ラベル語を伴うときだけ（飾りを全部拾わない）。"""
    html = ("<div><p>〇内　容　１３：００　ウォーターサバゲー</p>"
            "<p>〇場　所　2026年8月1日の会場は市民会館</p></div>")
    got = extract_dates(html, ref=date(2026, 6, 17), today=date(2026, 6, 17))
    assert got.date_start is None, f"飾りを節にした: {got.date_source}"


def test_nakaguro_is_not_a_label_mark():
    """`・`（中黒）は記号に入れない。本文のあらゆる場所に出る。"""
    html = "<div><p>持ち物・日時のご案内は2026年8月1日に掲載します</p></div>"
    got = extract_dates(html, ref=date(2026, 6, 17), today=date(2026, 6, 17))
    assert got.date_start is None, f"中黒を節の印にした: {got.date_source}"


def test_deadline_label_does_not_become_the_held_date():
    """◆申込締切の日付を開催日にしない。

    層1で締切が取れると、層2で同じ日付が開催日の判定に落ちてきて
    「午後５時１５分まで」の「午後◯時」に当たっていた。
    """
    got = extract_dates(HAMADA_SAKANA, ref=date(2026, 7, 15), today=date(2026, 7, 15))
    assert got.deadline == date(2026, 8, 21), got.deadline
    assert got.date_start != date(2026, 8, 21), "締切が開催日になっている"


def test_24h_clock_after_a_date_means_held():
    """「10月3日（土）11：00～15：00」の24時間表記を開催の手がかりにする。"""
    html = "<div><p>〇開催日：2026年10月3日（土）11：00～15：00</p></div>"
    got = extract_dates(html, ref=date(2026, 6, 23), today=date(2026, 6, 23))
    assert got.date_start == date(2026, 10, 3), got.date_start


def test_24h_clock_before_made_means_deadline():
    """「7月28日（火）17：00までに」は締切。開催日にしない。

    24時間表記を開催側だけに足すと、締切が開催日に化ける。
    両方に足したうえで、層2が締切を先に見ることで順序を守っている。
    """
    html = "<div><p>7月28日（火）17：00までに、石州和紙会館までお申し込みください。</p></div>"
    got = extract_dates(html, ref=date(2026, 7, 1), today=date(2026, 7, 1))
    assert got.deadline == date(2026, 7, 28), got.deadline
    assert got.date_start is None, f"締切を開催日にした: {got.date_start}"
    # 半角コロンでも同じ
    html2 = html.replace("17：00", "17:15")
    got2 = extract_dates(html2, ref=date(2026, 7, 1), today=date(2026, 7, 1))
    assert got2.deadline == date(2026, 7, 28) and got2.date_start is None


def test_declared_period_beats_the_body():
    """サイトが宣言している期間を、人手の本文より優先する。"""
    got = extract_dates(GINZAN_DECLARED_PERIOD, ref=date(2026, 6, 15),
                        today=date(2026, 6, 15))
    assert got.date_start == date(2026, 7, 18), got.date_start
    assert got.date_end == date(2026, 8, 9), f"注記の日付を終わりにしている: {got.date_end}"
    assert "構造化された期間欄" in got.date_source, got.date_source


def test_declaration_without_dates_falls_through():
    """日付の入っていない宣言（実例「イベント期間 (木)」）は見出しに任せる。"""
    html = ("<div><div class='period_box'><span>イベント期間</span>(木)</div>"
            "<h3>開催日</h3><p>2026年7月2日（木）</p></div>")
    got = extract_dates(html, ref=date(2026, 6, 12), today=date(2026, 6, 12))
    assert got.date_start == date(2026, 7, 2), got.date_start
    assert got.date_source == "見出し「開催日」", got.date_source


def test_post_time_element_is_not_a_period():
    """`<time datetime>` を期間として読まない。**掲載日が開催日に化ける。**

    江津市観光協会は記事の掲載日を `<time datetime="2026-07-08"
    class="c-postTitle__date">` で持っている。構造化されていることと、
    それが催しの期間を指していることは別。
    """
    got = extract_dates(GOTSU_KANKO_POST_TIME, ref=date(2026, 7, 8),
                        today=date(2026, 7, 8))
    assert got.date_start == date(2026, 7, 18), f"掲載日を拾った: {got.date_start}"


def test_reversed_period_drops_the_end():
    """期間が逆転していたら終わりを捨てて単日にする（出口での検証）。"""
    got = extract_dates(GINZAN_REVERSED_PERIOD, ref=date(2026, 6, 15),
                        today=date(2026, 6, 15))
    assert got.date_start == date(2026, 8, 18), got.date_start
    assert got.date_end == date(2026, 8, 17), "前提が変わっている（注記を拾わなくなった）"
    ev = _ev()
    apply_extracted(ev, got)
    assert ev.date_start == date(2026, 8, 18), ev.date_start
    assert ev.date_end is None, f"逆転した終わりが残っている: {ev.date_end}"


def test_same_day_period_is_kept():
    """始まりと終わりが同じ日は捨てない（1日だけの催し）。"""
    ev = _ev()
    got = Extracted(date_start=date(2026, 8, 1), date_end=date(2026, 8, 1),
                    date_source="見出し「開催期間」")
    apply_extracted(ev, got)
    assert ev.date_end == date(2026, 8, 1), "同日を捨ててしまった"


def test_normal_period_is_untouched():
    """正常な期間は影響を受けない（スタンプラリー 8/1〜12/15）。"""
    ev = _ev()
    apply_extracted(ev, extract_dates(HAMANAVI_STAMP, ref=date(2026, 7, 21),
                                      today=date(2026, 7, 21)))
    assert ev.date_start == date(2026, 8, 1)
    assert ev.date_end == date(2026, 12, 15), ev.date_end


def test_reversed_period_is_dropped_even_without_extraction():
    """すでに持っている値が逆転していても捨てる（保存済みデータの検証）。"""
    ev = _ev(date_start=date(2026, 8, 18), date_end=date(2026, 8, 17))
    assert drop_reversed_period(ev) is True
    assert ev.date_end is None
    assert drop_reversed_period(ev) is False, "2度目は何もしない"


def test_source_is_recorded():
    """どこから取ったかが必ず残る（人が承認画面で誤りに気づけるように）。"""
    got = extract_dates(GOTSU_GOCON, ref=date(2026, 5, 18))
    assert got.deadline_source, "根拠が記録されていない"


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
    if ok == len(fns):
        g = extract_dates(GOTSU_GOCON, ref=date(2026, 5, 18))
        h = extract_dates(HAMADA_YOGEI, ref=date(2026, 6, 19))
        print(f"\n江津Go-Con : 締切={g.deadline}（{g.deadline_source}）")
        print(f"浜田余芸大会: 開催={h.date_start}（{h.date_source}） "
              f"締切={h.deadline}（{h.deadline_source}）")
    sys.exit(0 if ok == len(fns) else 1)
