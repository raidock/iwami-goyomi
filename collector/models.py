"""イベントのデータモデルと日本語日付パーサ。"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional


# 「2026年3月14日(土)」「2026年5月4日(月・祝)」などから 年/月/日 を拾う
_FULL_DATE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
# 範囲の終端が「〜15(日)」「~5日」「~6月1日」など。
# 月が省略される場合や、末尾の「日」が無く曜日だけ括弧で来る場合がある
_RANGE_TAIL = re.compile(r"[〜~～\-]\s*(?:(\d{1,2})\s*月\s*)?(\d{1,2})\s*日?")
# タイトル先頭の「【島根県】」
_PREF_TAG = re.compile(r"【\s*(.+?[都道府県])\s*】")


def parse_japanese_date_range(text: str) -> tuple[Optional[date], Optional[date]]:
    """日本語の日付文字列から (開始日, 終了日) を返す。

    単日なら終了日は開始日と同じ。パースできなければ (None, None)。
    """
    m = _FULL_DATE.search(text)
    if not m:
        return None, None
    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        start = date(year, month, day)
    except ValueError:
        return None, None

    end = start
    tail = _RANGE_TAIL.search(text, m.end())
    if tail:
        end_month = int(tail.group(1)) if tail.group(1) else month
        end_day = int(tail.group(2))
        end_year = year + 1 if end_month < month else year  # 年跨ぎの保険
        try:
            end = date(end_year, end_month, end_day)
        except ValueError:
            end = start
    return start, end


def extract_prefecture(title: str) -> Optional[str]:
    m = _PREF_TAG.search(title)
    return m.group(1) if m else None


def clean_title(title: str) -> str:
    """【県名】を除いた純粋なイベント名。"""
    return _PREF_TAG.sub("", title).strip()


@dataclass
class Event:
    title: str                      # 【県名】を含まないイベント名
    prefecture: Optional[str]       # 例: 島根県
    date_start: Optional[date]
    date_end: Optional[date]
    url: str                        # 詳細ページ
    source: str                     # 取得元アダプター名
    raw_date_text: str = ""         # 元の日付表記（デバッグ・表示用）
    city: Optional[str] = None
    venue: Optional[str] = None
    distance_tier: Optional[str] = None  # フィルタ側で付与

    # --- 地域イベント版で追加 ---
    description: str = ""
    published_at: Optional[date] = None      # 掲載日（開催日ではない）
    deadline: Optional[date] = None          # 申込締切。行政系はこちらが主役
    category: Optional[str] = None
    tags: list = field(default_factory=list)
    organizer: Optional[str] = None
    organizer_type: Optional[str] = None     # 自治体/観光協会/企業/自治会/NPO
    kind: str = "催し"                        # 催し / 募集 / 制度
    status: str = "開催予定"                  # 開催予定/中止/終了/最後の開催
    review_state: str = "pending"            # pending/approved/rejected
    score: int = 0
    reason: str = ""
    source_trust: str = "normal" # normal / high（観光協会など事前に選別済み）
    date_source: str = ""        # 開催日をどこから取ったか
    deadline_source: str = ""    # 締切をどこから取ったか
    # 飛び石で複数回ある催しの回数。date_start は「次回」を指す。
    # 期間ではないので date_end には触れない（「9月12日〜翌3月17日」は嘘になる）
    session_count: Optional[int] = None
    # 同じ催しの別日程の数（会場違いなど）。**session_count とは意味が違う。**
    # 救命講習の「全6回」は同じ催しが6回繰り返される。天領さんの3会場は
    # 1つの祭りが大田・久手・大森で日を変えて開かれる。前者は「全N回」、
    # 後者は「ほか」と出す。
    other_dates: int = 0

    @classmethod
    def from_listing(cls, raw_title: str, raw_date_text: str, url: str, source: str) -> "Event":
        start, end = parse_japanese_date_range(raw_date_text)
        return cls(
            title=clean_title(raw_title),
            prefecture=extract_prefecture(raw_title),
            date_start=start,
            date_end=end,
            url=url,
            source=source,
            raw_date_text=raw_date_text.strip(),
        )

    @property
    def uid(self) -> str:
        """安定ID。

        **後から埋まる情報（開催日・締切）を絶対に混ぜないこと。**
        日付抽出で開催日が埋まった瞬間にuidが変わり、同じイベントが
        重複して追加される事故を起こした（v1.5）。
        URLは一次情報の場所そのものなので、最も安定した鍵になる。
        """
        key = self.url or f"{self.prefecture}|{self.title}"
        return hashlib.md5(key.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("date_start", "date_end", "published_at", "deadline"):
            d[k] = d[k].isoformat() if d.get(k) else None
        d["uid"] = self.uid
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        d = dict(d)
        d.pop("uid", None)
        for k in ("date_start", "date_end", "published_at", "deadline"):
            d[k] = date.fromisoformat(d[k]) if d.get(k) else None
        return cls(**d)


# ---------------------------------------------------------------- 日本時間
# GitHub Actions のサーバーは協定世界時(UTC)で動く。
# そのまま date.today() を使うと、日本時間の 0時〜9時 のあいだ日付が1日ずれ、
# 「あと○日」の計算も「終わった催し」への振り分けも狂う。
# 地域の暦なので、必ず日本時間で判断する。
JST = ZoneInfo("Asia/Tokyo")


def now_jst() -> datetime:
    return datetime.now(JST)


def today_jst() -> date:
    return now_jst().date()


# ---------------------------------------------------------------- 和暦
# はまナビ（浜田市観光協会）は「令和7年11月8日」のように和暦で書く。
# 西暦しか読めないと観光協会の日付が1件も取れない。
ERA_BASE = {"令和": 2018, "平成": 1988, "昭和": 1925}
_ERA_RE = re.compile(r"(令和|平成|昭和)\s*(元|\d{1,2})\s*年")
# 「R8.7.20」「H31.4.30」のような略記。地域のチラシや投稿でよく使われる
ERA_ABBR = {"R": 2018, "H": 1988, "S": 1925}
_ERA_ABBR_RE = re.compile(r"(?<![A-Za-z])([RHS])\s*(\d{1,2})\s*[.\-/年]\s*"
                          r"(\d{1,2})\s*[.\-/月]\s*(\d{1,2})\s*日?")


def wareki_to_seireki(text: str) -> str:
    """文中の和暦を西暦に置き換える。

    「令和元年」「令和7年11月8日」に加え、「R8.7.20」の略記にも対応する。
    """
    def rep_abbr(m):
        era, y, mo, d = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
        return f"{ERA_ABBR[era] + y}年{mo}月{d}日"

    def rep(m):
        era, num = m.group(1), m.group(2)
        n = 1 if num == "元" else int(num)
        return f"{ERA_BASE[era] + n}年"

    return _ERA_RE.sub(rep, _ERA_ABBR_RE.sub(rep_abbr, text))


# ---------------------------------------------------------------- 日付の抽出
# タイトルに書かれている開催日・締切を拾う。本文のLLM抽出はPhase 1。
#
# 年・月・日は名前付きで取る。位置で取ると、年つきの形を足したときに
# 月日の番号がずれて黙って壊れる（実際にこれで年が捨てられていた）。
_HELD_RE = [
    re.compile(r"(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日[^、。]{0,6}?開催"),
    re.compile(r"(?P<m>\d{1,2})\s*/\s*(?P<d>\d{1,2})[（(][^）)]{0,3}[）)]\s*開催"),
    # タイトル冒頭の日付は開催日とみなす
    # 例:「8月22日（土）有福温泉湯の町神楽殿 …神楽上演のお知らせ」
    re.compile(r"^\s*(?:(?P<y>\d{4})\s*年\s*)?(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日"),
]
_DEADLINE_RE = [
    re.compile(r"締[めm]?切[はり]?\s*[:：]?\s*(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日"),
    re.compile(r"(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日\s*まで"),
    re.compile(r"(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})\s*日\s*(?:必着|消印)"),
]


def _to_date(month: int, day: int, ref: Optional[date] = None) -> Optional[date]:
    """月日だけの表記に年を補う。

    基準は「今日」ではなく **記事の掲載日** を使う。
    1月に出た記事の「3/8開催」は、今が7月でも 2026年3月8日 を指すため。
    （掲載日を今日にすると翌年と誤認する。実際に踏んだバグ）
    """
    ref = ref or today_jst()
    for year in (ref.year, ref.year + 1):
        try:
            d = date(year, month, day)
        except ValueError:
            return None
        if d >= ref - timedelta(days=14):   # 告知が開催直後にずれる場合の余裕
            return d
    return None


def _matched_date(m: "re.Match[str]", ref: Optional[date]) -> Optional[date]:
    """一致した月日に年を与える。

    **年が書いてあれば、それを使う。** 掲載日から推し量るのは年が無いときだけ。
    かつて先頭の「2026年」を捨てて月日だけ見ていたため、掲載日の年に丸められた。
    先の年の催し（2026年7月に出た「2027年8月1日」の告知）が今年の8月1日になり、
    しかも掲載日基準では未来なので誰も気づけない形で1年ずれる。
    """
    mo, d = int(m.group("m")), int(m.group("d"))
    if y := m.groupdict().get("y"):
        try:
            return date(int(y), mo, d)
        except ValueError:            # 2026年2月30日 のような書き間違い
            return None
    return _to_date(mo, d, ref)


def extract_held_date(text: str, ref: Optional[date] = None) -> Optional[date]:
    """ref には記事の掲載日を渡すこと。和暦・略記も先に西暦へ直す。"""
    text = wareki_to_seireki(text)
    for r in _HELD_RE:
        if m := r.search(text):
            return _matched_date(m, ref)
    return None


def extract_deadline(text: str, ref: Optional[date] = None) -> Optional[date]:
    """ref には記事の掲載日を渡すこと。和暦・略記も先に西暦へ直す。"""
    text = wareki_to_seireki(text)
    for r in _DEADLINE_RE:
        if m := r.search(text):
            return _matched_date(m, ref)
    return None
