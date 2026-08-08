"""承認キュー。

自動で公開せず、いったん保留にして人が承認する。
公開物を一人で運用するときに品質を守る唯一の現実的な手段なので、
ここは意図的に自動化していない。

- pending.json  : 人の判断待ち
- approved.json : 公開してよいと判断したもの
- rejected.json : 捨てたもの。uidを覚えておき、次回以降は二度と聞かない
- manual.json   : 人が手で書いた掲載。**収集は読むだけで書き換えない**
                  （collector/manual.py。フィードに乗らない催しを足す口）
"""
from __future__ import annotations

import json
import pathlib
import re
import unicodedata
from datetime import date

from .manual import load_manual
from .models import ERA_BASE, Event, today_jst

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
        # 人が書く。**このクラスは絶対に書き込まない**（_save に渡さないこと）
        self.manual_path = self.dir / "manual.json"
        # 機械が is_finished() で黙って除外したものの記録。**却下（rejected）とは別。**
        # 却下は人の判断で二度と聞かない。こちらは機械の判定で、消せば次回また評価される
        # （詳しくは ingest() と main.py の説明）
        self.skipped_path = self.dir / "skipped.json"

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

    @property
    def manual(self) -> list[Event]:
        """手で書いた掲載。書き間違いは警告して飛ばす（公開は止めない）。"""
        return load_manual(self.manual_path)

    @property
    def skipped(self) -> list[Event]:
        """is_finished() で黙って除外したものの記録。人が audit で見られる。"""
        return self._load(self.skipped_path)

    def known_uids(self) -> set[str]:
        """一度でも判断したものは二度と聞かない。"""
        return {e.uid for e in
                self.pending + self.approved + self.rejected + self.manual}

    def skipped_uids(self) -> set[str]:
        """除外記録にあるもの。**known_uids() には混ぜない**（人の判断ではないため、
        `ingest()` の「既知」扱いにはしない）。collect 側で詳細ページの再取得だけを
        避けるのに使う。
        """
        return {e.uid for e in self.skipped}

    def prune_skipped(self, max_age_by_source: dict, default_max_age: int,
                      today: date) -> int:
        """除外記録から、情報源側の max_age_days を超えたものを消す。

        情報源のフィード自体がその年齢を超えた記事を返さなくなる
        （`build_sources` の max_age_days）ので、記録だけが残ると
        際限なく増える。消えた分は戻り値で報告する。
        """
        items = self.skipped
        if not items:
            return 0
        kept, removed = [], 0
        for e in items:
            max_age = max_age_by_source.get(e.source, default_max_age)
            ref = e.date_end or e.date_start or e.deadline or e.published_at
            if ref and (today - ref).days > max_age:
                removed += 1
                continue
            kept.append(e)
        if removed:
            self._save(self.skipped_path, kept)
        return removed

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

    # 分類器が毎回すべて出す値。**空でも正しい答えなのでそのまま上書きする。**
    #
    # 抽出（日付）とは性質が違う。抽出は失敗しうるので空欄は「まだ分からない」だが、
    # 分類は必ず答えを返すので空欄は「タグは無い」という答えそのもの。
    # ENRICHABLE と同じ「空なら飛ばす」で扱うと、**分類器を直しても公開中の
    # データから消えない。** 実際に2回踏んだ:
    #   - 「締切あり」タグを廃止したのに `tags: ['締切あり']` が2件残った
    #   - 種別をタイトル優先にしたのに `kind: 制度` `tags: ['随時']` が1件残った
    # どちらも手でデータを直して回復した。3回目を人の注意力で防ぐのは無理がある。
    CLASSIFIED = ("kind", "tags", "category", "score", "reason")

    # 取得元がそのまま持っている値。uid が同じなら同じ記事なので更新しない。
    FROM_SOURCE = ("title", "prefecture", "url", "source", "raw_date_text",
                   "city", "distance_tier", "description", "published_at",
                   "organizer", "organizer_type", "source_trust")

    # 人の判断。**どのリストにも入っていないことを起動時に確かめる。**
    HUMAN_DECIDED = ("review_state", "status")
    assert not (set(HUMAN_DECIDED)
                & set(ENRICHABLE + REFRESHABLE + CLASSIFIED + FROM_SOURCE))

    @staticmethod
    def is_finished(ev: Event, today: date) -> bool:
        """**初めて見る催しが、もう終わっているか。**

        フィードの窓を広げると、終わった催しがまとめて流れ込む
        （はまナビは3ページで94件・うち74件が終了済み）。
        一度も載らなかったものを終了済みとして足しても、畳んだ節が膨らむだけ。

        **設計判断4「終わった催しは消さない」とは別の話。** あちらは
        「載っていたものが終わった」記録を残すという意味で、価値はその過程にある。
        一度も載っていないものには、その過程がない。

        判定は素朴に、**分かっている日付が全部過去なら終わり**とする。

        - 日付が1つも分からない → **終わりとは言わない**（勝手に捨てない）
        - 開催日は未来・締切は過去 → 終わりではない（申込は締切っても催しは残る）
        - 期間ものは終わりの日で見る（`date_end`）

        `publish.is_past()` とは基準が違う。あちらは**画面での見せ方**を決めるもので、
        種別ごとに見る欄を変える（制度は常に現役、募集は締切だけ見る）。
        こちらは**そもそも取り込むか**を決める。混ぜないこと。
        """
        known = [d for d in (ev.date_end or ev.date_start, ev.deadline) if d]
        return bool(known) and all(d < today for d in known)

    def ingest(self, events: list[Event], auto_approve: bool = True,
               today: date | None = None) -> dict:
        """新規は取り込み、既知のものは新しく分かった情報で更新する。

        既知を単に飛ばしていたため、後から取れた締切が捨てられていた（v1.5）。
        人の判断（review_state）は絶対に上書きしない。

        **初めて見るもので、もう終わっているものは取り込まない**（is_finished）。
        既知には適用しない — 一度載ったものは畳んで残す（設計判断4）。
        """
        today = today or today_jst()
        approved, pending, rejected = self.approved, self.pending, self.rejected
        by_uid = {e.uid: (e, bucket) for bucket in ("a", "p", "r")
                  for e in (approved if bucket == "a" else
                            pending if bucket == "p" else rejected)}
        # 手で書いたものは触らない。**同じURLが自動収集で来ても、こちらが勝つ。**
        # キューにも入れない（人が書いた1件を、もう一度人に判断させない）。
        manual_uids = {e.uid for e in self.manual}
        stats = {"new_auto": 0, "new_pending": 0, "skipped": 0, "updated": 0,
                 "manual": 0, "finished": 0}
        touched = False
        newly_finished: list[Event] = []

        for ev in events:
            if ev.uid in manual_uids:
                stats["manual"] += 1
                continue
            if ev.uid in by_uid:
                old, _ = by_uid[ev.uid]
                changed = False
                # 分類器の出力は毎回そのまま反映する（空欄も答えのうち）
                for f in self.CLASSIFIED:
                    new_v = getattr(ev, f, None)
                    if getattr(old, f, None) != new_v:
                        setattr(old, f, new_v)
                        changed = True
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
            if self.is_finished(ev, today):
                # **静かに捨てない。** 取りこぼしは画面を見ても気づけないので、
                # ログだけが手がかりになる（GitHub Actions の実行ログに残る）。
                # あわせて data/skipped.json に記録する。次の収集では
                # skipped_uids() を見て詳細ページを再取得しない（無駄な
                # 再取得の防止。2026-08-08 measurements/is-finished-permanent-drop）。
                # **却下（rejected）とは別。** こちらは機械の判定で、記録を消せば
                # 次回また評価される
                when = ev.date_end or ev.date_start or ev.deadline
                stats["finished"] += 1
                print(f"[info] 既に終わっているため取り込みません: "
                      f"{ev.title[:34]}（{when}）")
                ev.review_state = "skipped"
                newly_finished.append(ev)
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
        if newly_finished:
            existing = {e.uid: e for e in self.skipped}
            for e in newly_finished:
                existing[e.uid] = e          # 上書き（最新の抽出結果を反映）
            self._save(self.skipped_path, list(existing.values()))
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
