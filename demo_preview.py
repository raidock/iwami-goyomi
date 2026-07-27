"""ネット接続なしで出力を確認するためのデモ（実イベント名を使用）。"""
import pathlib
from collector.models import Event
from collector.filters import filter_and_score
from collector.renderers import dedup, to_html, to_ics, to_json

RAW = [
    Event.from_listing("【島根県】つわの蚤の市", "2026年8月9日(日)", "https://good-antiques.com/blogs/places-events/896334482282", "good_antiques"),
    Event.from_listing("【島根県】やすぎ骨董とガラクタ市", "2026年8月14日(土)〜15(日)", "https://good-antiques.com/blogs/places-events/233247564863", "good_antiques"),
    Event.from_listing("【島根県】出雲ぜんざいマーケット", "2026年8月23日(日)", "https://good-antiques.com/blogs/places-events/000000000001", "good_antiques"),
    Event.from_listing("【鳥取県】くらよし大市", "2026年8月30日(日)", "https://good-antiques.com/blogs/places-events/264875966234", "good_antiques"),
    Event.from_listing("【山口県】周南蚤の市", "2026年8月30日(土)", "https://good-antiques.com/blogs/places-events/000000000009", "good_antiques"),  # 落ちるはず
    Event.from_listing("【島根県】石見銀山アンティーク市", "2026年9月13日(日)", "https://good-antiques.com/blogs/places-events/000000000002", "good_antiques"),
    Event.from_listing("【鳥取県】米子がいな骨董市", "2026年9月20日(日)〜21(月)", "https://good-antiques.com/blogs/places-events/000000000003", "good_antiques"),
    Event.from_listing("【島根県】松江水燈路古物市", "2026年9月27日(日)", "https://good-antiques.com/blogs/places-events/000000000004", "good_antiques"),
]

events = dedup(filter_and_score(RAW, ["島根県", "鳥取県"]))
out = pathlib.Path("out"); out.mkdir(exist_ok=True)
(out / "index.html").write_text(to_html(events, home_base="浜田"), encoding="utf-8")
(out / "sanin-nomi.ics").write_text(to_ics(events), encoding="utf-8")
(out / "events.json").write_text(to_json(events), encoding="utf-8")
print(f"{len(events)} events -> out/  (山口は除外されているはず)")
for e in events:
    print(f"  {e.date_start} {e.prefecture} {e.title} [{e.distance_tier}]")
