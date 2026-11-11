"""読みもの「隣の町の灯り」（story.html）のテスト。

ここで守るのは、ページの見た目ではなく**事実の出どころ**:
  1. 数を手書きしていない（情報源の数・市町の数・件数は渡したデータから数える。設計判断15）
  2. 情報源の本文を載せない。催しは題名とリンクだけ（設計判断12）
  3. 終わったかどうかは publish.is_past() と同じ基準（設計判断4）
  4. 「毎朝6時」が、実際に収集が動く時刻と食い違っていない
  5. 連絡先が無いときに、行き先の無いボタンを置かない
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from datetime import date

import yaml

from collector.models import Event
from collector.publish import to_public_site
from collector.story import sample_events, to_story_page

ROOT = pathlib.Path(__file__).resolve().parents[1]
TODAY = date(2026, 11, 11)   # テストの「今日」は固定する（CLAUDE.md「開発のしかた」）

SITE = {
    "title": "石見暦",
    "url": "https://raidock.github.io/iwami-goyomi/",
    "contact": "https://forms.gle/5ayQ1xFfUFX9kva69",
    "operator": "T&N design",
}
SOURCES = [{"key": f"s{i}", "municipality": "浜田市"} for i in range(13)]

HEADINGS = [
    "隣の町で今夜なにがあるか、知っていますか。",
    "知るには、その町のサイトまで行くしかなかった。",
    "毎朝6時、13の窓をのぞく。",
    "並べてみたら、石見はにぎやかだった。",
    "それでも、載らなかった祭りがある。",
    "あなたの町の催しを、教えてください。",
]


def _ev(title, city, start=None, end=None, kind="催し", category="祭り・市・マルシェ",
        url=None, deadline=None, status="開催予定", description=""):
    return Event(title=title, prefecture="島根県", date_start=start, date_end=end,
                 url=url or f"https://example.jp/{title}", source="test", city=city,
                 kind=kind, category=category, deadline=deadline, status=status,
                 description=description)


# 実データの題名（data/approved.json・2026-11-10 収集分）。本文は試験用の目印
BODY_MARK = "この文は情報源の本文で、公開してはいけない"
EVENTS = [
    _ev("こどもまんなかマルシェ", "浜田市", date(2026, 11, 15)),
    _ev("第３０回　江津市石見神楽大会（2026.11.22開催）", "江津市", date(2026, 11, 22),
        category="神楽・伝統芸能", description=BODY_MARK),
    _ev("【津和野盆踊り】8/15　409回目の夏　殿町盆踊り開催のお知らせ", "津和野町",
        date(2026, 8, 15)),
    # 期間ものは終わりの日で見る（始まりは過去でも開催中）
    _ev("石見神楽定期公演", "浜田市", date(2026, 4, 1), date(2027, 3, 31),
        category="神楽・伝統芸能"),
    # 日付が分からないものは終わった扱いにしない
    _ev("温泉津あさいち", "大田市"),
    # 募集は締切で見る
    _ev("出場者大募集", "益田市", date(2026, 12, 20), kind="募集",
        deadline=date(2026, 10, 31), category=None),
]


def _text(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html)


def _page(events=EVENTS, site=SITE, sources=SOURCES) -> str:
    return to_story_page(site, sources, events, today=TODAY)


def test_six_headings_in_order():
    """6章が、ブリーフの見出しのとおりの順で並ぶ。"""
    text = _text(_page())
    pos = [text.find(h) for h in HEADINGS]
    assert -1 not in pos, [h for h, p in zip(HEADINGS, pos) if p == -1]
    assert pos == sorted(pos)


def test_source_count_comes_from_config_not_from_the_template():
    """情報源を足したら、見出しと本文の数も変わる（13を手書きしていない）。"""
    text = _text(_page(sources=SOURCES[:5]))
    assert "毎朝6時、5の窓をのぞく。" in text
    assert "市町と観光協会の5のサイト" in text
    assert "13" not in text


def test_windows_match_the_number_of_sources():
    assert _page().count('class="window"') == 13
    assert _page(sources=SOURCES[:5]).count('class="window"') == 5


def test_counts_use_the_same_rule_as_the_top_page():
    """「もう過ぎた催し」の数が、トップページの畳んだ節の数と同じになる。"""
    text = _text(_page())
    top = to_public_site([Event(**vars(e)) for e in EVENTS], today=TODAY, site=SITE)
    n_past = int(re.search(r"終わった催し・締切<span class='n'>(\d+)", top).group(1))
    assert n_past == 2   # 盆踊り（8/15）と、締切が過ぎた募集
    assert f"いま暦に載っているのは{len(EVENTS)}件。そのうち{n_past}件は、もう過ぎた催しです。" in text


def test_town_count_follows_the_published_events():
    text = _text(_page())
    assert "5つの市町の催しを1枚に並べると" in text


def test_no_events_means_no_numbers_and_no_list():
    """公開データが空でも壊れず、0件とは書かない。"""
    html = _page(events=[])
    assert "いま暦に載っているのは" not in html
    assert 'class="titles"' not in html
    assert HEADINGS[5] in _text(html)


def test_samples_are_upcoming_titles_with_links_only():
    """題名を見せるのは、これからの催しだけ。本文は出さない。"""
    picked = sample_events(EVENTS, TODAY)
    assert [e.title for e in picked] == [
        "こどもまんなかマルシェ",
        "第３０回　江津市石見神楽大会（2026.11.22開催）",
    ]
    html = _page()
    assert 'href="https://example.jp/こどもまんなかマルシェ"' in html
    assert BODY_MARK not in html


def test_samples_skip_cancelled_and_long_titles():
    events = [
        _ev("中止になった祭り", "浜田市", date(2026, 11, 20), status="中止"),
        _ev("とても長い題名" * 8, "江津市", date(2026, 11, 21)),
        _ev("君谷マーケット", "美郷町", date(2026, 11, 23)),
    ]
    assert [e.title for e in sample_events(events, TODAY)] == ["君谷マーケット"]


def test_samples_prefer_events_that_have_not_started_yet():
    """会期中の催しより、これから始まる催しを先に選ぶ。"""
    events = [
        _ev("石見神楽定期公演", "浜田市", date(2026, 4, 1), date(2027, 3, 31),
            category="神楽・伝統芸能"),
        _ev("第３０回　江津市石見神楽大会（2026.11.22開催）", "江津市", date(2026, 11, 22),
            category="神楽・伝統芸能"),
    ]
    assert sample_events(events, TODAY)[0].city == "江津市"


def test_samples_only_link_to_web_pages():
    events = [_ev("あやしいリンクの祭り", "浜田市", date(2026, 11, 20),
                  url="javascript:alert(1)")]
    assert sample_events(events, TODAY) == []
    assert "javascript:" not in _page(events=events)


def test_titles_are_escaped():
    html = _page(events=[_ev("<script>alert(1)</script>祭り", "浜田市", date(2026, 11, 20))])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_button_goes_to_the_contact_in_config():
    html = _page()
    assert ('<a class="btn" href="https://forms.gle/5ayQ1xFfUFX9kva69" target="_blank" '
            'rel="noopener">催しの掲載を依頼する</a>') in html
    mail = _page(site={**SITE, "contact": "info@example.jp"})
    assert '<a class="btn" href="mailto:info@example.jp">' in mail


def test_no_button_without_a_contact():
    html = _page(site={**SITE, "contact": ""})
    assert '<a class="btn"' not in html
    assert "【要設定】" in html


def test_shared_brand_and_page_url():
    html = _page()
    assert 'rel="icon" href="assets/iwami-goyomi-mark.svg"' in html
    assert ('property="og:url" content="https://raidock.github.io/iwami-goyomi/story.html"'
            in html)
    assert '<meta name="theme-color" content="#111A2E">' in html
    # ほかのページの色は変えていない
    assert '<meta name="theme-color" content="#eae6dc">' in to_public_site([], site=SITE)


def test_top_page_links_to_the_story_once():
    """既存ページからの導線は、トップのフッターに1行だけ。"""
    top = to_public_site([], site=SITE)
    assert top.count('href="story.html"') == 1
    assert '<a href="story.html">読みもの「隣の町の灯り」</a>' in top


def test_six_oclock_matches_the_workflow():
    """「毎朝6時」は、収集が実際に動く時刻（ワークフローの cron・UTC）と同じ。"""
    wf = yaml.safe_load(next((ROOT / ".github" / "workflows").glob("*.yml")).read_text("utf-8"))
    cron = wf[True]["schedule"][0]["cron"]      # PyYAML は on: を True と読む
    minute, hour = cron.split()[:2]
    assert minute == "0"
    assert (int(hour) + 9) % 24 == 6
    assert "毎朝6時" in _text(_page())


def test_reads_without_script_and_without_avoided_styles():
    """JavaScript に頼らず読める。避けると決めた見た目が紛れ込んでいない。"""
    html = _page()
    assert "<script" not in html
    assert "<input" not in html
    for avoided in ("italic", "monospace", "border-radius:999", "border-radius:50%"):
        assert avoided not in html, avoided


def test_motion_is_an_optional_layer_on_top_of_the_still_page():
    """動きは「減らす」設定で全部止まり、非対応のブラウザでは静止表示になる。

    静止表示が完成形で、動きの CSS はその後ろに1か所だけ。animation の宣言が
    その外に出ると、設定で止められない動きができてしまう。
    """
    html = _page()
    gate = "@media screen and (prefers-reduced-motion:no-preference){"
    assert html.count(gate) == 1
    still, motion = html.split(gate)
    motion = motion.split("</style>")[0]
    assert "animation" not in still
    assert "@keyframes" not in still
    # スクロール連動は、対応を確かめた中にだけ書く
    supported = "@supports (animation-timeline:view()){"
    assert motion.count(supported) == 1
    before_supports = motion.split(supported)[0]
    assert "animation-timeline" not in before_supports
    assert "view-timeline" not in before_supports
    # くり返し・点滅はしない。どの動きも1回きり
    assert "infinite" not in html
    assert "alternate" not in html


def _scenes(html: str) -> list[str]:
    return re.findall(r'<svg class="scene .*?</svg>', html, flags=re.S)


def test_pictures_are_decoration_and_carry_no_outside_files():
    """絵は6枚とも飾り（読み上げない）。写真や外のファイルを読み込まない。"""
    html = _page()
    scenes = _scenes(html)
    assert len(scenes) == 6
    for svg in scenes:
        assert 'aria-hidden="true"' in svg.split(">")[0]
        assert "<image" not in svg
        assert "http" not in svg.replace('xmlns="http://www.w3.org/2000/svg"', "")
        assert "<text" not in svg      # 絵の中に文字を置かない（伝えることは本文に書く）


def test_ids_do_not_collide_between_the_six_pictures():
    """塗り（グラデーション）の id が絵どうしで重なると、別の絵の塗りを拾ってしまう。"""
    ids = re.findall(r'\bid="([^"]+)"', _page())
    assert ids
    assert len(ids) == len(set(ids)), sorted(i for i in set(ids) if ids.count(i) > 1)
    # 参照している id は、全部どこかで定義されている
    refs = set(re.findall(r'url\(#([^)]+)\)', _page())) | set(re.findall(r'href="#([^"]+)"', _page()))
    assert refs <= set(ids), refs - set(ids)


def test_other_towns_lights_follow_the_town_count():
    """第1章の「ほかの町の灯り」は、市町の数から自分の町を引いた数。"""
    first = _scenes(_page())[0]
    assert first.count('class="far"') == 5 - 1     # EVENTS は5市町


def test_calendar_is_the_same_picture_three_times():
    """第4〜6章は同じ暦。違うのは「載らなかった日」の提灯だけ。

    2026年8月は31日。1日を除いた30個が、3枚とも灯っている。
    """
    ch4, ch5, ch6 = _scenes(_page())[3:]
    for svg in (ch4, ch5, ch6):
        assert len(re.findall(r'<g class="lit( gone)?"', svg)) == 30
        assert len(re.findall(r'<g class="lit gone"', svg)) == 14   # 過ぎた2週も消さない
    assert 'class="unlit"' not in ch4 and 'class="last"' not in ch4   # 第4章では描かない
    assert ch5.count('class="unlit"') == 1 and 'class="last"' not in ch5
    assert ch6.count('class="unlit"') == 1 and ch6.count('class="last"') == 1


def test_text_never_moves():
    """動くのは灯り（SVG の中）だけ。見出し・本文・ボタンに animation を当てない。"""
    html = _page()
    motion = html.split("@media screen and (prefers-reduced-motion:no-preference){")[1]
    motion = re.sub(r"/\*.*?\*/", "", motion.split("</style>")[0], flags=re.S)
    targets = re.findall(r"([^{}]+)\{[^{}]*animation(?:-name)?:", motion)
    assert targets, "動きの宣言が1つも見つからない"
    for selector in targets:
        for one in selector.split(","):
            assert one.strip().startswith((".scene-", ".is-")), one


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
