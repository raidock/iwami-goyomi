"""実サイトの構造を写したHTMLでパーサを検証（ネット接続不要）。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from datetime import date

from collector.sources.good_antiques import GoodAntiques
from collector.filters import filter_and_score
from collector.models import parse_japanese_date_range

# GOOD ANTIQUES「中国・四国編」の本文構造を再現したスナップショット
SAMPLE = """
<article class="article__content">
  <h1>2026年3月開催の蚤の市一覧 ～中国・四国編～</h1>
  <p>2026年3月1日</p>
  <p>2026年3月に中国・四国で開催される蚤の市を日付順でご紹介。</p>
  <ul>
    <li>2026年3月8日(日)
      <ul>
        <li><a href="/blogs/places-events/896334482282">【島根県】つわの蚤の市</a></li>
        <li><a href="/blogs/places-events/628673587292">【山口県】普賢寺今昔市</a></li>
      </ul>
    </li>
    <li>2026年3月14日(土)〜15(日)
      <ul>
        <li><a href="/blogs/places-events/233247564863">【島根県】やすぎ骨董とガラクタ市</a></li>
      </ul>
    </li>
    <li>2026年3月29日(日)
      <ul>
        <li><a href="/blogs/places-events/264875966234">【鳥取県】くらよし大市</a></li>
      </ul>
    </li>
  </ul>
</article>
"""


def test_parse_extracts_all_events():
    evs = GoodAntiques().parse_article(SAMPLE)
    titles = [e.title for e in evs]
    assert "つわの蚤の市" in titles
    assert "やすぎ骨董とガラクタ市" in titles
    assert "くらよし大市" in titles
    assert len(evs) == 4


def test_prefecture_and_url():
    evs = {e.title: e for e in GoodAntiques().parse_article(SAMPLE)}
    assert evs["つわの蚤の市"].prefecture == "島根県"
    assert evs["くらよし大市"].prefecture == "鳥取県"
    assert evs["つわの蚤の市"].url.startswith("https://good-antiques.com/blogs/places-events/")


def test_date_range_parsing():
    s, e = parse_japanese_date_range("2026年3月14日(土)〜15(日)")
    assert s == date(2026, 3, 14) and e == date(2026, 3, 15)
    s, e = parse_japanese_date_range("2026年3月8日(日)")
    assert s == e == date(2026, 3, 8)


def test_sanin_filter_drops_yamaguchi():
    evs = GoodAntiques().parse_article(SAMPLE)
    kept = filter_and_score(evs, ["島根県", "鳥取県"])
    prefs = {e.prefecture for e in kept}
    assert prefs == {"島根県", "鳥取県"}          # 山口は落ちる
    assert kept[0].date_start <= kept[-1].date_start  # 日付順
    # 島根の県内デフォルトは日帰り帯、鳥取は小遠征
    tiers = {e.prefecture: e.distance_tier for e in kept}
    assert tiers["鳥取県"] == "excursion"


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    ok = 0
    for fn in fns:
        try:
            fn(); print(f"PASS {fn.__name__}"); ok += 1
        except Exception:
            print(f"FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{ok}/{len(fns)} passed")
    sys.exit(0 if ok == len(fns) else 1)
