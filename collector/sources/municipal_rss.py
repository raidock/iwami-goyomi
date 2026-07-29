"""自治体サイト向け汎用RSSアダプター。

石見9市町はCMSベンダーがバラバラなので、RSSのURLをハードコードせず
トップページの <link rel="alternate" type="application/rss+xml"> から
自動発見する。RSS 1.0(RDF) / RSS 2.0 / Atom のどれでも読む。

浜田市: https://www.city.hamada.shimane.jp/www/rss/news.rdf (RSS 1.0)
江津市: サイト側にRSS配信あり（自動発見に任せる）
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import Event, today_jst
from .base import DEFAULT_FETCH_DELAY_SEC, Source

FEED_TYPES = ("application/rss+xml", "application/atom+xml", "application/rdf+xml")
# 本文中のRSSリンクを拾うための判定（江津市 /rss/10/list1.xml のような形）
FEED_HREF_RE = re.compile(r"(rss|feed|atom).*\.(xml|rdf)$|\.(rdf|rss)$", re.I)
# よくある置き場所（自動発見が失敗したときの当て先）
FALLBACK_PATHS = ["/www/rss/news.rdf", "/rss/news.rdf", "/rss/10/list1.xml",
                  "/rss.xml", "/feed", "/index.rdf", "/news.rdf"]


class MunicipalRSS(Source):
    """1自治体 = 1インスタンス。config.yaml から生成される。"""

    def __init__(self, key: str, site: str, municipality: str,
                 feed_url: str | None = None, max_age_days: int = 400,
                 url_include: str | None = None,
                 fetch_delay_sec: float = DEFAULT_FETCH_DELAY_SEC, **kw):
        super().__init__(fetch_delay_sec=fetch_delay_sec,
                         **{k: v for k, v in kw.items() if k == "timeout"})
        self.name = key
        self.site = site.rstrip("/")
        self.municipality = municipality
        self.feed_url = feed_url
        self.max_age_days = max_age_days
        # サイト全体のRSSしかない場合に、記事URLで絞り込む
        # （江津市観光協会は /feed に観光スポット紹介まで流れてくる）
        self.url_include = re.compile(url_include) if url_include else None

    # ---- フィードの発見 ------------------------------------------------
    def _abs(self, href: str) -> str:
        """サイト基準の絶対URLにする。

        `//cdn.example.jp/rss.xml` というプロトコル相対URLは標準的な書き方だが、
        `http` で始まらないので `self.site + href` に落ちて壊れていた。
        `rss/news.rdf` のような先頭スラッシュ無しも同様に繋がらない。
        3種類とも urljoin が正しく解く。
        """
        return urljoin(self.site + "/", href.strip())

    def discover_feed(self) -> str | None:
        """3段階で探す。江津市は<head>ではなく本文の<a>にRSSを置いていた。"""
        if self.feed_url:
            return self.feed_url
        try:
            soup = BeautifulSoup(self.get(self.site), "html.parser")

            # (1) <head> の autodiscovery（標準的なやり方）
            for link in soup.find_all("link", rel=lambda r: r and "alternate" in r):
                if link.get("type") in FEED_TYPES and link.get("href"):
                    return self._abs(link["href"])

            # (2) 本文の <a> からRSSらしいリンクを拾う
            #     自治体サイトは複数のRSSを並べていることが多いので、
            #     「新着」と書かれたものを優先する（江津市は3本あった）
            candidates: list[tuple[int, str]] = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if not FEED_HREF_RE.search(href):
                    continue
                label = a.get_text(" ", strip=True) + " " + (a.get("title") or "")
                parent = a.find_parent(["span", "li", "p", "div"])
                if parent:
                    label += " " + parent.get_text(" ", strip=True)[:60]
                if "新着" in label:
                    rank = 0
                elif any(w in label for w in ("重要", "緊急", "防災")):
                    rank = 2          # 緊急情報系は催しが載らないので後回し
                else:
                    rank = 1
                candidates.append((rank, self._abs(href)))
            if candidates:
                candidates.sort(key=lambda c: c[0])
                return candidates[0][1]
        except Exception as e:
            print(f"[warn] {self.name}: トップページ取得に失敗: {e}")
        for path in FALLBACK_PATHS:
            url = self.site + path
            try:
                if "<rdf" in (head := self.get(url)[:400]).lower() or "<rss" in head.lower() \
                        or "<feed" in head.lower():
                    return url
            except Exception:
                continue
        return None

    # ---- パース --------------------------------------------------------
    @staticmethod
    def _parse_dt(raw: str | None) -> date | None:
        if not raw:
            return None
        raw = raw.strip()
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ",
                    "%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
        try:  # 末尾のタイムゾーンだけ違う形の保険
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            return None

    def parse_feed(self, xml: str) -> list[Event]:
        soup = BeautifulSoup(xml, "xml")
        cutoff = today_jst() - timedelta(days=self.max_age_days)
        events: list[Event] = []

        for item in soup.find_all(["item", "entry"]):
            title_el = item.find("title")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)

            link_el = item.find("link")
            url = ""
            if link_el:
                url = link_el.get("href") or link_el.get_text(strip=True) or ""
            if not url:
                url = item.get("rdf:about", "")

            raw_date = None
            for tag in ("date", "pubDate", "published", "updated"):
                if el := item.find(tag):
                    raw_date = el.get_text(strip=True)
                    break
            published = self._parse_dt(raw_date)

            # 古い記事はフィードに残り続けるので必ず捨てる
            # （浜田市RSSには2022年のコロナ情報が残っていた）
            if published and published < cutoff:
                continue

            desc_el = item.find(["description", "summary", "content"])
            body = desc_el.get_text(" ", strip=True)[:400] if desc_el else ""

            if self.url_include and not self.url_include.search(url):
                continue
            ev = Event.from_listing(title, raw_date or "", url, self.name)
            ev.prefecture = "島根県"
            ev.city = self.municipality
            ev.venue = None
            # RSSの日付は「掲載日」であって開催日ではない。
            # 開催日はタイトル/本文から拾えたものだけ採用し、拾えなければ未定にする。
            if not ev.date_start:
                ev.date_start = None
            ev.raw_date_text = ""
            ev.description = body
            ev.published_at = published
            return_title = title
            ev.title = return_title
            events.append(ev)
        return events

    def collect(self) -> list[Event]:
        feed = self.discover_feed()
        if not feed:
            print(f"[warn] {self.name}: RSSが見つかりませんでした")
            return []
        print(f"[info] {self.name}: {feed}")
        try:
            return self.parse_feed(self.get(feed))
        except Exception as e:
            print(f"[warn] {self.name}: 取得失敗: {e}")
            return []
