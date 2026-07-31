"""手で足す掲載（data/manual.json）。

**大きな催しほど専用ページが作られ、フィードから漏れる。**

2026年8月1日の石州浜っ子夏まつり（浜田市最大の祭り・花火3,000発）は、記事では
なくランディングページ（`/lp/hamakko-natsumaturi/`）で告知されていた。はまナビの
記事カテゴリRSSは記事しか流さないので、**このLPは永久にフィードに乗らない。**
小さな催しは普通の記事として投稿されるので拾えるのに、町の一大イベントは専用
ページを作ってもらえるので拾えない。**規模と検出率が反比例している。**

問い合わせフォームで「うちの催しを載せてください」と来ても、載せる手段が
なかった（フォームも掲載方針も削除依頼の窓口も用意したのに、追加だけが無かった）。
ここがその口。

決めごと:

- **収集は data/manual.json を読み書きしない。** 手で入れた値は機械の抽出より
  優先で、消えないし上書きもされない（設計判断3「人の判断は上書きしない」の延長）
- **build のときだけ**公開データに合流する
- 同じURL（＝同じ uid）が自動収集で来たら、**手動側を採る**。自動側は公開データに
  出さず、承認キューにも入れない（同じものを2回判断させない）
- 出どころが追えるように `source` は `手動`、日付には `手入力` と入れる。
  根拠が追えることは公開物の生命線なので、ここは書き手に任せず必ず入れる

書き方は data/manual.example.json を見ること。
"""
from __future__ import annotations

import json
import pathlib
from datetime import date

from .models import Event

MANUAL_SOURCE = "手動"          # source に入れる値
HAND_TYPED = "手入力"           # date_source / deadline_source に入れる値
MANUAL_REASON = "手で追加した掲載"

# 人が書いてよい欄。**Event の全項目を許さない**のは、機械が埋める欄
# （score・review_state・date_source など）を手で書かせないため。
# `_` で始まる名前は覚え書きとして無視する（JSONにコメントが書けないので、
# 「なぜ手で足したか」を残す場所が要る）。
WRITABLE = (
    "title", "url", "city", "prefecture",
    "kind", "category", "tags", "status",
    "date_start", "date_end", "deadline",
    "venue", "organizer", "organizer_type",
    "published_at", "description",
)
REQUIRED = ("title", "url")
DATE_FIELDS = ("date_start", "date_end", "deadline", "published_at")
# 機械が入れる欄。手で書かれていたら黙って捨てず、書いても無駄だと伝える
FORCED = ("source", "date_source", "deadline_source", "review_state",
          "score", "reason")
KINDS = ("催し", "募集", "制度")


def _warn(where: str, msg: str) -> None:
    """公開を止めない。**止めると1件の書き間違いで暦全体が出なくなる。**

    かわりに毎回うるさく出す（collect でも build でも出るので、
    GitHub Actions の実行ログにも残る）。
    """
    print(f"[警告] {where}: {msg}")


def _parse_date(value, field: str, where: str) -> "date | None":
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        _warn(where, f"{field} の日付が読めません（2026-08-01 の形で書いてください）"
                     f": {value!r}")
        return None


def _to_event(d: dict, where: str) -> "Event | None":
    if not isinstance(d, dict):
        _warn(where, "{ } の形で書いてください。")
        return None

    for k in d:
        if k.startswith("_"):
            continue                      # 覚え書き
        if k in FORCED:
            _warn(where, f"{k} は自動で入るので書かなくて構いません（無視します）。")
        elif k not in WRITABLE:
            _warn(where, f"{k} という欄はありません（無視します）。"
                         f" 書ける欄: {', '.join(WRITABLE)}")

    vals = {k: v for k, v in d.items() if k in WRITABLE}
    for k in REQUIRED:
        if not str(vals.get(k) or "").strip():
            _warn(where, f"{k} が空です。この1件は載せません。")
            return None

    kind = str(vals.get("kind") or "催し").strip()
    if kind not in KINDS:
        _warn(where, f"kind は {' / '.join(KINDS)} のどれかです（催し として扱います）"
                     f": {kind!r}")
        kind = "催し"

    tags = vals.get("tags") or []
    if not isinstance(tags, list):
        _warn(where, "tags は [ ] の並びで書いてください（無視します）。")
        tags = []

    dates = {f: _parse_date(vals.get(f), f, where) for f in DATE_FIELDS}
    # 期間の終わりが始まりより前なら捨てる。**出口で結果を検証する**
    # （抽出器と同じ手当て。手書きでも打ち間違いは起きる）
    if dates["date_end"] and dates["date_start"] and \
            dates["date_end"] < dates["date_start"]:
        _warn(where, f"date_end が date_start より前です（date_end を捨てます）"
                     f": {dates['date_start']} 〜 {dates['date_end']}")
        dates["date_end"] = None

    ev = Event(
        title=str(vals["title"]).strip(),
        prefecture=str(vals.get("prefecture") or "島根県").strip(),
        date_start=dates["date_start"],
        date_end=dates["date_end"],
        url=str(vals["url"]).strip(),
        source=MANUAL_SOURCE,
        city=(str(vals["city"]).strip() if vals.get("city") else None),
        venue=(str(vals["venue"]).strip() if vals.get("venue") else None),
        description=str(vals.get("description") or ""),
        published_at=dates["published_at"],
        deadline=dates["deadline"],
        category=(str(vals["category"]).strip() if vals.get("category") else None),
        tags=[str(t) for t in tags],
        organizer=(str(vals["organizer"]).strip() if vals.get("organizer") else None),
        organizer_type=(str(vals["organizer_type"]).strip()
                        if vals.get("organizer_type") else None),
        kind=kind,
        status=str(vals.get("status") or "開催予定").strip(),
    )
    # ここから下は手で書かせない。出どころが必ず追える状態にする
    ev.review_state = "approved"          # 人が書いた時点で人の判断は済んでいる
    ev.score, ev.reason = 0, MANUAL_REASON
    if ev.date_start:
        ev.date_source = HAND_TYPED
    if ev.deadline:
        ev.deadline_source = HAND_TYPED
    return ev


def load_manual(path: pathlib.Path) -> list[Event]:
    """data/manual.json を読む。書き間違いは警告して飛ばし、公開は止めない。"""
    path = pathlib.Path(path)
    if not path.exists():
        return []
    name = path.name
    try:
        raw = json.loads(path.read_text("utf-8"))
    except Exception as e:
        _warn(name, f"読めませんでした（JSONの書き方を確かめてください）: {e}")
        return []
    if not isinstance(raw, list):
        _warn(name, "いちばん外側は [ ] の並びにしてください。")
        return []

    out: list[Event] = []
    seen: dict[str, str] = {}
    for i, d in enumerate(raw, 1):
        ev = _to_event(d, f"{name} の{i}件目")
        if not ev:
            continue
        if ev.uid in seen:
            _warn(name, f"{i}件目は同じURLが上にあります（あとの1件を載せません）"
                        f": {seen[ev.uid]}")
            continue
        seen[ev.uid] = ev.title
        out.append(ev)
    return out


def merge_for_build(approved: list[Event], manual: list[Event]) -> list[Event]:
    """公開データに手動分を合流する。**同じURLなら手動が勝つ。**

    自動収集が同じURLを拾っていても、手で書いた値のほうが正しい
    （そもそも機械が取れなかったから手で足している）。
    """
    if not manual:
        return list(approved)
    manual_uids = {e.uid for e in manual}
    kept = []
    for e in approved:
        if e.uid in manual_uids:
            print(f"[info] 手動の掲載を優先しました（自動収集分は出しません）: "
                  f"{e.title[:34]}")
            continue
        kept.append(e)
    return kept + list(manual)
