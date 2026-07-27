#!/usr/bin/env python3
"""山陰の蚤の市オートコレクター — エントリポイント。

  python main.py                     # config.yaml どおりに収集して out/ に出力
  python main.py --months-ahead 2    # 今月＋2か月先まで
  python main.py --open              # 生成後にダッシュボードをブラウザで開く
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import yaml

from collector.filters import filter_and_score
from collector.renderers import dedup, to_html, to_ics, to_json
from collector.sources import REGISTRY

ROOT = pathlib.Path(__file__).parent


def load_config(path: pathlib.Path) -> dict:
    if path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="山陰の蚤の市オートコレクター")
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--months-ahead", type=int, default=None,
                    help="今月から何か月先まで拾うか（config を上書き）")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--open", action="store_true", help="生成後にHTMLを開く")
    args = ap.parse_args(argv)

    cfg = load_config(pathlib.Path(args.config))
    months_ahead = args.months_ahead if args.months_ahead is not None \
        else cfg.get("months_ahead", 1)
    target_prefs = cfg.get("target_prefectures", ["島根県", "鳥取県"])
    home_base = cfg.get("home_base", "浜田")
    enabled = cfg.get("sources", list(REGISTRY.keys()))
    out_dir = pathlib.Path(args.out_dir or cfg.get("out_dir", ROOT / "out"))
    out_dir.mkdir(parents=True, exist_ok=True)

    # 収集
    raw = []
    for name in enabled:
        src_cls = REGISTRY.get(name)
        if not src_cls:
            print(f"[warn] 未知のソース: {name}")
            continue
        print(f"[info] {name} を収集中 …")
        raw.extend(src_cls(months_ahead=months_ahead).collect())
    print(f"[info] 収集 {len(raw)} 件（全国・フィルタ前）")

    # フィルタ → 距離帯付与 → 重複排除
    events = dedup(filter_and_score(raw, target_prefs))
    print(f"[info] 山陰該当 {len(events)} 件（{'/'.join(target_prefs)}）")

    # 出力
    (out_dir / "events.json").write_text(to_json(events), encoding="utf-8")
    (out_dir / "sanin-nomi.ics").write_text(to_ics(events), encoding="utf-8")
    html_path = out_dir / "index.html"
    html_path.write_text(to_html(events, home_base=home_base), encoding="utf-8")
    print(f"[done] 出力先: {out_dir}")

    if args.open:
        import webbrowser
        webbrowser.open(html_path.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
