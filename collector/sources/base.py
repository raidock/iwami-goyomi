"""ソースアダプターの共通インターフェース。

新しい情報源（fmfm.jp / ANTIQUE LEAVES など）を足すときは、
このクラスを継承して collect() を実装するだけでよい。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import requests

from ..models import Event

USER_AGENT = "sanin-nomi-collector/1.0 (+personal flea-market tracker)"


class Source(ABC):
    name: str = "base"

    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def get(self, url: str) -> str:
        resp = self.session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or resp.encoding
        return resp.text

    @abstractmethod
    def collect(self) -> list[Event]:
        """このソースから取得できるイベントを全部返す（フィルタ前）。"""
        raise NotImplementedError
