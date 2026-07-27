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

from .models import Event


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

    # ---- 取り込み ------------------------------------------------------
    ENRICHABLE = ("date_start", "date_end", "deadline",
                  "date_source", "deadline_source", "venue")

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
                    if new_v and not getattr(old, f, None):
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
        print(f"承認待ち {len(queue)}件  [y]公開 [n]捨てる [s]あとで [q]終了\n")
        for i, ev in enumerate(queue, 1):
            print(f"--- {i}/{len(queue)} ---")
            print(f"  {ev.title}")
            print(f"  {ev.city} / {ev.category or 'カテゴリ未判定'} / score={ev.score}")
            print(f"  判定理由: {ev.reason}")
            print(f"  {ev.url}")
            ans = input("  > ").strip().lower()
            if ans == "q":
                break
            if ans == "s":
                continue
            self.decide(ev.uid, approve=(ans == "y"))
        print("\n承認作業を終了しました。")
