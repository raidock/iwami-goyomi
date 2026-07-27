"""詳細ページから開催日・申込締切を抜き出す。

実ページを読んで分かったこと（2026-07）:

1. 1ページに日付が7個あることがある（江津 Go-Con2026: 掲載日/提出期限/公募期間/
   結果通知/勉強会×3/最終審査会）。本文を正規表現でなめると必ず間違える。

2. 市によって書き方が違う。
   - 江津: 「#### 提出期限」→「8月3日（月曜日）」と見出しで区切られている
   - 浜田: 「12月13日（日） 午後1時～ … 7月31日（金）までに」と流し込み

   そこで2層構えにする。
     層1 見出しベース  … 見出しの語が日付の意味を教えてくれる（高精度）
     層2 文脈語ベース  … 「までに」「必着」「午後1時～」などの手がかり（流し込み用）

3. どこから取った日付かを必ず記録する。人が承認画面で見て誤りに気づけるようにする
   （根拠の見えない日付は、公開物では載せないほうがまし）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

from bs4 import BeautifulSoup

from .models import _to_date, wareki_to_seireki

# ---------------------------------------------------------------- 見出しの語
DEADLINE_HEADS = [
    "提出期限", "応募期限", "申込期限", "申し込み期限", "申込締切", "応募締切",
    "締切", "締め切り", "受付期限", "募集期限", "エントリー期限",
]
PERIOD_HEADS = [                      # 期間の見出しは「終わり」が締切
    "公募期間", "募集期間", "申込期間", "申し込み期間", "受付期間", "応募期間",
    "エントリー期間",
]
HELD_HEADS = [
    "日時", "開催日", "開催日時", "開催期間", "とき", "期日", "開催場所と日時",
]

# ---------------------------------------------------------------- 日付の形
# 「8月3日（月曜日）」「12月13日（日）」「2026年8月3日」いずれも拾う
_DATE = re.compile(r"(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_DATE_SLASH = re.compile(r"(?:(\d{4})\s*/\s*)?(\d{1,2})\s*/\s*(\d{1,2})")

# はまナビなどが使う【日時】【場所】形式のラベル。見出しタグではないので別で拾う
_BRACKET_LABEL = re.compile(r"[【〔\[]\s*([^】〕\]]{1,12})\s*[】〕\]]")

# 流し込み文中の手がかり。日付の「後ろ」に来る語
_DEADLINE_TAIL = re.compile(
    r"(?:（[^）]{0,6}）|\([^)]{0,6}\)|\s)*(?:正午|午前\d{1,2}時|午後\d{1,2}時)?\s*"
    r"(?:まで|までに|必着|消印有効|締切|締め切り)")
# 日付の「後ろ」に開演時刻が来ていれば開催日
_HELD_TAIL = re.compile(
    r"(?:（[^）]{0,6}）|\([^)]{0,6}\)|\s)*(?:午前|午後)\s*\d{1,2}\s*時|開演|開場|開催")


@dataclass
class Extracted:
    date_start: Optional[date] = None
    deadline: Optional[date] = None
    date_source: str = ""        # どこから取ったか（承認画面に出す）
    deadline_source: str = ""


def _find_dates(text: str, ref: Optional[date]) -> list[tuple[date, int]]:
    """テキスト中の日付を (日付, 出現位置) で返す。"""
    out = []
    for m in _DATE.finditer(text):
        y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
        dt = date(int(y), mo, d) if y else _to_date(mo, d, ref)
        if dt:
            out.append((dt, m.end()))
    if not out:
        for m in _DATE_SLASH.finditer(text):
            y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
            if not 1 <= mo <= 12 or not 1 <= d <= 31:
                continue
            dt = date(int(y), mo, d) if y else _to_date(mo, d, ref)
            if dt:
                out.append((dt, m.end()))
    return out


def _bracket_sections(text: str) -> list[tuple[str, str]]:
    """【日時】…【場所】… の形から (ラベル, 中身) を取り出す。"""
    out, marks = [], list(_BRACKET_LABEL.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else min(len(text), m.end() + 160)
        out.append((m.group(1), text[m.end():end].strip()[:160]))
    return out


def _sections(soup: BeautifulSoup) -> list[tuple[str, str]]:
    """(見出し, その見出しに続く本文) の並びに分解する。"""
    heads = soup.find_all(["h2", "h3", "h4", "h5", "h6", "th", "dt", "strong", "b"])
    out = []
    for h in heads:
        label = h.get_text(" ", strip=True)
        if not label or len(label) > 24:
            continue
        # 見出しの直後にある文字列を集める
        chunks = []
        for sib in h.next_siblings:
            if getattr(sib, "name", None) in ("h2", "h3", "h4", "h5", "h6"):
                break
            txt = sib.get_text(" ", strip=True) if hasattr(sib, "get_text") else str(sib).strip()
            if txt:
                chunks.append(txt)
            if sum(len(c) for c in chunks) > 200:
                break
        # th/dt/strong は同じ行の隣を見る
        if not chunks and h.name in ("th", "dt", "strong", "b"):
            nxt = h.find_next(["td", "dd"]) if h.name in ("th", "dt") else h.next_sibling
            if nxt is not None:
                txt = nxt.get_text(" ", strip=True) if hasattr(nxt, "get_text") else str(nxt)
                if txt:
                    chunks.append(txt.strip())
        out.append((label, " ".join(chunks)[:200]))
    return out


def extract_dates(html: str, ref: Optional[date] = None) -> Extracted:
    """詳細ページのHTMLから開催日と締切を取り出す。

    ref には記事の掲載日を渡す（年の推定に使う）。
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    got = Extracted()

    # ---- 層1: 見出しベース（【日時】形式も同じ扱い）---------------------
    plain = wareki_to_seireki(soup.get_text(" ", strip=True))
    sections = [(l, wareki_to_seireki(b)) for l, b in _sections(soup)]
    sections += _bracket_sections(plain)
    for label, body in sections:
        dates = _find_dates(body, ref)
        if not dates:
            continue
        if not got.deadline and any(k in label for k in DEADLINE_HEADS):
            got.deadline = dates[0][0]
            got.deadline_source = f"見出し「{label}」"
        elif not got.deadline and any(k in label for k in PERIOD_HEADS):
            got.deadline = dates[-1][0]          # 期間は終わりが締切
            got.deadline_source = f"見出し「{label}」の終わり"
        elif not got.date_start and any(k in label for k in HELD_HEADS):
            got.date_start = dates[0][0]
            got.date_source = f"見出し「{label}」"

    if got.date_start and got.deadline:
        return got

    # ---- 層2: 文脈語ベース（流し込みの本文用）--------------------------
    text = plain
    for dt, pos in _find_dates(text, ref):
        tail = text[pos:pos + 24]
        if not got.deadline and _DEADLINE_TAIL.match(tail):
            got.deadline = dt
            got.deadline_source = "本文「…までに/必着」"
        elif not got.date_start and _HELD_TAIL.match(tail):
            got.date_start = dt
            got.date_source = "本文「…時〜/開催」"
        if got.date_start and got.deadline:
            break
    return got
