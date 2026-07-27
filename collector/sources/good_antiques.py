"""GOOD ANTIQUES「中国・四国編」月次まとめのアダプター。

Shopify ブログなので、記事一覧は Atom フィードで機械可読に取れる。
Atom が取れないときは記事一覧HTMLへフォールバックする。
記事本文は「日付見出し + 【県名】イベント名 + 詳細リンク」という
規則的な構造なので、詳細リンクを起点に直近の日付を紐づけて抽出する。
"""
from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup, NavigableString

from ..models import Event, _FULL_DATE
from .base import Source

BASE = "https://good-antiques.com"
FEATURE_INDEX = f"{BASE}/blogs/places-features"
FEATURE_ATOM = f"{BASE}/blogs/places-features.atom"
REGION_TOKEN = "中国・四国"
EVENT_HREF = re.compile(r"/blogs/places-events/")

# 記事本文コンテナの候補（Shopify テーマ差異を吸収）
ARTICLE_SELECTORS = ["article", ".article__content", ".article-content",
                     '[class*="article"]', "main"]


def _target_month_tokens(months_ahead: int) -> list[str]:
    today = date.today()
    tokens = []
    y, m = today.year, today.month
    for _ in range(months_ahead + 1):
        tokens.append(f"{y}年{m}月")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return tokens


class GoodAntiques(Source):
    name = "good_antiques"

    def __init__(self, months_ahead: int = 1, **kw):
        super().__init__(**kw)
        self.months_ahead = months_ahead

    # ---- 記事URLの発見 -------------------------------------------------
    def discover_articles(self) -> list[str]:
        tokens = _target_month_tokens(self.months_ahead)
        urls = self._from_atom(tokens) or self._from_index(tokens)
        return urls

    def _from_atom(self, tokens: list[str]) -> list[str]:
        try:
            xml = self.get(FEATURE_ATOM)
        except Exception:
            return []
        soup = BeautifulSoup(xml, "xml")
        urls = []
        for entry in soup.find_all("entry"):
            title = (entry.title.text if entry.title else "")
            if REGION_TOKEN not in title:
                continue
            if not any(tok in title for tok in tokens):
                continue
            link = entry.find("link")
            href = link.get("href") if link else None
            if href:
                urls.append(href)
        return urls

    def _from_index(self, tokens: list[str]) -> list[str]:
        html = self.get(FEATURE_INDEX)
        soup = BeautifulSoup(html, "html.parser")
        urls = []
        for a in soup.select('a[href*="/blogs/places-features/"]'):
            text = a.get_text(strip=True)
            if REGION_TOKEN in text and any(tok in text for tok in tokens):
                href = a["href"]
                urls.append(href if href.startswith("http") else BASE + href)
        # 重複除去（順序維持）
        return list(dict.fromkeys(urls))

    # ---- 記事本文のパース ---------------------------------------------
    def _article_body(self, soup: BeautifulSoup):
        for sel in ARTICLE_SELECTORS:
            node = soup.select_one(sel)
            if node:
                return node
        return soup

    def parse_article(self, html: str) -> list[Event]:
        soup = BeautifulSoup(html, "html.parser")
        body = self._article_body(soup)
        events: list[Event] = []
        current_date_text = ""
        for node in body.descendants:
            if isinstance(node, NavigableString):
                text = str(node).strip()
                if text and _FULL_DATE.search(text):
                    current_date_text = text
            elif getattr(node, "name", None) == "a":
                href = node.get("href", "")
                if EVENT_HREF.search(href):
                    title = node.get_text(strip=True)
                    if not title or not current_date_text:
                        continue
                    url = href if href.startswith("http") else BASE + href
                    events.append(
                        Event.from_listing(title, current_date_text, url, self.name)
                    )
        return events

    # ---- エントリポイント ---------------------------------------------
    def collect(self) -> list[Event]:
        events: list[Event] = []
        for url in self.discover_articles():
            try:
                events.extend(self.parse_article(self.get(url)))
            except Exception as e:  # 1記事の失敗で全体を止めない
                print(f"[warn] {self.name}: {url} の取得に失敗: {e}")
        return events
