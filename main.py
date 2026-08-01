#!/usr/bin/env python3
"""石見暦（いわみごよみ）— 石見の催しを集めて公開する

  python main.py collect   # 集める → 仕分ける → 承認キューに入れる
  python main.py pending   # 承認待ちを一覧で見る
  python main.py review    # 承認する（1日5分の作業）
  python main.py build     # 承認済みだけで公開サイトを作る
  python main.py dedupe    # 重複をまとめる
  python main.py audit     # 情報源の在庫と突き合わせ、見ていない記事を出す（月1回）
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
from collector.classify import classify, decide_bucket
from collector.extract import TITLE_SOURCE, apply_extracted, extract_dates
from collector.models import extract_deadline, extract_held_date, today_jst
from collector.about import to_about_page
from collector.manual import merge_for_build
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
                feed_url=m.get("feed_url"),
                # 掲載日の足切りも情報源ごとに上書きできる。
                # **繰り返しの催しは記事を作り直さない**ので、毎週の天体観察会や
                # 毎月の朝市は掲載日が何年も前のまま生き続ける。全体を伸ばすと
                # 浜田市の公式RSSに残っていた2022年のコロナ情報まで拾うので、
                # イベント専用のフィードにだけ書くこと（config.yaml に理由を残す）
                max_age_days=m.get("max_age_days", cfg.get("max_age_days", 400)),
                url_include=m.get("url_include"),
                fetch_delay_sec=fetch_delay_for(m, cfg),
                # フィードを何ページさかのぼるか。効く情報源だけ config で指定する
                feed_pages=m.get("feed_pages", 1),
            ),
            m,
        ))
    return out


def enrich_with_detail_pages(events: list, cfg: dict) -> set:
    """仕分けを通過したものだけ詳細ページを見て、開催日と締切を取る。

    177件すべてではなく残った20件程度だけを取りに行くので、相手にも優しい。

    **取れなかったものの uid を返す。** 呼び出し側で取り込みを見送るため。
    詳細が読めないと日付が分からず、日付が分からないと `is_finished` が
    働かないので、**終わった催しが「これから」に居座る**（2026-08-01 に
    「新町商店街 土曜夜市」で発生。7/18・7/25 の催しが日付なしで公開に回った）。
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
    failed: set = set()
    for ev in events:
        if not ev.url:
            continue
        pacer = pacers.get(ev.source, default)
        got = None
        # 1回だけ取り直す。**相手の一時的な不調で取りこぼさないため。**
        # 2回に増やさないこと（失敗するときは続けて失敗するので、
        # 相手のサーバを余計に叩くだけになる。設計判断12）
        for attempt in (1, 2):
            pacer.wait()
            try:
                r = sess.get(ev.url, timeout=20)
                r.raise_for_status()
                r.encoding = r.apparent_encoding or r.encoding
                got = extract_dates(r.text, ref=ev.published_at)
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  [warn] 詳細取得に失敗: {ev.title[:24]} … {e}")
                    failed.add(ev.uid)
            finally:
                pacer.mark()
        if got is None:
            continue
        # 取れたときは入れる。既存を残す判断は ReviewQueue.ingest 側で行う
        # （こちらで握りつぶすと、繰り返しの催しの次回が更新されない）。
        # ただしタイトル由来の開催日だけは本文抽出に譲らない
        apply_extracted(ev, got)
        if got.date_start or got.deadline:
            hit += 1
    print(f"[info] 詳細ページ: {len(events)}件を確認し {hit}件から日付を取得")
    return failed


def cmd_collect(cfg: dict, queue: ReviewQueue, fetch_detail: bool = True,
                pages: int | None = None) -> None:
    raw = []
    health = {}
    for src, conf in build_sources(cfg):
        # `--pages` は**取りこぼしを一度だけ拾い直す**ための上書き。
        # 常用しないこと（毎日深く読むぶんだけ相手のサーバを叩く。設計判断12）。
        # paged が効かないフィードは2ページ目で打ち切るので、無駄は1回で済む
        if pages:
            src.feed_pages = pages
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
        # どこへ入れるかは `decide_bucket` に集めてある（観光協会のしきい値と、
        # 「人を通さず公開するならタイトルに根拠が要る」の2つ）。
        # **判断が散ると必ず食い違う**ので、ここでは呼ぶだけにする。
        #
        # auto のしきい値は 2 のまま。3 に上げると実データ17件で
        # auto 12→6 / review 4→10 となり、承認作業が2.5倍になる（2026-07 実測）。
        # 落ちる6件（ぶどうまつり・第3回岡見花火・和紙と灯りの夕べ・金唐紙ワーク
        # ショップ・inclusive×海 講演会・神楽定期公演ステッカー）は全部本物なので、
        # 人が見ても「はい」を6回押すだけになる。
        bucket = decide_bucket(v, ev.title, getattr(ev, "source_trust", "normal"))
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
        failed = enrich_with_detail_pages(kept, cfg)
        # **詳細が取れなかった新規は、その回は取り込まない。**
        # 日付が分からないまま公開に回ると、終わった催しが「これから」に居座る。
        # **消えるわけではない** — フィードに載っているかぎり次の収集で
        # また対象になる（uid は URL 基準なので同じものとして扱われる）。
        # 既知のものは対象外。既にある日付を消さないため、そのまま更新に回す。
        known = queue.known_uids()
        if hold := [e for e in kept if e.uid in failed and e.uid not in known]:
            for e in hold:
                print(f"[info] 詳細が読めなかったので今回は見送ります: {e.title[:34]}")
            print(f"        （{len(hold)}件。次の収集で取り直します）")
            kept = [e for e in kept if e not in hold]

    stats = queue.ingest(kept)
    print(f"[info] 自動承認 {stats['new_auto']}件 / 要承認 {stats['new_pending']}件 "
          f"/ 既知 {stats['skipped']}件 / 日付を追記 {stats.get('updated', 0)}件")
    if stats.get("finished"):
        print(f"[info] 初めて見るが既に終わっていた {stats['finished']}件は"
              f"取り込みません（一度載ったものは畳んで残します）")
    if stats.get("manual"):
        print(f"[info] 手動の掲載と同じURLだった {stats['manual']}件は取り込みません"
              f"（data/manual.json が優先）")
    if stats["new_pending"]:
        print(f"\n→ `python main.py review` で {stats['new_pending']}件を確認してください")


def cmd_build(cfg: dict, queue: ReviewQueue) -> None:
    # 手で書いた掲載（data/manual.json）はここで合流する。収集では触らない。
    # フィードに乗らない催し（LP告知の大きな祭りなど）を足す唯一の口なので、
    # 公開の直前に必ず通す。詳しくは collector/manual.py
    manual = queue.manual
    events = merge_for_build(
        [e for e in queue.approved if e.review_state == "approved"], manual)
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
    hand = f"（うち手動 {len(manual)}件）" if manual else ""
    print(f"[done] {len(events)}件{hand}で公開サイトを生成 → {out}/index.html")


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
        # 番号の行に印を出す。詳細だけだと20件を超えたときに見落とす
        # （同じ催しが4回投稿されていることがある。はまナビの朝のビーチヨガ）
        mark = "⚠ " if e.uid in warnings else "  "
        print(f"{i}. {mark}[{e.city}] {e.title}")
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


def _rough_when(ev) -> "object | None":
    """タイトルとRSS要約から読める**いちばん後ろの日付**。監査の目安に使う。

    詳細ページは見にいかないので（設計判断12）、ここで分かるのは
    「もう終わっていそうか」の当たりだけ。判定ではない。

    日付の読み方を書き足さないこと。`extract._find_dates` は
    「8月11日」も「8/11」も読むので、そのまま借りる（邑南町観光協会は
    タイトルが `8/11 石見やまんば祭り` の形）。
    """
    from collector.extract import _find_dates
    text = f"{ev.title} {ev.description}"
    found = [d for d, _ in _find_dates(text, ev.published_at)]
    if found:
        return max(found)
    return (ev.date_start or extract_held_date(text, ev.published_at)
            or extract_deadline(text, ev.published_at))


def cmd_audit(cfg: dict, queue: ReviewQueue, pages: int = 10) -> None:
    """情報源の在庫と突き合わせ、**一度も見ていない記事**を出す。

    「拾ったものが正しいか」は何度も測ってきたが、
    **「載るべきものが載っているか」は一度も測っていなかった。**
    浜田市最大の祭りが載っていないことに、人伝に聞くまで気づけなかったのはそのため。
    **無いものは画面を見ても目に入らない。** 数えるしかない。

    **読むだけ。データは1バイトも変更しない。** 載せるかは人が決める（設計判断3）。
    月1回くらい手で回せば足りる（毎日やる必要はない）。

    詳細ページは見にいかない（設計判断12）。日付はタイトルとRSS要約から
    分かるぶんだけなので、「終了？」は目安であって判定ではない。
    """
    known = queue.known_uids()
    today = today_jst()
    print(f"手元にあるもの: {len(known)}件（公開中・承認待ち・却下済み・手動）")
    print(f"フィードを {pages} ページまでさかのぼって突き合わせます。\n")
    total, total_over = 0, 0
    for src, conf in build_sources(cfg):
        src.feed_pages = pages          # 監査のときだけ深く読む
        try:
            got = src.collect()
        except Exception as e:
            print(f"[warn] {src.name}: {e}")
            continue
        # **仕分けで落ちるものは出さない。** それは「見ていない」のではなく
        # 「見て捨てた」もので、在庫の8〜9割を占める行政の告知（入札・予算・人事）。
        # 全部並べると読めなくなり、読まれない一覧は無いのと同じ。
        keep, unseen, over = 0, [], []
        for ev in got:
            v = classify(ev.title, ev.description)
            # collect と同じ判断を使う。**別々に書くと必ず食い違う**
            bucket = decide_bucket(v, ev.title, conf.get("trust", "normal"))
            if bucket == "drop":
                continue
            keep += 1
            if ev.uid in known:
                continue
            when = _rough_when(ev)
            (over if when and when < today else unseen).append((ev, v, bucket))
        total += len(unseen)
        total_over += len(over)
        print(f"── {src.name}: 在庫 {len(got)}件 / 仕分けを通る {keep}件 / "
              f"**キューに無い {len(unseen) + len(over)}件**"
              + (f"（うち終わっていそうなもの {len(over)}件）" if over else ""))
        for ev, v, bucket in unseen:
            print(f"   掲載{ev.published_at or '—'} [{bucket}/{v.score}] "
                  f"{ev.title[:38]}\n     {ev.url}")
    print(f"\nこれから開催かもしれないのに手元に無いもの: {total}件"
          f"（終わっていそうなものは別に {total_over}件）")
    print("載せたいものがあれば data/manual.json に足すか、"
          "config.yaml の feed_pages を広げてください。")
    print("**このコマンドはデータを1バイトも変更していません。**")


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
    manual = queue.manual
    print(f"  承認待ち : {len(queue.pending)}件")
    print(f"  公開中   : {len(queue.approved)}件")
    print(f"  却下済み : {len(queue.rejected)}件")
    # 手動分は build のときだけ合流するので、ここに出さないと存在を忘れる
    # （書き間違いで載っていないことにも、この行で気づける）
    print(f"  手動掲載 : {len(manual)}件  ({queue.manual_path})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="石見暦")
    ap.add_argument("command",
                    choices=["collect", "pending", "review", "build",
                             "dedupe", "audit", "health", "status"])
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--data-dir", default=None,
                    help="承認データの保存先（GitHub Actionsでは ./data を指定）")
    ap.add_argument("--no-fetch", action="store_true",
                    help="詳細ページを見にいかない（速いが日付が取れない）")
    ap.add_argument("--pages", type=int, default=None,
                    help="フィードを何ページさかのぼるか。"
                         "audit は既定10 / collect は既定 config.yaml の feed_pages。"
                         "**取りこぼしを一度だけ拾い直すとき**に collect で指定する")
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

    {"collect": lambda: cmd_collect(cfg, queue, fetch_detail=not args.no_fetch,
                                    pages=args.pages),
     "pending": lambda: cmd_pending(queue),
     "review": queue.review_cli,
     "build": lambda: cmd_build(cfg, queue),
     "dedupe": lambda: cmd_dedupe(cfg, queue),
     "audit": lambda: cmd_audit(cfg, queue, pages=args.pages or 10),
     "health": lambda: sys.exit(cmd_health(cfg)),
     "status": lambda: cmd_status(queue)}[args.command]()
    return 0


if __name__ == "__main__":
    sys.exit(main())
