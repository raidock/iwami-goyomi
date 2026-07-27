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
