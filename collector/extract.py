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

from .models import _to_date, today_jst, wareki_to_seireki

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
    # 実サイトで見つけた言い回し（2026-07）
    "開催月日",      # 浜田市 一斉相談会【開催月日】。「開催日」には部分一致しない
    "開催月日時",
    "実施日",        # 浜田市 危険物取扱者保安講習「対面講習の実施日・会場」
    "実施日時",
    "会期",          # 浜田市 世界こども美術館「会期 7月4日～9月27日」
]
# 「◯◯期間」のうち、催しがその期間ずっと続くことを示す語。
# 「公募期間」「募集期間」は応募の受付窓であって開催期間ではない
# （江津 Go-Con の公募期間 5/18〜8/3 を開催日にしてはいけない）
PERIOD_EVENT_WORDS = ["実施", "開催"]
# それ自体が「催しが続く期間」を意味する見出し。「期間」の語を含まない。
# （かつて会期を PERIOD_EVENT_WORDS に入れていたが、あちらは「期間」を含む
#   見出しにしか効かないため一度も一致しない死にコードだった）
SELF_PERIOD_HEADS = ["会期"]

# ---------------------------------------------------------------- 日付の形
# 「8月3日（月曜日）」「12月13日（日）」「2026年8月3日」いずれも拾う
_DATE = re.compile(r"(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日")
_DATE_SLASH = re.compile(r"(?:(\d{4})\s*/\s*)?(\d{1,2})\s*/\s*(\d{1,2})")

# はまナビなどが使う【日時】【場所】形式のラベル。見出しタグではないので別で拾う
_BRACKET_LABEL = re.compile(r"[【〔\[]\s*([^】〕\]]{1,12})\s*[】〕\]]")

# 流し込み文中の手がかり。日付の「後ろ」に来る語
# 時刻は「午後5時」だけでなく「午後５時１５分まで」と分まで書かれることがある。
# 分を許していなかったため、浜田市お魚料理教室の申込締切
# 「８ 月２1 日（金） 午後５時１５分まで」が締切として拾えず、
# 代わりに下の _HELD_TAIL の「午後◯時」に当たって開催日にされていた。
_DEADLINE_TAIL = re.compile(
    r"(?:（[^）]{0,6}）|\([^)]{0,6}\)|\s)*"
    r"(?:正午|(?:午前|午後)?\s*\d{1,2}\s*時(?:\s*\d{1,2}\s*分)?)?\s*"
    r"(?:まで|までに|必着|消印有効|締切|締め切り)")
# 日付の「後ろ」に開演時刻が来ていれば開催日
_HELD_TAIL = re.compile(
    r"(?:（[^）]{0,6}）|\([^)]{0,6}\)|\s)*(?:午前|午後)\s*\d{1,2}\s*時|開演|開場|開催")


# タイトル（＋概要）から取った日付につける印。main.py の仕分けで立てる。
# これが立っているものは、詳細ページの本文抽出で上書きしない。
TITLE_SOURCE = "タイトル冒頭"


@dataclass
class Extracted:
    date_start: Optional[date] = None
    date_end: Optional[date] = None       # 切れ目なく続く期間の終わり
    deadline: Optional[date] = None
    date_source: str = ""        # どこから取ったか（承認画面に出す）
    deadline_source: str = ""
    session_count: Optional[int] = None   # 飛び石で複数回ある催しの回数


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


def _column_dates(cells: list[str], ref: Optional[date]) -> list[date]:
    """表の1列を上から順に読み、各行の日付を返す。

    「第1回…第8回」のように行が時間順に並ぶので、年が書かれていない場合は
    **前の行より前に戻ったら翌年** と読む。掲載日を基準にする _to_date だけだと、
    掲載より前に終わった第1回（6月20日）を翌年と誤読する。
    年が明記されている行（和暦変換後の「2026年5月16日」など）はそれに従う。
    """
    base = ref.year if ref else today_jst().year
    out: list[date] = []
    prev: Optional[date] = None
    for cell in cells:
        m = _DATE.search(cell)
        if not m:
            continue
        y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
        if y:
            year = int(y)
        elif prev is None:
            year = base
        else:
            year = prev.year + 1 if (mo, d) < (prev.month, prev.day) else prev.year
        try:
            dt = date(year, mo, d)
        except ValueError:
            continue
        # 先頭が掲載日より半年以上前になるのは、年の当てが外れている
        if prev is None and not y and ref and (ref - dt).days > 180:
            dt = date(year + 1, mo, d)
        out.append(dt)
        prev = dt
    return out


def _table_columns(soup: BeautifulSoup) -> list[tuple[str, list[str]]]:
    """見出しが横一列に並ぶ表を、(列見出し, その列の全セル) に分解する。

    _sections() は見出しの next_siblings を見るため、横組みの表では
    「講習日時」の隣にある同じ見出し行のセル（会場・定員…）しか拾えず、
    データ行に一度も届かない。浜田市は見出しセルが th ですらなく td のことも
    あるので、表そのものを列で読み直す。

    縦組み（<tr><th>日時</th><td>…</td></tr>）は既存の見出し経路が正しく扱うので、
    列が3つ以上あり、かつ見出し行に日付が無い表だけを対象にする。
    """
    out = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        head = rows[0].find_all(["th", "td"])
        if len(head) < 3:
            continue
        labels = [wareki_to_seireki(c.get_text(" ", strip=True)) for c in head]
        if any(_DATE.search(l) for l in labels):
            continue                      # 見出し行に日付がある＝縦組み
        body = [r.find_all(["th", "td"]) for r in rows[1:]]
        for j, label in enumerate(labels):
            if not label or len(label) > 24:
                continue
            col = [wareki_to_seireki(cells[j].get_text(" ", strip=True))
                   for cells in body if j < len(cells)]
            if col:
                out.append((label, col))
    return out


# class/id がこれらで始まる語を含む要素は、記事本文ではなくページの枠。
#
# 浜田市はフッターに「開庁時間 …12月29日～1月3日は閉庁」があり、32ページ中
# 14ページで「日付を含む見出し節」として拾われていた。いまは見出し語に当たらない
# ので無害だが、HELD_HEADS に「期間」のような短い語を足した瞬間に誤爆する。
#
# **header は入れない。** 江津市の main_header には記事タイトルそのものが入る。
# タイトルに開催日を書く情報源があり（はまナビ「8月22日（土）有福温泉…」）、
# 節の見出しを指す名前（main-header / section-header）も一般的。
# 実測でも header を除いて取れる日付は増えなかったので、危険なだけで益がない。
#
# **`sidebar` は入れてはいけない。** 実データ49ページで測ったとき、これだけが
# 公開中5件の開催日を消した（キッズフェス in GOTSU / 2026 江の川祭 ほか）。
# 江津市観光協会は記事本文を包む div に状態クラス `-sidebar-on` を付けている。
# 枠の名前と、枠の有無を示す名前は違う。`tests/test_extract.py` で固定している。
# 同じ理由で widget / recommend / breadcrumb / pickup も入れていない
# （損失は0だったが、直す実害も無かった。消せる範囲を広げるだけ損）。
#
# **`related` は未検証。** 実データ49ページで一度も踏まれていない（0件）。
# 関連記事一覧の名前として最も一般的なので入れているが、安全性は測れていない。
# 「測って安全と確認済み」ではないので、疑わしくなったら外してよい。
_NOISE_PARTS = ("footer", "copyright", "nav", "gnav", "related")
# 区切りをまたぐ名前は、区切りを取り払った全体の先頭で見る。
#
# 大田市観光協会（ginzan-wm.jp）は記事の下に「ほかの催し」の一覧を
# `div#sub_events_area` で置いている。中身は他の記事の見出しなので、
# そこの「【7月4日～8月30日まで】…」を拾って**全記事に同じ締切 2026-08-30**が
# 付いていた。関連記事一覧は本文ではないので、日付を見る前に落とす。
#
# 語に割ると sub / events / area で、どれも本文側にある普通の語だから
# 単語では拾えない（「events」を除去語にしたら催しの本文が消える）。
# かといって sub_events_area と名指しすると、このサイトのこのIDにしか効かない。
#
# subevents は実データで踏んで直った（偽締切3件が消え、本物の締切は残った）。
# **otherevents は未検証。** 49ページで一度も踏まれていない（0件）。
# 関連記事一覧の名前として一般的なので入れているが、安全性は測れていない。
_NOISE_JOINED = ("subevents", "otherevents")
_NOISE_SPLIT = re.compile(r"[-_\s]+")


def _is_noise(value: str) -> bool:
    """class/id の値1つが「記事本文ではない枠」を指しているか。"""
    v = str(value).lower()
    # 区切りで分けた語の**先頭一致**。単純な部分一致だと「innovation」が nav に
    # 当たってしまい、逆に完全一致だと「navi」「navbar」「gnav」が漏れる
    if any(p.startswith(w) for p in _NOISE_SPLIT.split(v) for w in _NOISE_PARTS):
        return True
    # 区切りを取り払った全体の先頭一致（sub_events_area / subEventsArea / sub-events）
    return _NOISE_SPLIT.sub("", v).startswith(_NOISE_JOINED)


def _strip_chrome(soup: BeautifulSoup) -> None:
    """記事本文ではない枠（フッター・ナビ・著作権表示・関連記事一覧）を落とす。"""
    for el in soup.find_all(True):
        if el.decomposed or el.attrs is None:
            continue                       # 親ごと消えた要素は飛ばす
        vals = []
        cls = el.get("class")
        vals += cls if isinstance(cls, list) else ([cls] if cls else [])
        if el.get("id"):
            vals.append(el.get("id"))
        if any(_is_noise(v) for v in vals):
            el.decompose()


# サイトが機械可読な形で宣言している期間。class に period を含む要素で見る。
# 実ページ235件で当たったのは ginzan-wm.jp の `period_box` だけだった。
#
# **`<time datetime="...">` は使わない。** 江津市観光協会は記事の掲載日を
# `<time datetime="2026-07-08" class="c-postTitle__date">` で持っており、
# これを期間として読むと7件すべての開催日が掲載日に化ける
# （キッズフェス in GOTSU が 7/18 → 7/8 になる）。構造化されていることと、
# それが催しの期間を指していることは別。
_PERIOD_BOX = re.compile(r"period", re.I)


def _structured_period(soup: BeautifulSoup,
                       ref: Optional[date]) -> tuple[list[date], str]:
    """宣言された期間を (日付の並び, ラベル) で返す。無ければ空。

    ginzan-wm.jp は
      `<div class="period_box"><span>イベント期間</span>
        2026年07月18日(土) ～ 08月09日(日)</div>`
    を持つ。**人手で書かれた本文より信頼できる。** 本文側は
    「8月31（金）」のように日が落ちたり、第1弾・第2弾・注記を1つの節に
    まとめて書いたりするが、宣言はテンプレートが出すので崩れない。

    日付が入っていない宣言もある（「イベント期間 (木)」だけの実例が1件）。
    その場合は空を返し、既存の見出しベース・文脈語ベースに任せる。
    """
    for el in soup.find_all(attrs={"class": _PERIOD_BOX}):
        label = el.get_text(" ", strip=True)
        dates = [d for d, _ in _find_dates(wareki_to_seireki(label), ref)]
        if dates:
            return dates, label
    return [], ""


_LABEL_WS = re.compile(r"[\s　]+")


def _norm_label(label: str) -> str:
    """見出しの中の空白を取り除いて比べる。

    江津市観光協会は【日　時】のように全角空白で字間を空ける。
    そのままでは「日時」に一致せず、開催日を1件も取れなかった。
    比較にはこれを使い、date_source に出す文字は元のまま残す。
    """
    return _LABEL_WS.sub("", label)


def _is_event_period(label: str) -> bool:
    """催しがその期間ずっと続くことを示す見出しか。

    「実施・応募期間」は実施＝催しが8/1から12/15まで続くという意味なので、
    始まりが開催日、終わりが date_end。
    「公募期間」「募集期間」「申込期間」は応募の受付窓であって開催期間ではない。

    修飾語のない裸の「期間」も開催期間として扱う。実ページ32件で「期間」を
    含む見出しを数えたところ、応募の窓・雇用期間はすべて修飾語付き
    （公募期間／募集期間／実施・応募期間／雇用形態・期間）で、裸の「期間」は
    催しの開催期間だけだった（はまナビ 海開き 7/18〜8/23）。
    「期間」を HELD_HEADS に入れると「募集期間」にも部分一致してしまうため、
    ここで語全体が「期間」のときだけを見る。
    """
    if label == "期間" or any(k in label for k in SELF_PERIOD_HEADS):
        return True
    return "期間" in label and any(w in label for w in PERIOD_EVENT_WORDS)


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


def extract_dates(html: str, ref: Optional[date] = None,
                  today: Optional[date] = None) -> Extracted:
    """詳細ページのHTMLから開催日と締切を取り出す。

    ref には記事の掲載日を渡す（年の推定に使う）。
    today は「次回」の判定に使う。省略時は日本時間の今日（テストからは固定値を渡す）。
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()
    _strip_chrome(soup)
    got = Extracted()
    today = today or today_jst()

    # ---- 層0: 複数回が横組みの表で並ぶもの ------------------------------
    # 救命講習（年6回）やお魚料理教室（全8回）のように、飛び石の日程が
    # 表で並ぶ。期間ではないので date_end は使わず、次回と回数だけを持つ。
    for label, col in _table_columns(soup):
        if not any(k in _norm_label(label) for k in HELD_HEADS):
            continue
        dates = sorted(set(_column_dates(col, ref)))
        if not dates:
            continue
        future = [d for d in dates if d >= today]
        got.date_start = future[0] if future else dates[-1]
        if len(dates) > 1:
            got.session_count = len(dates)
            got.date_source = f"表「{label}」の列（全{len(dates)}回・次回）"
        else:
            got.date_source = f"表「{label}」の列"
        break

    # ---- 層0': サイトが宣言している期間 ---------------------------------
    # 見出しベースより優先する。構造化された宣言は、見出しの直下にある人手の
    # テキストより信頼できる（本文は「8月31（金）」と日を落とすことがある）。
    #
    # 層0（横組みの表）はそのまま先に見る。あちらは飛び石の複数回を数える別の
    # 役目で、宣言と両方を持つページは実データに無い。無いものに順序を決めない。
    if not got.date_start:
        declared, label = _structured_period(soup, ref)
        if declared:
            # ラベルは日付の手前まで（「イベント期間 2026年07月…」→「イベント期間」）。
            # 既存の date_source と同じ読み方にする
            name = re.split(r"[\d０-９]", label, maxsplit=1)[0].strip(" 　:：")
            got.date_start = declared[0]
            got.date_source = f"構造化された期間欄「{name or '期間'}」"
            if len(declared) > 1:
                got.date_end = declared[-1]

    # ---- 層1: 見出しベース（【日時】形式も同じ扱い）---------------------
    plain = wareki_to_seireki(soup.get_text(" ", strip=True))
    sections = [(l, wareki_to_seireki(b)) for l, b in _sections(soup)]
    sections += _bracket_sections(plain)
    for label, body in sections:
        dates = _find_dates(body, ref)
        if not dates:
            continue
        name = _norm_label(label)            # 【日　時】を「日時」として比べる
        if not got.deadline and any(k in name for k in DEADLINE_HEADS):
            got.deadline = dates[0][0]
            got.deadline_source = f"見出し「{label}」"
        elif not got.deadline and any(k in name for k in PERIOD_HEADS):
            got.deadline = dates[-1][0]          # 期間は終わりが締切
            got.deadline_source = f"見出し「{label}」の終わり"

        # 締切を取ったかどうかとは独立に開催日を見る。ここを elif にしていたため、
        # 「実施・応募期間 8月1日〜12月15日」が締切に消費され、
        # スタンプラリーの開始日8/1が捨てられていた
        if not got.date_start and any(k in name for k in HELD_HEADS):
            got.date_start = dates[0][0]
            got.date_source = f"見出し「{label}」"
            if _is_event_period(name) and len(dates) > 1:
                got.date_end = dates[-1][0]
        elif not got.date_start and _is_event_period(name):
            got.date_start = dates[0][0]
            got.date_source = f"見出し「{label}」の始まり"
            if len(dates) > 1:
                got.date_end = dates[-1][0]

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


def apply_extracted(ev, got: Extracted) -> None:
    """詳細ページの抽出結果をイベントに反映する。

    **タイトル由来の開催日は本文抽出で上書きしない。**
    タイトルの日付は、書いた人がその記事の主題として選んだもの。対して本文には
    関連する日付が何個も混ざる（江津 Go-Con は1ページに7個）。
    カテゴリをタイトル優先で決めているのと同じ理屈（設計判断10）。

    取れなかったときに既存を消さないのは呼び出し側と同じ約束。
    """
    if got.date_start and ev.date_source != TITLE_SOURCE:
        ev.date_start = got.date_start
        ev.date_source = got.date_source
        ev.session_count = got.session_count
        if got.date_end:
            ev.date_end = got.date_end
    if got.deadline:
        ev.deadline = got.deadline
        ev.deadline_source = got.deadline_source
    drop_reversed_period(ev)


def drop_reversed_period(ev) -> bool:
    """期間の終わりが始まりより前なら、終わりを捨てる。単日として扱う。

    **抽出の失敗ではなく、結果の検証。** どんな抽出器でも起こりうるので出口に置く。

    実例（ginzan-wm.jp 夏休みイベント第2弾）:
      「■ 開催期間 2026年8月18日（火）～ 8月31（金）
        ※8月10日～8月17日の期間中は開催いたしませんのでご注意ください。」
    終わりの「8月31（金）」は**日が抜けていて**日付として読めないため、
    同じ節の最後の日付である注記の「8月17日」を終わりに採ってしまい、
    公開画面に「8月18日（火）〜8月17日」と出た。

    入口（「8月31」を日付として読む）は直さない。`8月31日〜9月1日` の一部を
    誤読しかねないため。注記の切り落としも、他のページで本物の日付を消す危険がある。

    捨てたことは必ず警告に出す。**抽出がおかしいことに気づける必要がある。**
    """
    if ev.date_start and ev.date_end and ev.date_end < ev.date_start:
        print(f"  [warn] 期間が逆転しているため終わりを捨てました: {ev.title[:24]} "
              f"{ev.date_start.month}/{ev.date_start.day} → "
              f"{ev.date_end.month}/{ev.date_end.day}")
        ev.date_end = None
        return True
    return False
