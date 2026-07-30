"""承認キュー。

自動で公開せず、いったん保留にして人が承認する。
公開物を一人で運用するときに品質を守る唯一の現実的な手段なので、
ここは意図的に自動化していない。

- pending.json  : 人の判断待ち
- approved.json : 公開してよいと判断したもの（サイトはここだけを見る）
- rejected.json : 捨てたもの。uidを覚えておき、次回以降は二度と聞かない
"""
from __future__ import annotations

import json
import pathlib
import re
import unicodedata

from .models import ERA_BASE, Event

# ---- 市またぎ重複の気づき（表示専用） ----------------------------------
#
# 県全体の催しは、市町ごとに違う切り口で流れてくる。
# 「しまねふるさとフェア２０２７（広島市）」（浜田市／参加申込）と
# 「しまねふるさとフェア出展者募集」（益田市／募集）は、対象読者も種別も
# 違うので、機械的に片方へ寄せると情報が失われる。
# かわりに承認画面で人に知らせる。データは変更しない。
#
# しきい値は緩めに倒している。気づけないほうが、似ていないものに警告が
# 出るより痛い（誤検知は人が読み飛ばすだけ）。
SIMILAR_THRESHOLD = 0.5
# 比較の邪魔になる記号・空白。全角半角はNFKCで寄せてから落とす
_DROP_CHARS = re.compile(
    r"[\s\-–—ー~〜・,.、。!?\"'「」『』【】〔〕()\[\]{}/|:;#*+=_@&%]")
# 「令和8年度」「第3回」のような頭の定型句。ここが揃っただけで似ていると
# 言われると、無関係な市の告知まで並んでしまう
_LEAD_BOILER = re.compile(
    r"^(?:(?:%s)\d+年度?|第\d+回|\d+年度?)+" % "|".join(ERA_BASE))


def normalize_title(title: str) -> str:
    """全角半角・空白・記号を寄せて比較しやすくする。"""
    s = unicodedata.normalize("NFKC", title or "").lower()
    return _DROP_CHARS.sub("", s)


def title_similarity(a: str, b: str) -> float:
    """0.0〜1.0。簡易判定でよい（人が見るだけなので）。"""
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return 0.0
    if na == nb or na in nb or nb in na:
        return 1.0
    ga = {na[i:i + 2] for i in range(len(na) - 1)}
    gb = {nb[i:i + 2] for i in range(len(nb) - 1)}
    if not ga or not gb:
        return 0.0
    dice = 2 * len(ga & gb) / (len(ga) + len(gb))
    # 催しの名前は頭に来る。定型句を外した先頭が6文字そろえば拾う
    core_a, core_b = _LEAD_BOILER.sub("", na), _LEAD_BOILER.sub("", nb)
    shared = 0
    for x, y in zip(core_a, core_b):
        if x != y:
            break
        shared += 1
    return max(dice, 0.6 if shared >= 6 else 0.0)


class ReviewQueue:
    def __init__(self, data_dir: pathlib.Path):
        self.dir = pathlib.Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.pending_path = self.dir / "pending.json"
        self.approved_path = self.dir / "approved.json"
        self.rejected_path = self.dir / "rejected.json"

    # ---- 入出力 --------------------------------------------------------
    def _load(self, path: pathlib.Path) -> list[Event]:
        if not path.exists():
            return []
        return [Event.from_dict(d) for d in json.loads(path.read_text("utf-8"))]

    def _save(self, path: pathlib.Path, events: list[Event]) -> None:
        path.write_text(
            json.dumps([e.to_dict() for e in events], ensure_ascii=False, indent=2),
            encoding="utf-8")

    @property
    def pending(self) -> list[Event]:
        return self._load(self.pending_path)

    @property
    def approved(self) -> list[Event]:
        return self._load(self.approved_path)

    @property
    def rejected(self) -> list[Event]:
        return self._load(self.rejected_path)

    def known_uids(self) -> set[str]:
        """一度でも判断したものは二度と聞かない。"""
        return {e.uid for e in self.pending + self.approved + self.rejected}

    # ---- 市またぎ重複の気づき ------------------------------------------
    def similarity_warnings(
        self, items: list[Event] | None = None,
        threshold: float = SIMILAR_THRESHOLD,
    ) -> dict[str, list[tuple[float, str, Event]]]:
        """uid → 似ているもの（似ている度・どこにあるか・そのもの）。

        比較先は公開中と承認待ちの両方。同じ日の収集で両市から同時に入ると
        どちらも未承認のまま並ぶので、pending 同士も見る必要がある。

        **表示専用。データは一切変更しない。**
        """
        items = self.pending if items is None else items
        pools = [("公開中", self.approved), ("承認待ち", self.pending)]
        out: dict[str, list[tuple[float, str, Event]]] = {}
        for ev in items:
            hits: list[tuple[float, str, Event]] = []
            for label, pool in pools:
                for other in pool:
                    if other.uid == ev.uid:
                        continue
                    score = title_similarity(ev.title, other.title)
                    if score >= threshold:
                        hits.append((score, label, other))
            if hits:
                hits.sort(key=lambda h: -h[0])
                out[ev.uid] = hits[:3]      # 多すぎると読まれない
        return out

    # ---- 取り込み ------------------------------------------------------
    # 空欄なら埋めるもの
    ENRICHABLE = ("date_start", "date_end", "deadline",
                  "date_source", "deadline_source", "venue", "session_count",
                  "other_dates")
    # 値が入っていても、毎回の抽出結果で上書きしてよいもの。
    #
    # 日付は機械が抽出した値なので、最新の抽出結果を正とする。埋めるだけにすると、
    # 複数回ある催し（救命講習は年6回）で次回が過ぎた瞬間に古い日付が残り、
    # is_past() が真になって、残りの回があるのに永久に畳まれる。
    # 繰り返しの催しでは毎回・確実に起きるぶん、古い日付が残るほうが有害。
    #
    # 「取れなかったら消さない」は下のループで守っているので、抽出器が条件に
    # 合わずに None を返した場合は既存の値がそのまま残る。
    #
    # venue は入れない（空欄のときだけ埋める）。
    # review_state と status は絶対に入れないこと。日付は機械の抽出値、
    # 承認は人が下した判断で、性質が違う。
    REFRESHABLE = ("date_start", "date_end", "deadline",
                   "date_source", "deadline_source", "session_count",
                   "other_dates")
    # 人の判断。どちらのリストにも入っていないことを起動時に確かめる
    assert not ({"review_state", "status"} & set(ENRICHABLE + REFRESHABLE))

    def ingest(self, events: list[Event], auto_approve: bool = True) -> dict:
        """新規は取り込み、既知のものは新しく分かった情報で更新する。

        既知を単に飛ばしていたため、後から取れた締切が捨てられていた（v1.5）。
        人の判断（review_state）は絶対に上書きしない。
        """
        approved, pending, rejected = self.approved, self.pending, self.rejected
        by_uid = {e.uid: (e, bucket) for bucket in ("a", "p", "r")
                  for e in (approved if bucket == "a" else
                            pending if bucket == "p" else rejected)}
        stats = {"new_auto": 0, "new_pending": 0, "skipped": 0, "updated": 0}
        touched = False

        for ev in events:
            if ev.uid in by_uid:
                old, _ = by_uid[ev.uid]
                changed = False
                for f in self.ENRICHABLE:
                    new_v = getattr(ev, f, None)
                    if not new_v:
                        continue                    # 取れなかったら既存を消さない
                    old_v = getattr(old, f, None)
                    if not old_v:
                        setattr(old, f, new_v)      # 空欄を埋める
                        changed = True
                    elif f in self.REFRESHABLE and new_v != old_v:
                        # 変わったことが分かる必要がある。collect のログに出れば
                        # GitHub Actions の実行ログにも残る
                        if f in ("date_start", "date_end", "deadline"):
                            print(f"[info] 日付を更新: {old.title[:34]} "
                                  f"{old_v} → {new_v}")
                        setattr(old, f, new_v)
                        changed = True
                if changed:
                    stats["updated"] += 1
                    touched = True
                else:
                    stats["skipped"] += 1
                continue
            if auto_approve and ev.review_state == "auto":
                ev.review_state = "approved"
                approved.append(ev)
                stats["new_auto"] += 1
            else:
                ev.review_state = "pending"
                pending.append(ev)
                stats["new_pending"] += 1

        self._save(self.approved_path, approved)
        self._save(self.pending_path, pending)
        if touched:
            self._save(self.rejected_path, rejected)
        return stats

    # ---- 承認作業 ------------------------------------------------------
    def decide(self, uid: str, approve: bool) -> bool:
        pending = self.pending
        target = next((e for e in pending if e.uid == uid), None)
        if not target:
            return False
        pending = [e for e in pending if e.uid != uid]
        if approve:
            target.review_state = "approved"
            self._save(self.approved_path, self.approved + [target])
        else:
            target.review_state = "rejected"
            self._save(self.rejected_path, self.rejected + [target])
        self._save(self.pending_path, pending)
        return True

    def review_cli(self) -> None:
        """端末で1件ずつ承認する。y=公開 / n=捨てる / s=あとで / q=終了"""
        queue = self.pending
        if not queue:
            print("承認待ちはありません。")
            return
        warnings = self.similarity_warnings(queue)
        print(f"承認待ち {len(queue)}件  [y]公開 [n]捨てる [s]あとで [q]終了\n")
        for i, ev in enumerate(queue, 1):
            print(f"--- {i}/{len(queue)} ---")
            print(f"  {ev.title}")
            print(f"  {ev.city} / {ev.category or 'カテゴリ未判定'} / score={ev.score}")
            print(f"  判定理由: {ev.reason}")
            print(f"  {ev.url}")
            for _, label, other in warnings.get(ev.uid, []):
                print(f"  ⚠ 似た催しが{label}: [{other.city}] {other.title[:34]}")
                print(f"    {other.url}")
            ans = input("  > ").strip().lower()
            if ans == "q":
                break
            if ans == "s":
                continue
            self.decide(ev.uid, approve=(ans == "y"))
        print("\n承認作業を終了しました。")
