"""詳細ページからの日付抽出テスト。

実際に取得したページの構造を再現している。
- 江津 Go-Con2026: 見出しで区切られ、1ページに日付が7個ある
- 浜田 石央ふれあい余芸大会: 見出しがなく流し込み
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from datetime import date

from collector.extract import extract_dates

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


def test_no_date_returns_nothing():
    got = extract_dates(NO_DATE, ref=date(2026, 7, 10))
    assert got.date_start is None and got.deadline is None


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
