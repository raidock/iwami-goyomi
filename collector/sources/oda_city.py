"""大田市アダプター。フィードに掲載日が無いので、新着一覧HTMLから補う。

実ページを読んで分かったこと（2026-07-30）:

1. `https://www.city.oda.lg.jp/feed/` は**新着フィードではない**。
   サイト全体の目次で、907件のうち大半が組織案内・施設案内などの固定ページ。
   RSS 2.0 の形をしているが `<pubDate>` を1件も持たない（907件中0件）。

2. 記事は `/update_info/…` の99件。掲載日はここには無く、
   新着一覧 `/update_info/` のHTMLに `2026.07.27` の形で載っている（99件すべて）。
   URLは `/update_info/11137` の連番だけでなく `/update_info/guidebook` のような
   名前つきもある。**数字に限定すると4件が漏れる**（新庁舎整備の経過・ガイド作成・
   特設サイト・説明会の回答）。

3. **掲載日が無いと年の推定が「今日」に落ちる。**
   `_to_date()` は掲載日を基準に年を当てるので、掲載日が無いと today_jst() を
   使う。すると1月に出た「【３月７日～８日開催】石見銀山フェスin名古屋」は、
   いま7月なので**翌年の2027-03-07**になる。
   日付が1年ずれた催しは、載っていないより悪い（住民が来年の予定だと思って
   見送る）。だから1リクエストを払って一覧HTMLを見る。

一覧HTMLの読み方はこのサイト固有なので、汎用の仕組みにはしていない。
他の市町は掲載日をフィードに持っているので、必要になるまで一般化しない。
"""
from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup

from ..models import Event
from .municipal_rss import MunicipalRSS

# 新着一覧の日付表記。「2026.07.27」
_LIST_DATE = re.compile(r"(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})")
# 記事のURL。索引ページ `/update_info/` そのものと、`?page=2` のような
# 一覧の続きは含まない。記事は `/update_info/11137` のような連番だが、
# `/update_info/guidebook` のような名前つきもあるので数字に限定しない
_ARTICLE_HREF = re.compile(r"/update_info/[^/?#]")


class OdaCityRSS(MunicipalRSS):
    """大田市。フィード＋新着一覧HTMLの2リクエストで1回の収集が終わる。"""

    list_path = "/update_info/"

    def published_dates(self) -> dict[str, date]:
        """新着一覧HTMLから {記事URL: 掲載日} を作る。1リクエストで95件ぶん。

        `<li><span class="date">2026.07.27</span><span class="title"><a …>` という
        並びだが、class 名には依存しない。**記事URLのリンクから親をたどって、
        いちばん近い日付を拾う**。テーマが変わってもリンクと日付の近さは変わらない。
        """
        html = self.get(self.site + self.list_path)
        soup = BeautifulSoup(html, "html.parser")
        out: dict[str, date] = {}
        for a in soup.find_all("a", href=True):
            if not _ARTICLE_HREF.search(a["href"]):
                continue
            node = a
            for _ in range(4):               # li まで届けば十分（実測は2段）
                node = node.parent
                if node is None:
                    break
                if m := _LIST_DATE.search(node.get_text(" ", strip=True)):
                    try:
                        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                    except ValueError:
                        break
                    out.setdefault(self._abs(a["href"]).rstrip("/"), d)
                    break
        return out

    def collect(self) -> list[Event]:
        events = super().collect()
        if not events:
            return events
        try:
            dates = self.published_dates()
        except Exception as e:
            # 落としはしない。95件を捨てるほうが痛い。ただし黙って進まない
            # （掲載日が無いまま進むと、年が1年ずれた催しが出る）
            print(f"[警告] {self.name}: 新着一覧から掲載日が取れませんでした: {e}")
            print("        年の推定が今日基準になります。日付は承認画面で確かめてください。")
            return events
        hit = 0
        for ev in events:
            if ev.published_at:
                continue
            if d := dates.get((ev.url or "").rstrip("/")):
                ev.published_at = d
                hit += 1
        print(f"[info] {self.name}: 新着一覧から掲載日を {hit}/{len(events)}件 補完")
        return events
