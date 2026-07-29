"""ソースアダプターの共通インターフェース。

新しい情報源（fmfm.jp / ANTIQUE LEAVES など）を足すときは、
このクラスを継承して collect() を実装するだけでよい。
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Optional

import requests

from .. import USER_AGENT          # 名乗る名前は collector/__init__.py に1つだけ
from ..models import Event

__all__ = ["USER_AGENT", "Pacer", "Source"]

DEFAULT_FETCH_DELAY_SEC = 1.0


class Pacer:
    """1つの情報源に対する取得間隔を守る。

    間隔は**情報源ごと**に持つ。全体で1つの値にしていると、
    robots.txt で `Crawl-delay: 5` を宣言しているサイトに合わせた瞬間、
    他の情報源まで5秒待つことになる（大田市を足すときに詰まった）。

    待つ長さは「前回の応答が返ってから」で数える。Crawl-delay の読み方は
    複数あるが、終わりから数えるのが一番おとなしい。取得に失敗したときも
    相手のサーバは叩いているので、同じように数える。
    """

    def __init__(self, delay: float = DEFAULT_FETCH_DELAY_SEC):
        self.delay = max(0.0, float(delay))
        self._last: Optional[float] = None

    def wait(self) -> None:
        """前回から delay 秒経つまで待つ。初回は待たない。"""
        if self._last is None:
            return
        rest = self.delay - (time.monotonic() - self._last)
        if rest > 0:
            time.sleep(rest)

    def mark(self) -> None:
        """1回叩いたことを記録する（成否によらず）。"""
        self._last = time.monotonic()


class Source(ABC):
    name: str = "base"

    def __init__(self, timeout: int = 20,
                 fetch_delay_sec: float = DEFAULT_FETCH_DELAY_SEC):
        self.timeout = timeout
        self.pacer = Pacer(fetch_delay_sec)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def get(self, url: str) -> str:
        """間隔を空けてから取りにいく。

        フィードの自動発見は1サイトに何度も当てにいく（FALLBACK_PATHS は
        最大7回）ので、間隔はここに置く。呼ぶ側に任せると必ず抜ける。
        """
        self.pacer.wait()
        try:
            resp = self.session.get(url, timeout=self.timeout)
        finally:
            self.pacer.mark()
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or resp.encoding
        return resp.text

    @abstractmethod
    def collect(self) -> list[Event]:
        """このソースから取得できるイベントを全部返す（フィルタ前）。"""
        raise NotImplementedError
