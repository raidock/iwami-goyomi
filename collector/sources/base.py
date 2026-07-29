"""ソースアダプターの共通インターフェース。

新しい情報源（fmfm.jp / ANTIQUE LEAVES など）を足すときは、
このクラスを継承して collect() を実装するだけでよい。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import requests

from .. import USER_AGENT          # 名乗る名前は collector/__init__.py に1つだけ
from ..models import Event

__all__ = ["USER_AGENT", "Source"]


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
