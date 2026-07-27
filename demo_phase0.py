"""浜田市RSSの実データ（抜粋）でパイプライン全体を通す。

ネット接続なしで collect→仕分け→承認キュー→公開サイト生成 を検証する。
"""
import pathlib
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from collector.classify import classify
from collector.publish import to_public_site
from collector.review import ReviewQueue
from collector.sources.municipal_rss import MunicipalRSS

# 2026-07-27 に実際に取得した浜田市RSS（RSS 1.0 / RDF）の抜粋
FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
 xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns="http://purl.org/rss/1.0/" xml:lang="ja">
<channel rdf:about="x"><title>浜田市ホームページ</title><link>https://www.city.hamada.shimane.jp/</link>
<description>新着情報</description></channel>
{items}
</rdf:RDF>"""

REAL = [
    ("令和8年度（令和9年度等採用）第1回浜田市職員採用試験　第2次試験の結果について", "1784797956307", "2026-07-24T20:00:00+09:00"),
    ("防災行政無線で流れる曲名を紹介します", "1783670896127", "2026-07-24T16:13:12+09:00"),
    ("石見神楽保存・伝承拠点基本構想（案）について", "1784069179633", "2026-07-24T16:00:00+09:00"),
    ("浜田市DX推進計画(案)への意見募集", "1775520034735", "2026-07-24T08:29:36+09:00"),
    ("山陰浜田港（浜田漁港）水揚げ速報値", "1415775865779", "2026-07-24T00:00:00+09:00"),
    ("救命講習定期開催のお知らせ", "1751507719522", "2026-07-23T08:30:50+09:00"),
    ("令和8年度山陰浜田港お魚料理教室の開催日程", "1708068769697", "2026-07-22T16:07:23+09:00"),
    ("浜田市文化祭協賛行事", "1784159958213", "2026-07-22T10:24:32+09:00"),
    ("浜田市農林道トンネル長寿命化修繕計画", "1784597101113", "2026-07-22T08:33:28+09:00"),
    ("公社賃貸住宅（今福団地）入居者募集について", "1603681154752", "2026-07-17T08:30:00+09:00"),
    ("危険物取扱者保安講習を行います", "1424847308833", "2026-07-16T08:31:27+09:00"),
    ("令和8年度 浜田市優良建設工事表彰", "1693288159881", "2026-07-14T00:00:00+09:00"),
    ("食育講座の様子を掲載しました(すくすく)", "1396849471665", "2026-07-13T00:00:00+09:00"),
    ("「自社PRのための効果的な情報発信について学んでみませんか？」を開催します", "1783386403573", "2026-07-10T12:00:00+09:00"),
    ("石央文化ホール「バックステージツアー！！～ホール舞台裏探検隊集合～」が開催されます", "1783496689810", "2026-07-10T08:31:52+09:00"),
    ("石央文化ホール「2026　DANCE　CONTEST」出場者大募集！！", "1783555518382", "2026-07-10T08:31:42+09:00"),
    ("第57回浜田市美術展写真の部ワークショップ写真教室「プリント大伸ばし体験」参加者募集", "1783303687543", "2026-07-09T09:43:32+09:00"),
    ("サンマリン浜田の指定管理者の公募について", "1783050862022", "2026-07-08T08:15:00+09:00"),
    ("市長の日記を更新しました", "1646883970524", "2026-07-08T00:00:00+09:00"),
    ("しまねふるさとフェア２０２７（広島市）の参加申込の受付を開始します！", "1782715766244", "2026-07-03T10:00:00+09:00"),
    ("第37回さざんか祭り　アトラクション参加者募集について", "1782986394099", "2026-07-03T00:00:00+09:00"),
    ("一斉相談会（法律相談）のお知らせ", "1751509359840", "2026-07-01T00:00:00+09:00"),
    ("広報はまだ7月号", "1773203826879", "2026-06-30T08:30:00+09:00"),
    ("【世界こども美術館】企画展「さわっ手たのしむタッチミュージアムⅡ～森と海～」が開催されます", "1782456015383", "2026-06-30T13:10:35+09:00"),
    ("【石央文化ホール】企画展「石央シネマ俱楽部企画上映会『国宝』が開催されます", "1782457703557", "2026-06-30T13:10:20+09:00"),
    # RSSに残っていた2022年の古い記事（日付フィルタで落ちるはず）
    ("新型コロナウイルス感染症の市内での発生状況（5月14日）", "1652519650023", "2022-05-14T18:14:11+09:00"),
]

ITEM = """<item rdf:about="{u}"><title>{t}</title><link>{u}</link>
<description/><dc:date>{d}</dc:date></item>"""


def main():
    xml = FIXTURE.format(items="\n".join(
        ITEM.format(t=t, u=f"https://www.city.hamada.shimane.jp/www/contents/{i}/index.html", d=d)
        for t, i, d in REAL))

    src = MunicipalRSS(key="hamada_city", site="https://www.city.hamada.shimane.jp",
                       municipality="浜田市")
    events = src.parse_feed(xml)
    print(f"1. RSS取得        : {len(REAL)}件 → 日付フィルタ後 {len(events)}件"
          f"（2022年の記事を除外）")

    kept, dropped = [], 0
    for ev in events:
        v = classify(ev.title, ev.description)
        if v.bucket == "drop":
            dropped += 1
            continue
        ev.category, ev.tags, ev.score, ev.reason = v.category, v.tags, v.score, v.reason
        ev.review_state, ev.organizer_type = v.bucket, "自治体"
        kept.append(ev)
    print(f"2. 仕分け          : {dropped}件を除外（{dropped/len(events):.0%}）→ 残り {len(kept)}件")

    data_dir = pathlib.Path("data_demo")
    if data_dir.exists():
        shutil.rmtree(data_dir)
    queue = ReviewQueue(data_dir)
    stats = queue.ingest(kept)
    print(f"3. 承認キュー      : 自動公開 {stats['new_auto']}件 / 要確認 {stats['new_pending']}件")

    # 承認作業をシミュレート（実際は `python main.py review` で1件ずつ）
    for ev in queue.pending:
        queue.decide(ev.uid, approve=ev.score >= 2)
    approved = queue.approved
    print(f"4. 承認後          : 公開 {len(approved)}件 / 却下 {len(queue.rejected)}件")

    out = pathlib.Path("out")
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(to_public_site(approved, "石見"), encoding="utf-8")
    print(f"5. 公開サイト生成  : out/index.html\n")

    print("--- 公開されるもの ---")
    for e in sorted(approved, key=lambda x: x.category or ""):
        print(f"  [{e.category or '未分類'}] {e.title[:40]}")


if __name__ == "__main__":
    main()
