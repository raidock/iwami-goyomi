#!/usr/bin/env python3
"""石見暦（いわみごよみ）— 石見の催しを集めて公開する

  python main.py collect   # 集める → 仕分ける → 承認キューに入れる
  python main.py pending   # 承認待ちを一覧で見る
  python main.py review    # 承認する（1日5分の作業）
  python main.py build     # 承認済みだけで公開サイトを作る
  python main.py dedupe    # 重複をまとめる
  python main.py health    # 情報源が生きているか確かめる
  python main.py status    # いまの状況を見る

蚤の市だけを集める旧版は main_nomi.py に残してあります。
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import yaml

from collector import USER_AGENT, __version__
from collector.classify import classify
from collector.extract import TITLE_SOURCE, apply_extracted, extract_dates
from collector.models import extract_deadline, extract_held_date
from collector.about import to_about_page
from collector.publish import to_public_site
from collector.renderers import to_ics, to_json
from collector.review import ReviewQueue
from collector.sources.base import DEFAULT_FETCH_DELAY_SEC, Pacer
from collector.sources.municipal_rss import MunicipalRSS
from collector.sources.oda_city import OdaCityRSS

ROOT = pathlib.Path(__file__).parent


def load_config(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}


def fetch_delay_for(m: dict, cfg: dict) -> float:
    """その情報源の取得間隔（秒）。情報源の指定 → 全体の既定値 の順に見る。

    間隔を全体で1つにしていると、robots.txt が `Crawl-delay: 5` を宣言している
    サイトに合わせた瞬間、関係のない情報源まで5秒待つことになる。
    かといって無視すれば設計判断12（情報源への礼儀）に反する。
    **相手が宣言した値は、その相手にだけ効かせる。**
    """
    return float(m.get("fetch_delay_sec", cfg.get("fetch_delay_sec",
                                                  DEFAULT_FETCH_DELAY_SEC)))


# 汎用RSSアダプターで足りない情報源だけ、ここで差し替える。
# config.yaml の key と対応する（config 側にもその旨のコメントを書いてある）。
# **増やすのは最後の手段。** まず config で足りないかを確かめること。
ADAPTERS = {
    # 大田市のフィードは掲載日を持たない（サイト全体の目次で pubDate が無い）。
    # 新着一覧HTMLから掲載日を補う。詳しくは collector/sources/oda_city.py
    "oda_city": OdaCityRSS,
}


def build_sources(cfg: dict) -> list[tuple[MunicipalRSS, dict]]:
    """(アダプター, その情報源の設定) の並びを返す。"""
    out = []
    for m in cfg.get("municipalities", []) + cfg.get("tourism", []):
        cls = ADAPTERS.get(m["key"], MunicipalRSS)
        out.append((
            cls(
                key=m["key"], site=m["site"], municipality=m["municipality"],
                feed_url=m.get("feed_url"), max_age_days=cfg.get("max_age_days", 400),
                url_include=m.get("url_include"),
                fetch_delay_sec=fetch_delay_for(m, cfg),
            ),
            m,
        ))
    return out


def enrich_with_detail_pages(events: list, cfg: dict) -> None:
    """仕分けを通過したものだけ詳細ページを見て、開催日と締切を取る。

    177件すべてではなく残った20件程度だけを取りに行くので、相手にも優しい。
    """
    import requests
    # 待ち時間は情報源ごとに数える。1つの時計で回すと、間隔の長い情報源に
    # 引きずられて他まで待つ（逆に、混ぜて均すと宣言を守れない）
    pacers = {m["key"]: Pacer(fetch_delay_for(m, cfg))
              for m in cfg.get("municipalities", []) + cfg.get("tourism", [])}
    default = Pacer(cfg.get("fetch_delay_sec", DEFAULT_FETCH_DELAY_SEC))
    sess = requests.Session()
    sess.headers.update({"User-Agent": USER_AGENT})
    hit = 0
    for ev in events:
        if not ev.url:
            continue
        pacer = pacers.get(ev.source, default)
        pacer.wait()
        try:
            r = sess.get(ev.url, timeout=20)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or r.encoding
            got = extract_dates(r.text, ref=ev.published_at)
        except Exception as e:
            print(f"  [warn] 詳細取得に失敗: {ev.title[:24]} … {e}")
            continue
        finally:
            pacer.mark()
        # 取れたときは入れる。既存を残す判断は ReviewQueue.ingest 側で行う
        # （こちらで握りつぶすと、繰り返しの催しの次回が更新されない）。
        # ただしタイトル由来の開催日だけは本文抽出に譲らない
        apply_extracted(ev, got)
        if got.date_start or got.deadline:
            hit += 1
    print(f"[info] 詳細ページ: {len(events)}件を確認し {hit}件から日付を取得")


def cmd_collect(cfg: dict, queue: ReviewQueue, fetch_detail: bool = True) -> None:
    raw = []
    health = {}
    for src, conf in build_sources(cfg):
        before = len(raw)
        for ev in src.collect():
            ev.organizer_type = conf.get("organizer_type", "自治体")
            ev.source_trust = conf.get("trust", "normal")
            raw.append(ev)
        health[src.name] = len(raw) - before
    print(f"[info] 収集 {len(raw)}件（仕分け前）")

    # 0件の情報源があれば知らせる。スクレイパーは静かに壊れるのが一番怖い
    dead = [k for k, n in health.items() if n == 0]
    if dead:
        print(f"[警告] 0件だった情報源: {', '.join(dead)}")
        print("        サイト構造が変わった可能性があります。RSSのURLを確認してください。")
    out = ROOT / cfg.get("out_dir", "out")
    out.mkdir(parents=True, exist_ok=True)
    import json as _json
    from datetime import datetime as _dt
    (out / "health.json").write_text(_json.dumps(
        {"checked_at": _dt.now().isoformat(timespec="seconds"), "per_source": health},
        ensure_ascii=False, indent=2), encoding="utf-8")

    kept, dropped = [], 0
    kinds: dict[str, int] = {}
    for ev in raw:
        v = classify(ev.title, ev.description)
        bucket = v.bucket
        # 観光協会のイベント専用RSSは、そもそもイベントしか流れてこない。
        # 自治体サイトと同じ厳しさで仕分けると、語彙にない催しを取りこぼす。
        #
        # ここでやるのは**しきい値を下げること**であって、除外を無効化することではない。
        # drop には2つの原因がある — 除外語を踏んだ -10 と、手がかりが何もない 0。
        # 拾いたいのは後者（語彙にない催し）だけなので、-10 は通さない。
        # 以前は無条件に上書きしていたため、観光協会から入札や通行止めが流れてきたら
        # そのまま承認キューに入る穴が空いていた（実害が出る前に塞いだ）。
        #
        # auto のしきい値は 2 のまま。3 に上げると実データ17件で
        # auto 12→6 / review 4→10 となり、承認作業が2.5倍になる（2026-07 実測）。
        # 落ちる6件（ぶどうまつり・第3回岡見花火・和紙と灯りの夕べ・金唐紙ワーク
        # ショップ・inclusive×海 講演会・神楽定期公演ステッカー）は全部本物なので、
        # 人が見ても「はい」を6回押すだけになる。
        # trust: high の根拠はスコアではなく情報源そのもの（観光協会が既に選んでいる）。
        # しきい値を上げるのは trust: high の存在理由と衝突する。
        if v.score > -10 and getattr(ev, "source_trust", "normal") == "high":
            bucket = "auto" if v.score >= 2 else "review"
        if bucket == "drop":
            dropped += 1
            continue
        ev.category, ev.tags = v.category, v.tags
        ev.score, ev.reason = v.score, v.reason
        ev.kind = v.kind
        # 年の推定は「今日」ではなく記事の掲載日を基準にする
        ref = ev.published_at
        text = f"{ev.title} {ev.description}"
        if not ev.date_start:
            # 由来を残す。これが立っていると詳細ページの本文抽出に負けない
            if held := extract_held_date(text, ref):
                ev.date_start, ev.date_source = held, TITLE_SOURCE
        ev.deadline = extract_deadline(text, ref)
        ev.review_state = bucket            # auto / review
        kinds[ev.kind] = kinds.get(ev.kind, 0) + 1
        kept.append(ev)

    rate = dropped / len(raw) if raw else 0
    print(f"[info] 仕分け: {dropped}件を除外（{rate:.0%}）→ 残り {len(kept)}件")
    if kinds:
        print("[info] 種別: " + " / ".join(f"{k} {n}件" for k, n in kinds.items()))

    if fetch_detail and kept:
        print(f"[info] 詳細ページを確認中（{len(kept)}件）…")
        enrich_with_detail_pages(kept, cfg)

    stats = queue.ingest(kept)
    print(f"[info] 自動承認 {stats['new_auto']}件 / 要承認 {stats['new_pending']}件 "
          f"/ 既知 {stats['skipped']}件 / 日付を追記 {stats.get('updated', 0)}件")
    if stats["new_pending"]:
        print(f"\n→ `python main.py review` で {stats['new_pending']}件を確認してください")


def cmd_build(cfg: dict, queue: ReviewQueue) -> None:
    events = [e for e in queue.approved if e.review_state == "approved"]
    out = ROOT / cfg.get("out_dir", "out")
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(
        to_public_site(events, region=cfg.get("region_name", "石見"),
                       site=cfg.get("site", {})), encoding="utf-8")
    (out / "events.json").write_text(to_json(events), encoding="utf-8")
    (out / "events.ics").write_text(to_ics(events, "石見の催し"), encoding="utf-8")
    srcs = cfg.get("municipalities", []) + cfg.get("tourism", [])
    (out / "about.html").write_text(
        to_about_page(cfg.get("site", {}), srcs), encoding="utf-8")
    print(f"[done] {len(events)}件で公開サイトを生成 → {out}/index.html")


def cmd_pending(queue: ReviewQueue) -> None:
    """承認待ちを一覧で見る（判断はしない）。

    review は1件ずつしか見えないので、先に全体を眺めるための窓口。
    """
    items = queue.pending
    if not items:
        print("承認待ちはありません。")
        return
    warnings = queue.similarity_warnings(items)
    print(f"承認待ち {len(items)}件\n")
    for i, e in enumerate(items, 1):
        print(f"{i}. [{e.city}] {e.title}")
        print(f"   〈{e.kind}〉{e.category or 'カテゴリ未判定'} / score={e.score} / {e.reason}")
        if e.date_start:
            print(f"   開催 {e.date_start}  ({e.date_source or '—'})")
        if e.deadline:
            print(f"   締切 {e.deadline}  ({e.deadline_source or '—'})")
        print(f"   {e.url}")
        # 市またぎの重複は自動で寄せない（対象読者も種別も違うことがある）。
        # 気づけるように出すだけ。
        for _, label, other in warnings.get(e.uid, []):
            print(f"   ⚠ 似た催しが{label}: [{other.city}] {other.title[:34]}")
    if warnings:
        print(f"\n⚠ の {len(warnings)}件は似たものがあります（別の催しのこともあります）")
    print(f"\n承認するには: python main.py review")


def cmd_dedupe(cfg: dict, queue: ReviewQueue) -> None:
    """URLが同じものをまとめる（v1.5の重複事故の後始末）。

    情報の多いほう（日付・締切を持つほう）を残す。
    """
    import json
    ap = queue.approved_path
    if not ap.exists():
        print("公開中のデータがありません。")
        return
    backup = ap.with_suffix(".before-dedupe.json")
    backup.write_text(ap.read_text("utf-8"), encoding="utf-8")

    items = queue.approved
    best: dict[str, object] = {}
    for e in items:
        key = e.url or f"{e.prefecture}|{e.title}"
        cur = best.get(key)
        # 情報が多いほうを残す
        score = sum(bool(getattr(e, f)) for f in
                    ("date_start", "deadline", "date_source", "deadline_source"))
        if cur is None or score > cur[1]:
            best[key] = (e, score)
    kept = [v[0] for v in best.values()]
    removed = len(items) - len(kept)
    queue._save(ap, kept)
    print(f"重複 {removed}件をまとめました（{len(items)}件 → {len(kept)}件）")
    print(f"バックアップ: {backup}")
    if removed:
        print("→ `python main.py build` でサイトを作り直してください")


def cmd_health(cfg: dict) -> int:
    """情報源が生きているか確かめる。0件があれば異常終了する。

    GitHub Actions の最後に置いておくと、壊れたときにメールが届く。
    """
    import json
    f = ROOT / cfg.get("out_dir", "out") / "health.json"
    if not f.exists():
        print("[警告] health.json がありません。先に collect を実行してください。")
        return 1
    d = json.loads(f.read_text("utf-8"))
    print(f"最終確認: {d['checked_at']}")
    bad = []
    for name, n in d["per_source"].items():
        mark = "✓" if n else "✗"
        print(f"  {mark} {name:14} {n}件")
        if not n:
            bad.append(name)
    if bad:
        print(f"\n[異常] {', '.join(bad)} が0件です。サイト構造の変更を疑ってください。")
        return 1
    print("\nすべての情報源が生きています。")
    return 0


def cmd_status(queue: ReviewQueue) -> None:
    print(f"  承認待ち : {len(queue.pending)}件")
    print(f"  公開中   : {len(queue.approved)}件")
    print(f"  却下済み : {len(queue.rejected)}件")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="石見暦")
    ap.add_argument("command",
                    choices=["collect", "pending", "review", "build",
                             "dedupe", "health", "status"])
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--data-dir", default=None,
                    help="承認データの保存先（GitHub Actionsでは ./data を指定）")
    ap.add_argument("--no-fetch", action="store_true",
                    help="詳細ページを見にいかない（速いが日付が取れない）")
    args = ap.parse_args(argv)

    # どのコードを動かしているのか毎回はっきりさせる。
    # 新旧のフォルダを取り違えて古いコードを動かす事故が実際に起きたため。
    print(f"石見暦（いわみごよみ）v{__version__}")
    print(f"  実行パス: {ROOT}")
    feats = []
    try:
        from collector.classify import detect_kind  # noqa
        feats.append("種別3分類(催し/募集/制度)")
    except ImportError:
        pass
    try:
        from collector.classify import HARD_EXCLUDE_RE  # noqa
        feats.append("正規表現除外")
    except ImportError:
        pass
    if (ROOT / "collector" / "extract.py").exists():
        feats.append("詳細ページからの日付抽出")
    if (ROOT / "tests" / "test_dedup.py").exists():
        feats.append("重複防止(uid安定化)")
    if (ROOT / "tests" / "test_wareki.py").exists():
        feats.append("観光協会+和暦対応")
    try:
        from collector.publish import is_past  # noqa
        feats.append("終了分の自動仕分け")
    except ImportError:
        pass
    if (ROOT / "tests" / "test_feed_discovery.py").exists():
        feats.append("RSS自動発見の改良")
    print(f"  搭載: {', '.join(feats) if feats else 'なし（旧バージョンです）'}\n")

    cfg = load_config(pathlib.Path(args.config))
    # 置き場は ./data ひとつ。--data-dir で上書きできるが、常用しないこと。
    # 以前は config.yaml が ~/iwami-events-data を指し、ワークフローだけが
    # --data-dir ./data を渡していたため、承認済み36件と45件の2つのキューが
    # 並存する事故を起こした（手元で build すると公開分より古いサイトができる）。
    # git が data/ を保持するので、コードの外に逃がす理由はもうない。
    _dd = pathlib.Path(args.data_dir or cfg.get("data_dir", "data")).expanduser()
    queue = ReviewQueue(_dd if _dd.is_absolute() else ROOT / _dd)

    {"collect": lambda: cmd_collect(cfg, queue, fetch_detail=not args.no_fetch),
     "pending": lambda: cmd_pending(queue),
     "review": queue.review_cli,
     "build": lambda: cmd_build(cfg, queue),
     "dedupe": lambda: cmd_dedupe(cfg, queue),
     "health": lambda: sys.exit(cmd_health(cfg)),
     "status": lambda: cmd_status(queue)}[args.command]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
