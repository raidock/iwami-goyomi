"""読みもの「隣の町の灯り」（story.html）。

石見暦がなぜ生まれ、何を載せ、何が載らなかったかを、石見に住む人へ向けて
6章で語るページ。最後に「催しの掲載を依頼する」ボタンがある。

守っていること（CLAUDE.md の設計判断に対応）:
  - 数は手書きしない。情報源の数は config.yaml、件数と市町の数は公開データから
    build のたびに数える（設計判断15）
  - 情報源の本文は載せない。催しは題名とリンクだけ（設計判断12）
  - 終わったかどうかは publish.is_past() と同じ基準、日付は日本時間（設計判断4・9）
  - 依存を足さない。CSS とインライン SVG だけで、JavaScript は使わない（設計判断6）

静止表示が完成形。動きは後から重ねるもので、無くても全文が読める。
"""
from __future__ import annotations

import calendar
import html as _html
import re
from datetime import date

from .models import Event, today_jst
from .publish import is_past
from .site_meta import MARK_PATH, STORY_PATH, STORY_TITLE, brand_meta

# 宵の藍。色はここ1か所（theme-color にも同じ値を渡す）
NIGHT = "#111A2E"

# 第4章の本文「祭り、市、神楽、講座、展示」の並びに合わせて、題名を1件ずつ見せる。
# 値は Event.category。選ぶためだけに使い、画面には出さない
_SAMPLE_CATEGORIES = [
    "祭り・市・マルシェ",
    "神楽・伝統芸能",
    "学び・講座",
    "文化・アート・クラフト",
]
_SAMPLE_TITLE_MAX = 40   # 長い題名は削らずに見送る（題名を書き換えない）

# 第4〜6章の暦の絵は、2026年8月の並び。右上の1点が8月1日（土）で、
# 石見暦が初めて「載らなかった」ことに気づいた祭りの日（CLAUDE.md の事故表）
_GRID_YEAR, _GRID_MONTH, _MISSING_DAY = 2026, 8, 1


def _count_label(n: int) -> str:
    """「8つの市町」「13の市町」。10以上に「つ」は付かない。"""
    return f"{n}つ" if n < 10 else str(n)


def _phrases(*parts: str) -> str:
    """見出しを文節で折り返す。語の途中で切れないよう、文節ごとに inline-block。"""
    return "".join(f'<span class="ph">{_html.escape(p)}</span>' for p in parts)


def sample_events(events: list[Event], today: date) -> list[Event]:
    """第4章で題名を見せる催しを選ぶ（題名とリンクだけを使う）。

    これからの催しを分野ごとに1件、なるべく違う市町から。人が選ぶのではなく
    規則で選ぶので、中止・終了・長すぎる題名は見送る。
    """
    upcoming = [
        e for e in events
        if (e.kind or "催し") == "催し" and e.status == "開催予定"
        and e.date_start and not is_past(e, today)
        and e.url.startswith(("http://", "https://"))
        and e.title and len(e.title) <= _SAMPLE_TITLE_MAX
    ]
    # まだ始まっていないものを先に。何か月も前に始まった会期ものが先頭に並ばないように
    upcoming.sort(key=lambda e: (e.date_start < today, e.date_start, e.url))
    picked: list[Event] = []
    for cat in _SAMPLE_CATEGORIES:
        pool = [e for e in upcoming if e.category == cat and e not in picked]
        if not pool:
            continue
        seen = {p.city for p in picked}
        fresh = [e for e in pool if e.city not in seen]
        picked.append((fresh or pool)[0])
    return picked


# ---- 絵（インライン SVG）------------------------------------------------
# どの絵も飾りで、伝えることは本文に全部書いてある（aria-hidden）。

def _svg(view: str, body: str, cls: str, style: str = "") -> str:
    style = f' style="{style}"' if style else ""
    return (f'<svg class="scene {cls}"{style} viewBox="{view}" aria-hidden="true" '
            f'focusable="false" xmlns="http://www.w3.org/2000/svg">{body}</svg>')


_HALO_DEF = ('<defs><radialGradient id="{id}">'
             '<stop offset="0" stop-color="#F0A63A" stop-opacity=".55"/>'
             '<stop offset="1" stop-color="#F0A63A" stop-opacity="0"/>'
             '</radialGradient></defs>')

# 第1章: 遠くの町の灯りの位置（x, y, 半径）。手前ほど大きい
_FAR_LIGHTS = [
    (164, 94, 2.2), (220, 72, 2.0), (279, 88, 2.1), (331, 61, 1.8),
    (374, 82, 2.0), (249, 42, 1.6), (304, 31, 1.5), (188, 52, 1.7),
    (358, 39, 1.5), (132, 66, 1.7), (92, 46, 1.5),
]


def scene_towns(n_towns: int) -> str:
    """第1章。自分の町の灯りが1つ、ほかの町の灯りは遠くに小さく。"""
    far = "".join(
        f'<circle class="far" style="--i:{i}" cx="{x}" cy="{y}" r="{r}"/>'
        for i, (x, y, r) in enumerate(_FAR_LIGHTS[:max(n_towns - 1, 0)]))
    body = (_HALO_DEF.format(id="halo-home")
            + '<path class="rule" d="M0 150 H400"/>'
            + far
            + '<circle cx="64" cy="136" r="24" fill="url(#halo-home)"/>'
            + '<circle class="lit" cx="64" cy="136" r="4.2"/>')
    return _svg("0 0 400 164", body, "scene-towns")


_ROW_LENGTHS = [272, 210, 334, 174, 251, 309, 195, 356, 232, 150,
                284, 205, 326, 182, 263, 345, 223, 165, 298, 242]
_ROWS_WITH_EVENT = (3, 10, 16)   # 20行に3行。お知らせのおよそ8〜9割は催し以外


def scene_notices() -> str:
    """第2章。行政のお知らせの行に、催しの小さな灯りが埋もれている。"""
    rows = []
    for i, length in enumerate(_ROW_LENGTHS):
        y = 8 + i * 14.5
        dot = (f'<circle class="buried" cx="10" cy="{y:g}" r="3.2"/>'
               if i in _ROWS_WITH_EVENT else "")
        rows.append(f'<g class="row" style="--i:{i}">{dot}'
                    f'<path class="rule" d="M24 {y:g} h{length}"/></g>')
    return _svg("0 0 400 292", "".join(rows), "scene-notices")


_WINDOW_SLICE = 5.25   # 窓1つが灯るのに使う区間。全体35%のおよそ15%ぶん


def scene_windows(n_sources: int) -> str:
    """第3章。情報源の数だけ窓があり、灯りが入っている。"""
    w, h, pitch = 34, 44, 56
    top = (n_sources + 1) // 2
    rows = [top, n_sources - top]
    parts, i = [], 0
    for r, count in enumerate(rows):
        x0 = (400 - (count * w + (count - 1) * (pitch - w))) / 2
        y = 6 + r * 70
        for c in range(count):
            x = x0 + c * pitch
            parts.append(
                f'<g class="window" style="--i:{i}">'
                f'<rect class="glow" x="{x + 4:g}" y="{y + 4}" width="{w - 8}" height="{h - 8}"/>'
                f'<path class="pane" d="M{x + w / 2:g} {y + 4} v{h - 8} M{x + 4:g} {y + h / 2:g} h{w - 8}"/>'
                f'<rect class="frame" x="{x:g}" y="{y}" width="{w}" height="{h}" rx="1"/>'
                f'</g>')
            i += 1
    # 窓が順に灯る間隔。全体の区間（35%）を窓の数で割り振る（動きの CSS が使う）
    step = (35 - _WINDOW_SLICE) / max(n_sources - 1, 1)
    return _svg("0 0 400 126", "".join(parts), "scene-windows", f"--step:{step:.3f}%")


def _grid_xy(row: int, col: int) -> tuple[int, int]:
    return 44 + col * 52, 22 + row * 40


def scene_calendar(missing: str) -> str:
    """第4〜6章。灯りが暦の形に並ぶ。

    missing: "absent"（第4章。描かない）/ "unlit"（第5章。輪郭だけ）/
             "lit"（第6章。灯りが入る）
    """
    weeks = calendar.Calendar(firstweekday=6).monthdayscalendar(_GRID_YEAR, _GRID_MONTH)
    dots, hole, i = [], "", 0
    for r, week in enumerate(weeks):
        for c, day in enumerate(week):
            if not day:
                continue
            x, y = _grid_xy(r, c)
            if day == _MISSING_DAY:
                if missing == "unlit":
                    hole = f'<circle class="unlit" cx="{x}" cy="{y}" r="5.5"/>'
                elif missing == "lit":
                    hole = (_HALO_DEF.format(id="halo-last")
                            + f'<circle class="unlit" cx="{x}" cy="{y}" r="5.5"/>'
                            + f'<circle class="halo" cx="{x}" cy="{y}" r="22" fill="url(#halo-last)"/>'
                            + f'<circle class="lit last" cx="{x}" cy="{y}" r="5.5"/>')
                continue
            # 上の2段は過ぎた週。暗くはなるが、消えない
            cls = "lit gone" if r in (1, 2) else "lit"
            # 集まる前に散らばっている位置（格子からのずれ）。乱数ではなく番号から決める
            dx, dy = (i * 37) % 81 - 40, (i * 53 + 17) % 61 - 30
            dots.append(f'<circle class="{cls}" style="--dx:{dx}px;--dy:{dy}px" '
                        f'cx="{x}" cy="{y}" r="5"/>')
            i += 1
    return _svg("0 0 400 244", "".join(dots) + hole, f"scene-calendar is-{missing}")


# ---- ページ ---------------------------------------------------------------

def _cta(contact: str) -> str:
    """行動のボタン。行き先は config.yaml の site.contact ただ一つ。"""
    c = contact.strip()
    if c.startswith(("http://", "https://")):
        return (f'<a class="btn" href="{_html.escape(c)}" target="_blank" '
                f'rel="noopener">催しの掲載を依頼する</a>')
    if "@" in c and " " not in c:
        return f'<a class="btn" href="mailto:{_html.escape(c)}">催しの掲載を依頼する</a>'
    # 連絡先の無いボタンは置かない。運用者に見える形で知らせる（about.py と同じ）
    return ('<p class="warn">【要設定】config.yaml の site.contact に'
            '連絡先を入れてください。</p>')


def to_story_page(site: dict, sources: list[dict], events: list[Event],
                  today: date | None = None) -> str:
    today = today or today_jst()
    title = site.get("title") or "石見暦"
    operator = site.get("operator") or ""

    n_sources = len(sources)
    n_towns = len({e.city for e in events if e.city})
    n_total = len(events)
    n_past = sum(1 for e in events if is_past(e, today))

    samples = sample_events(events, today)
    sample_html = ""
    if samples:
        items = "".join(
            f'<li><span class="where">{_html.escape(e.city or "")}</span>'
            f'<a href="{_html.escape(e.url)}" target="_blank" rel="noopener">'
            f'{_html.escape(e.title)}</a></li>' for e in samples)
        sample_html = f'<ul class="titles">{items}</ul>'

    count_html = ""
    if n_total:
        count_html = (f"<p>いま暦に載っているのは{n_total}件。"
                      f"そのうち{n_past}件は、もう過ぎた催しです。</p>")

    page_title = f"{STORY_TITLE}｜{title}"
    description = (f"{title}がなぜ生まれ、何を載せ、何が載らなかったか。"
                   "石見に住むあなたへの、短い読みものです。")
    fill = {
        "page_title": _html.escape(page_title),
        "description": _html.escape(description),
        "meta_html": brand_meta(site, page_title, description, STORY_PATH,
                                theme_color=NIGHT),
        "mark_path": MARK_PATH,
        "title": _html.escape(title),
        "h1": _phrases("隣の町で今夜", "なにがあるか、", "知っていますか。"),
        "h2": _phrases("知るには、", "その町のサイトまで", "行くしかなかった。"),
        "h3": _phrases("毎朝6時、", f"{n_sources}の窓をのぞく。"),
        "h4": _phrases("並べてみたら、", "石見は", "にぎやかだった。"),
        "h5": _phrases("それでも、", "載らなかった", "祭りがある。"),
        "h6": _phrases("あなたの町の催しを、", "教えてください。"),
        "n_sources": str(n_sources),
        "towns_label": _count_label(n_towns),
        "scene1": scene_towns(n_towns),
        "scene2": scene_notices(),
        "scene3": scene_windows(n_sources),
        "scene4": scene_calendar("absent"),
        "scene5": scene_calendar("unlit"),
        "scene6": scene_calendar("lit"),
        "sample_html": sample_html,
        "count_html": count_html,
        "cta": _cta(site.get("contact") or ""),
        "sign": (f'<p class="sign">{_html.escape(operator)}</p>' if operator else ""),
    }
    # 1回で差し込む（差し込んだ題名の中の [[…]] を、もう一度読まないため）
    return _SLOT.sub(lambda m: fill[m.group(1)], _TPL)


_SLOT = re.compile(r"\[\[(\w+)\]\]")

# 差し込みは [[名前]]。CSS の波かっこをそのまま書けるようにするため
# （about.py の str.format だと全部を二重にする必要がある）。
_TPL = """<!doctype html>
<html lang="ja"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>[[page_title]]</title>
<meta name="description" content="[[description]]">
<meta name="color-scheme" content="dark">
[[meta_html]]
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Zen+Old+Mincho:wght@700;900&family=Zen+Kaku+Gothic+New:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  :root{--night:#111A2E;--light:#F0A63A;--ink:#E9E6DC;--soft:#B4B9C8;
    --rule:#2B3A5C;--unlit:#5A6A8C;
    --col:34rem;--wide:44rem;--gutter:1.25rem}
  *{box-sizing:border-box}
  html{-webkit-text-size-adjust:100%}
  body{margin:0;background:var(--night);color:var(--ink);
    font-family:"Zen Kaku Gothic New",system-ui,sans-serif;
    font-size:1.0625rem;line-height:2.05;letter-spacing:.04em;
    line-break:strict;word-break:auto-phrase;overflow-wrap:anywhere;
    -webkit-font-smoothing:antialiased}
  a{color:inherit;text-underline-offset:.3em;text-decoration-thickness:1px;
    transition:color .15s}
  a:hover{color:var(--light)}
  a:focus-visible{outline:2px solid var(--light);outline-offset:4px;border-radius:2px}

  .top{max-width:var(--wide);margin:0 auto;padding:1.5rem var(--gutter) 0}
  .top a{display:inline-flex;align-items:center;gap:.55rem;min-height:44px;
    font-family:"Zen Old Mincho",serif;font-weight:700;font-size:1rem;
    letter-spacing:.12em;text-decoration:none}
  .top img{width:1.6rem;height:1.6rem}

  .ch{padding:clamp(5rem,15vh,9rem) var(--gutter)}
  .ch > *{max-width:var(--col);margin-left:auto;margin-right:auto}
  .ch > .scene{display:block;width:100%;height:auto}
  .ch1 > .scene{max-width:var(--wide)}
  .ch1{min-height:calc(100svh - 5rem);display:flex;flex-direction:column;
    justify-content:center;padding-top:2rem;padding-bottom:clamp(4rem,12vh,7rem)}
  .ch1 > *{width:100%}
  /* 第5章は前後の余白で一拍を置く。動きではなく、何もない画面で間を作る */
  .ch5{padding-top:clamp(10rem,30vh,18rem);padding-bottom:clamp(10rem,30vh,18rem)}

  h1,h2{font-family:"Zen Old Mincho",serif;font-weight:700;
    font-size:clamp(1.55rem,1.1rem + 2.2vw,2.35rem);line-height:1.6;
    letter-spacing:.06em;margin-top:0;margin-bottom:2.2rem}
  .ph{display:inline-block}
  p{margin-top:0;margin-bottom:1.5em}
  .ch > .scene + p,.ch > .scene + h1{margin-top:clamp(2.5rem,7vh,4rem)}
  h2 + .scene{margin-bottom:clamp(2.5rem,7vh,4rem)}

  /* 灯り。ここが完成形で、動きはこの上に重ねる */
  .lit{fill:var(--light)}
  .gone{opacity:.5}
  .far{fill:var(--light);opacity:.6}
  .buried{fill:var(--light);opacity:.45}
  .rule{stroke:var(--rule);stroke-width:2;stroke-linecap:round;fill:none}
  .unlit{fill:none;stroke:var(--unlit);stroke-width:1.5}
  .frame{fill:none;stroke:var(--unlit);stroke-width:1.5}
  .glow{fill:var(--light)}
  .pane{stroke:var(--night);stroke-width:2;fill:none}

  .titles{list-style:none;padding:0;margin-top:0;margin-bottom:1.8em;
    border-top:1px solid var(--rule)}
  .titles li{display:flex;gap:1em;align-items:baseline;
    border-bottom:1px solid var(--rule);line-height:1.7}
  .where{flex:0 0 4.2em;color:var(--soft);font-size:.875rem}
  /* 余白はリンクの側に持たせる（1行の題名でも押せる高さが44pxを下回らないように） */
  .titles a{flex:1;min-width:0;padding:.75em 0;overflow-wrap:anywhere}

  .act{margin-top:clamp(2rem,6vh,3.5rem)}
  .btn{display:inline-flex;align-items:center;justify-content:center;
    min-height:56px;padding:.8rem 2rem;background:var(--light);color:var(--night);
    font-weight:700;font-size:1.0625rem;letter-spacing:.08em;text-decoration:none;
    border-radius:2px;transition:background-color .15s}
  .btn:hover{background:#F6BC62;color:var(--night)}
  .hint{color:var(--soft);font-size:.875rem;line-height:1.9;margin-top:1.2rem}
  .more{display:flex;flex-wrap:wrap;gap:.4rem 2rem;margin-top:2.6rem;font-size:.9375rem}
  .more a{display:inline-flex;align-items:center;min-height:44px}
  .warn{color:var(--light);font-weight:700}

  footer{max-width:var(--wide);margin:0 auto;padding:2.5rem var(--gutter) 4rem;
    border-top:1px solid var(--rule);color:var(--soft);font-size:.875rem}
  .sign{margin:0;letter-spacing:.12em}

  @media (max-width:420px){
    .btn{display:flex;width:100%;padding-left:1rem;padding-right:1rem}
  }

  /* ---- 動き --------------------------------------------------------
     文字は動かさない。動くのは灯りだけで、1場面に1つ、1回きり。
     上の静止表示が完成形で、ここはその手前の状態（from）だけを書く。
     「動きを減らす」設定と印刷では、この節がまるごと効かない。 */
  @media screen and (prefers-reduced-motion:no-preference){
    @keyframes appear{from{opacity:0}}
    @keyframes gather{from{opacity:var(--from,.5);transform:translate(var(--dx),var(--dy))}}
    @keyframes bloom{from{opacity:0;transform:scale(.6)}}

    /* 第1章だけは時間で進む。ほかの町の灯りが、遠くに1つずつ現れる */
    .scene-towns .far{animation:appear 1200ms cubic-bezier(.2,.6,.3,1) both;
      animation-delay:calc(800ms + var(--i) * 600ms)}

    /* 第2〜6章は読者のスクロールに連動する。対応していないブラウザでは静止表示のまま */
    @supports (animation-timeline:view()){
      .scene{view-timeline-name:--scene;overflow:visible}

      /* 第2章: お知らせの行が上から順に現れる。灯りは暗いまま埋もれていく */
      .scene-notices .row{animation:appear linear both;animation-timeline:--scene;
        animation-range:cover calc(15% + var(--i) * 1.5%) cover calc(21% + var(--i) * 1.5%)}

      /* 第3章: 窓に左から順に灯りが入る */
      .scene-windows .glow{animation:appear linear both;animation-timeline:--scene;
        animation-range:cover calc(15% + var(--i) * var(--step))
                        cover calc(20.25% + var(--i) * var(--step))}

      /* 第4章: 散らばっていた灯りが、暦の形に集まる */
      .is-absent .lit{animation:gather cubic-bezier(.35,.1,.25,1) both;
        animation-timeline:--scene;animation-range:cover 0% cover 50%}
      .is-absent .gone{--from:.25}

      /* 第5章: 輪郭だけの円が1つ、ゆっくり見えてくる。ほかは何も動かさない */
      .is-unlit .unlit{animation:appear linear both;animation-timeline:--scene;
        animation-range:cover 30% cover 58%}

      /* 第6章: 行動のボタンが画面に入ると、輪郭だけだった円に灯りが入る */
      .ch6{timeline-scope:--cta}
      .ch6 .btn{view-timeline-name:--cta}
      .is-lit .last,.is-lit .halo{animation:appear cubic-bezier(.2,.6,.3,1) both;
        animation-timeline:--cta;animation-range:cover 0% cover 26%}
      .is-lit .halo{animation-name:bloom;transform-box:fill-box;transform-origin:center}
    }
  }
</style></head>
<body>
<header class="top">
  <a href="./"><img src="[[mark_path]]" width="64" height="64" alt="">[[title]]</a>
</header>
<main>
  <section class="ch ch1">
    [[scene1]]
    <h1>[[h1]]</h1>
    <p>同じ石見に住んでいても、隣の町の催しは、案外届いてきません。</p>
    <p>知らなかったのは、関心が無かったからではないはずです。</p>
  </section>

  <section class="ch ch2">
    <h2>[[h2]]</h2>
    [[scene2]]
    <p>各地に面白い取り組みやコミュニティがあるのに、それを知るには、その地域のウェブサイトを見に行くしかない。まとめたサイトがあればいいのに。</p>
    <p>[[title]]は、作り手自身のその実感から始まりました。</p>
    <p>市町のお知らせの多くは、入札や人事、計画案といった行政の内側の情報です。催しは、その中に埋もれています。</p>
  </section>

  <section class="ch ch3">
    <h2>[[h3]]</h2>
    [[scene3]]
    <p>毎朝6時、[[title]]は市町と観光協会の[[n_sources]]のサイトを見に行きます。</p>
    <p>催しらしいものを拾い、迷うものは人が目で確かめてから載せます。全部を機械に任せることはしていません。</p>
    <p>載せるのは、題名と日付と、元のページへのリンクだけです。</p>
  </section>

  <section class="ch ch4">
    <h2>[[h4]]</h2>
    [[scene4]]
    <p>祭り、市、神楽、講座、展示。[[towns_label]]の市町の催しを1枚に並べると、暦は思っていたよりずっと埋まっていました。</p>
    [[sample_html]]
    [[count_html]]
    <p>終わった催しも消していません。過ぎた日も、この土地の記録だからです。</p>
  </section>

  <section class="ch ch5">
    <h2>[[h5]]</h2>
    [[scene5]]
    <p>[[title]]を公開して最初の週のことです。</p>
    <p>浜田でいちばん大きな祭りが、開催の前日まで載っていませんでした。告知はおよそ1か月前に出ていたのに、仕組みの目が届く範囲の外にありました。人づてに聞くまで、気づけませんでした。</p>
    <p>載っていないものは、画面を見ても分かりません。</p>
    <p>無いものは、目に入らないからです。</p>
  </section>

  <section class="ch ch6">
    <h2>[[h6]]</h2>
    <p>仕組みが拾えない催しは、これからも必ずあります。それを知っているのは、その町に住むあなたです。</p>
    <p>地区の祭り、小さな市、公民館の講座。載っていないものを見つけたら、教えてください。</p>
    <p>それが、石見のこれからを一緒に編む最初の一歩になります。</p>
    [[scene6]]
    <div class="act">
      [[cta]]
      <p class="hint">催しの名前、日付、場所、元のページのURLが分かれば、書き添えてください。分かる範囲でかまいません。</p>
      <p class="more"><a href="./">[[title]]を見る</a><a href="about.html">掲載の方針</a></p>
    </div>
  </section>
</main>
<footer>
  [[sign]]
</footer>
</body></html>"""
