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
import math
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
# 6枚とも同じ夜の入り江の景色: 奥に山、沖に漁火、手前に赤瓦の家並み。
# 灯りは提灯として描く。位置は乱数を使わず、番号から決める（build のたびに同じ絵になる）。
#
# 章ごとに温度差をつける（品質基準 2026-11-12）。第2章は暗いまま、第4章がいちばん
# 華やか。華やかさは光の色と大小で作り、意味のある形（暦の7列・30個、冒頭の灯り1つ）
# は崩さない。

_W, _H = 1200, 500
_SEA = 408   # 水平線の y
# 幅の狭い画面では左右が切れる（高さを保って中央を見せる）。
# 意味のあるものは、スマホでも見えるこの範囲に置く
_SAFE_L, _SAFE_R = 285, 915

_ROOF, _ROOF_EDGE = "#3A2630", "#6E3D36"   # 石州瓦の赤を、夜の色に沈めたもの
_WALL = "#0E1628"
_ROPE = "#40507A"
_TEAL = "#1E5560"                          # 青緑。空の下端と海

# 灯りの色は3つ: (紙の中心, 中ほど, 縁, 骨, にじみ)
_TONES = {
    "a": ("#FFE2A0", "#F6B64E", "#D4851F", "#9A5A12", "#F0A63A"),   # 橙（差し色）
    "r": ("#FF9E6E", "#E8512D", "#B03418", "#7A2410", "#E8512D"),   # 朱
    "w": ("#FFFDF2", "#FFF0C8", "#EBCB86", "#B08C48", "#FFF0C8"),   # 黄みの白
}


def _svg(body: str, cls: str, style: str = "", align: str = "xMidYMid") -> str:
    style = f' style="{style}"' if style else ""
    return (f'<svg class="scene {cls}"{style} viewBox="0 0 {_W} {_H}" '
            f'preserveAspectRatio="{align} slice" aria-hidden="true" focusable="false" '
            f'xmlns="http://www.w3.org/2000/svg">{body}</svg>')


def _defs(k: int, extra: str = "", sky_from: float = 0, tones: str = "a",
          teal: bool = True, haze: float = .16) -> str:
    """場面ごとの塗り。id は場面の番号つき（1ページに6枚あるので重ならないように）。

    空の上端はページの地の色。sky_from までは地の色のままにする（上を切って見せる
    場面で、切り口に色の段差が出ないように）。teal のとき、空は藍から青緑へ移る。
    haze は、山の稜線に沿わせる橙の明るみの濃さ。
    """
    span = 1 - sky_from
    if teal:
        # 青緑は山の稜線より上で見え始める（山に隠れると、ぼかしが海にしか残らない）
        low = (f'<stop offset="{sky_from + span * .5:.2f}" stop-color="#13224A"/>'
               f'<stop offset="{sky_from + span * .68:.2f}" stop-color="{_TEAL}"/>')
    else:
        low = (f'<stop offset="{sky_from + span * .78:.2f}" stop-color="#131E38"/>'
               f'<stop offset="1" stop-color="#1B2848"/>')
    water = (   # 稜線の明るみと海。青緑を使わない場面（第2章）には置かない
        f'<linearGradient id="haze-{k}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="#F0A63A" stop-opacity="0"/>'
        f'<stop offset=".3" stop-color="#F0A63A" stop-opacity="{haze * .05:.3f}"/>'
        f'<stop offset=".6" stop-color="#F0A63A" stop-opacity="{haze * .3:.2f}"/>'
        f'<stop offset="1" stop-color="#F6B64E" stop-opacity="{haze:.2f}"/></linearGradient>'
        f'<linearGradient id="sea-{k}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="#1A4652"/><stop offset=".5" stop-color="#132B45"/>'
        f'<stop offset="1" stop-color="#101A33"/></linearGradient>') if teal else ""
    lights = "".join(
        f'<radialGradient id="halo-{t}-{k}">'
        f'<stop offset="0" stop-color="{_TONES[t][4]}" stop-opacity=".5"/>'
        f'<stop offset=".45" stop-color="{_TONES[t][4]}" stop-opacity=".14"/>'
        f'<stop offset="1" stop-color="{_TONES[t][4]}" stop-opacity="0"/></radialGradient>'
        f'<radialGradient id="paper-{t}-{k}" cx=".5" cy=".42" r=".7">'
        f'<stop offset="0" stop-color="{_TONES[t][0]}"/>'
        f'<stop offset=".5" stop-color="{_TONES[t][1]}"/>'
        f'<stop offset="1" stop-color="{_TONES[t][2]}"/></radialGradient>'
        for t in tones)
    return (
        f'<defs>'
        f'<linearGradient id="sky-{k}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="{sky_from:g}" stop-color="{NIGHT}"/>'
        f'<stop offset="{sky_from + span * .3:.2f}" stop-color="#0C1426"/>{low}'
        f'</linearGradient>{water}{lights}'
        f'<linearGradient id="foot-{k}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{NIGHT}" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="{NIGHT}"/></linearGradient>'
        f'<linearGradient id="edge-{k}">'
        f'<stop offset="0" stop-color="{NIGHT}"/>'
        f'<stop offset=".06" stop-color="{NIGHT}" stop-opacity="0"/>'
        f'<stop offset=".94" stop-color="{NIGHT}" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="{NIGHT}"/></linearGradient>'
        f'{extra}</defs>')


def _lantern_defs(k: int, tones: str = "a") -> str:
    """提灯のかたち（灯っているもの lan-色 / 灯っていないもの off）。中心が原点。"""
    def ribs(color: str) -> str:
        out = []
        for f in (-0.5, 0, 0.5):
            half = 9.6 * math.sqrt(1 - f * f)
            out.append(f'<path d="M{-half:.1f} {f * 13.5:.1f}q{half:.1f} 2.4 {2 * half:.1f} 0" '
                       f'stroke="{color}" stroke-width=".8" fill="none" opacity=".55"/>')
        return "".join(out)

    def caps(color: str) -> str:
        return (f'<rect x="-5.5" y="-16.5" width="11" height="3.4" rx="1" fill="{color}"/>'
                f'<rect x="-5" y="12.9" width="10" height="3" rx="1" fill="{color}"/>')

    lit = "".join(
        f'<g id="lan-{t}-{k}"><ellipse rx="10" ry="13.5" fill="url(#paper-{t}-{k})"/>'
        f'{ribs(_TONES[t][3])}{caps("#2A1B10")}</g>' for t in tones)
    return (lit + f'<g id="off-{k}"><ellipse rx="10" ry="13.5" fill="{NIGHT}" stroke="#5A6A8C" '
            f'stroke-width="1.4"/>{ribs("#5A6A8C")}{caps("#5A6A8C")}</g>')


def _use(ref: str, x: float, y: float, s: float) -> str:
    return f'<use href="#{ref}" transform="translate({x:g} {y:g}) scale({s:g})"/>'


def _halo(k: int, x: float, y: float, r: float, cls: str = "", tone: str = "a") -> str:
    cls = f' class="{cls}"' if cls else ""
    return f'<circle{cls} cx="{x:g}" cy="{y:g}" r="{r:g}" fill="url(#halo-{tone}-{k})"/>'


def _lantern(k: int, x: float, y: float, s: float, cls: str = "lit", style: str = "",
             tone: str = "a", glow: float = 46) -> str:
    """灯った提灯1つ（にじみつき）。動かすときは、この g ごと動かす。"""
    style = f' style="{style}"' if style else ""
    return (f'<g class="{cls}"{style}>{_halo(k, x, y, glow * s, tone=tone)}'
            f'{_use(f"lan-{tone}-{k}", x, y, s)}</g>')


def _reflect(x: float, tone: str, width: float, rows: int = 4, strength: float = .5) -> str:
    """水面に落ちる灯りの映り。短い横線を、下へ行くほど細く薄く。"""
    out = []
    for j in range(rows):
        w = width * (1 - j * .17)
        dx = (-1, 1.5, -2, 1)[j % 4]
        out.append(f'<path d="M{x - w / 2 + dx:.1f} {_SEA + 5 + j * 6.5:.1f}h{w:.1f}" '
                   f'opacity="{strength * (1 - j * .2):.2f}"/>')
    return (f'<g stroke="{_TONES[tone][4]}" stroke-width="1.8" stroke-linecap="round">'
            f'{"".join(out)}</g>')


def _ridge(base: float, amp: float, seed: float) -> str:
    """山の稜線。正弦を重ねて決める。"""
    pts = []
    for x in range(0, _W + 24, 24):
        y = base - amp * (0.55 * math.sin(x / 190 + seed) + 0.3 * math.sin(x / 83 + seed * 2.3)
                          + 0.15 * math.sin(x / 37 + seed * 4.1))
        pts.append(f"{x},{y:.0f}")
    return f'M0,{_H}L' + "L".join(pts) + f'L{_W},{_H}Z'


def _stars(clear: tuple[int, int, int, int] | None = None, big: bool = False) -> str:
    """星。clear（左, 上, 右, 下）の中には置かない（暗い提灯ごしに透けて見えるため）。

    big のとき、粒の大きさの差を広げる（華やかな場面で使う）。
    """
    out = []
    for i in range(46):
        x, y = (i * 263 + 71) % _W, (i * 149 + 23) % 260
        if clear and clear[0] < x < clear[2] and clear[1] < y < clear[3]:
            continue
        r = 0.6 + ((i * 7) % 5) * 0.18
        o = 0.18 + ((i * 11) % 6) * 0.07
        if big and i % 4 == 0:
            r, o = r * 2.1, min(o + .3, .85)
        out.append(f'<circle cx="{x}" cy="{y}" r="{r:.2f}" opacity="{o:.2f}"/>')
    return f'<g fill="#E9E6DC">{"".join(out)}</g>'


_BOATS = (96, 168, 262, 930, 1010, 1124)   # 沖の漁火


def _night(k: int, clear: tuple[int, int, int, int] | None = None, teal: bool = True,
           big_stars: bool = False, haze_y: int = 372) -> str:
    """夜空・星・山並み・海。どの場面でも動かさない。"""
    s = f'<rect width="{_W}" height="{_H}" fill="url(#sky-{k})"/>'
    s += _stars(clear, big_stars)
    # 山並みは、空が青緑へ移る場面では少し青緑に寄せる
    far, near = ("#15294A", "#173349") if teal else ("#16223D", "#1A2947")
    if teal:   # 水平線の上の、橙のにじみ（山の向こうの明るみ）
        # 稜線に沿う細い帯にする（広く敷くと、青緑と混ざって濁る）
        s += f'<rect y="{haze_y - 110}" width="{_W}" height="110" fill="url(#haze-{k})"/>'
    s += f'<path d="{_ridge(322, 50, 0.6)}" fill="{far}"/>'
    s += f'<path d="{_ridge(378, 30, 2.1)}" fill="{near}"/>'
    sea = f"url(#sea-{k})" if teal else "#131E36"
    s += f'<rect y="{_SEA}" width="{_W}" height="{_H - _SEA}" fill="{sea}"/>'
    s += f'<path d="M0 {_SEA}H{_W}" stroke="#2B3A5C" stroke-width="1.2"/>'
    for i, x in enumerate(_BOATS):
        y = _SEA + 5 + (i % 2) * 3
        s += (f'<circle cx="{x}" cy="{y}" r="1.6" fill="#F0A63A" opacity=".75"/>'
              f'<path d="M{x} {y + 4}v9" stroke="#F0A63A" opacity=".22"/>')
    return s


def _finish(k: int) -> str:
    """絵の下と左右を、ページの地の色へなじませる。"""
    return (f'<rect y="{_H - 16}" width="{_W}" height="16" fill="url(#foot-{k})"/>'
            f'<rect width="{_W}" height="{_H}" fill="url(#edge-{k})"/>')


def _house(x: float, top: float, w: float, rise: float) -> str:
    """赤瓦の家1軒（屋根と壁）。壁は絵の下端まで。"""
    return (f'<path d="M{x - 10:g} {top:g}L{x + w / 2:g} {top - rise:g}L{x + w + 10:g} {top:g}Z" '
            f'fill="{_ROOF}" stroke="{_ROOF_EDGE}" stroke-width="1.2" stroke-linejoin="round"/>'
            f'<rect x="{x:g}" y="{top:g}" width="{w:g}" height="{_H - top:g}" fill="{_WALL}"/>')


_WINDOW_FILLS = ("#F0A63A", "#FFD98A", "#F3B45A", "#EE8A45")   # 橙〜黄〜朱寄り


def _houses(k: int, lit: bool) -> str:
    """手前の家並み。海が見えるよう低く置く。lit のとき、どの家の窓にも灯りがある。"""
    out, x, i = [], -30, 0
    while x < _W + 40:
        w, h, rise = 92 + (i * 37) % 58, 38 + (i * 23) % 22, 16 + (i * 13) % 10
        top = _H - h
        out.append(_house(x, top, w, rise))
        if lit:
            # 広い家には窓が2つ。色味と大きさを少しずつ変える
            for n in range(2 if w > 118 else 1):
                wx = x + 14 + (i * 17 + n * 53) % (w - 40)
                ww, wh = 11 + (i + n) % 3 * 2, 11 + (i * 2 + n) % 3 * 2
                out.append(f'<rect x="{wx}" y="{top + 7}" width="{ww}" height="{wh}" '
                           f'fill="{_WINDOW_FILLS[(i + n * 2) % 4]}" opacity=".88"/>'
                           + _halo(k, wx + ww / 2, top + 7 + wh / 2, 24))
        x += w + 14
        i += 1
    return "".join(out)


# ほかの町の灯りの位置（x, y）。入り江の向こうの山すそと海辺
_FAR_LIGHTS = [
    (648, 402), (742, 396), (566, 404), (836, 388), (694, 372),
    (792, 364), (884, 400), (610, 380), (520, 398), (858, 352), (474, 404),
]


def _far_light(k: int, i: int, x: float, y: float) -> str:
    """遠くの町の灯り1つ。大きさは番号で変える。海辺のものは水面に映る。"""
    r = 1.8 + (i * 5) % 4 * 0.6
    mirror = _reflect(x, "a", r * 4, rows=2, strength=.45) if y >= 396 else ""
    return (f'{_halo(k, x, y, r * 6)}<circle cx="{x}" cy="{y}" r="{r:.1f}" fill="#F6B64E"/>'
            f'{mirror}')


_HOME = (436, 362, 2.3)   # 自分の町の提灯（x, y, 大きさ）


def scene_towns(n_towns: int) -> str:
    """第1章。自分の町の提灯が1つ。ほかの町の灯りは、入り江の向こうに小さく。"""
    far = "".join(
        f'<g class="far" style="--i:{i}">{_far_light(1, i, x, y)}</g>'
        for i, (x, y) in enumerate(_FAR_LIGHTS[:max(n_towns - 1, 0)]))
    hx, hy, hs = _HOME
    cap = hy - 16.5 * hs               # 提灯の上端
    px, arm = hx - 30, cap - 14        # 竿の位置と、腕木の高さ
    pole = (f'<path d="M{px} {_H}V{arm - 7:g}M{px - 6} {arm:g}H{hx + 6}M{hx} {arm:g}V{cap:g}" '
            f'stroke="#2E3D63" stroke-width="3" stroke-linecap="round" fill="none"/>')
    # 主役の光は面積を取る: 広いにじみを1枚敷き、その上に提灯のにじみを重ねる
    home = (_halo(1, hx, hy, 190) + _reflect(hx, "a", 46, rows=5, strength=.7)
            + _houses(1, lit=False) + pole + _lantern(1, hx, hy, hs, glow=52))
    body = (_defs(1, _lantern_defs(1), sky_from=.36) + _night(1) + far + home + _finish(1))
    # 高さを抑える画面では、空を切って家並みを残す
    return _svg(body, "scene-towns", align="xMidYMax")


_LAMPS_BURIED = [(470, 236, 1.5), (760, 300, 1.4), (352, 322, 1.3)]
_SHEET_FILLS = ("#152038", "#18243F", "#131D34")
_SHEET_SLICE = 6   # 紙1枚が現れるのに使う区間（%）。全体は35%


def _sheet_def(k: int, name: str, w: int, h: int, lines: int) -> str:
    """お知らせの紙1枚。見出しの太い線と、本文の細い線。地の色は使う側で決める。"""
    rows = "".join(
        f'<path d="M14 {40 + i * 15}h{(w - 28) * (0.55 + ((i * 37 + w) % 40) / 100):.0f}" '
        f'stroke="#26345A" stroke-width="2" stroke-linecap="round"/>' for i in range(lines))
    return (f'<g id="{name}-{k}"><rect width="{w}" height="{h}" rx="2" stroke="#2B3A5C" '
            f'stroke-width="1.2"/><path d="M14 20h{w // 2}" stroke="#3B4C74" stroke-width="4" '
            f'stroke-linecap="round"/>{rows}</g>')


def scene_notices() -> str:
    """第2章。積み重なったお知らせの紙に、催しの提灯が埋もれている。

    紙は37枚、提灯は3つ。お知らせの大半は催し以外で、催しはその中に埋もれている
    （CLAUDE.md「何をするツールか」）。絵は割合を正確に写したものではない。
    この章だけ色を足さない。紙は催しを埋もれさせる側で、華やかにすると意味が逆になる。
    """
    kinds = (("sa", 170, 226), ("sb", 205, 262))
    back, front = [], []
    for i in range(34):
        name, w, h = kinds[i % 2]
        x, y = -40 + (i * 173) % 1180, 40 + (i * 97) % 300
        rot = (i * 13) % 17 - 8
        # 提灯に重なる紙は奥へ回す（提灯が丸ごと隠れないように）
        near = any(x - 30 < lx < x + w + 30 and y - 30 < ly < y + h + 30
                   for lx, ly, _ in _LAMPS_BURIED)
        (back if i % 2 == 0 or near else front).append((name, x, y, w, h, rot, i))
    # 提灯の半分を隠す紙を、1枚ずつ手前に重ねる
    cover = [("sa", x - 4 + j * 3, y - 6 + j * 4, 170, 226, (-6, 5, -3)[j], j)
             for j, (x, y, _) in enumerate(_LAMPS_BURIED)]
    order = back + cover + front
    step = (35 - _SHEET_SLICE) / (len(order) - 1)

    def draw(n: int) -> str:
        name, x, y, w, h, rot, tone = order[n]
        return (f'<use class="sheet" style="--i:{n}" href="#{name}-2" '
                f'fill="{_SHEET_FILLS[tone % 3]}" '
                f'transform="translate({x} {y}) rotate({rot} {w // 2} {h // 2})"/>')

    lamps = "".join(_lantern(2, x, y, s, "buried") for x, y, s in _LAMPS_BURIED)
    body = (_defs(2, _lantern_defs(2) + _sheet_def(2, "sa", 170, 226, 9)
                  + _sheet_def(2, "sb", 205, 262, 11), teal=False)
            + f'<rect width="{_W}" height="{_H}" fill="url(#sky-2)"/>'
            + "".join(draw(n) for n in range(len(back)))
            + lamps
            + "".join(draw(n) for n in range(len(back), len(order)))
            + f'<rect y="{_H - 150}" width="{_W}" height="150" fill="url(#foot-2)"/>'
            + f'<rect width="{_W}" height="{_H}" fill="url(#edge-2)"/>')
    return _svg(body, "scene-notices", f"--step:{step:.3f}%")


_WINDOW_SLICE = 5.25   # 窓1つが灯るのに使う区間。全体35%のおよそ15%ぶん


def scene_windows(n_sources: int) -> str:
    """第3章。夜明け前の家並みに、情報源の数だけ窓があり、灯りが入っている。"""
    front_n = (n_sources + 1) // 2
    pitch = min(90.0, (_SAFE_R - _SAFE_L) / max(front_n, 1))
    front_x0 = _W / 2 - front_n * pitch / 2     # 窓のある家は中央に寄せる
    rows = (   # (段, 窓のある軒数, 左端, 屋根の下端, 屋根の高さ, 窓の位置, 窓の幅, 窓の高さ)
        # 奥の段は半軒ずらす（手前の屋根の谷間から、奥の窓が見えるように）
        (0, n_sources - front_n, front_x0 + pitch / 2, 352, 24, 10, 22, 28),
        (1, front_n, front_x0, 410, 26, 16, 26, 36),
    )
    houses: dict[int, list[str]] = {0: [], 1: []}
    windows = []
    for row, count, x0, top0, rise0, wdy, ww, wh in rows:
        for j in range(-8, count + 9):           # 窓の無い家で、絵の両端まで埋める
            x = x0 + j * pitch
            if x + pitch < -20 or x > _W + 20:
                continue
            top = top0 + ((j * 5) % 3 - 1) * 5   # 軒の高さを少しずつ変える
            rise = rise0 + (j * 7) % 3 * 3
            houses[row].append(_house(x, top, pitch + 2, rise))
            if 0 <= j < count:
                windows.append((x + (pitch + 2) / 2, top + wdy, ww, wh, row))

    def draw(i: int, cx: float, y: float, ww: float, wh: float) -> str:
        # 窓ごとに大きさと色味を少し変える（数と並ぶ順は変えない）
        k = 0.88 + (i * 5) % 4 * 0.09
        ww, wh = round(ww * k), round(wh * k)
        x, cy = cx - ww / 2, y + wh / 2
        fill = _WINDOW_FILLS[(i * 3 + i // 4) % 4]
        return (f'<g class="window" style="--i:{i}">'
                f'<circle class="glow" cx="{cx:g}" cy="{cy:g}" r="{round(40 * k)}" '
                f'fill="url(#halo-a-3)"/>'
                f'<rect class="glow" x="{x:g}" y="{y:g}" width="{ww}" height="{wh}" fill="{fill}"/>'
                f'<path class="pane" d="M{cx:g} {y:g}v{wh}M{x:g} {cy:g}h{ww}"/>'
                f'<rect class="frame" x="{x:g}" y="{y:g}" width="{ww}" height="{wh}"/></g>')

    # 灯る順は左から（奥と手前を行き来する）
    ordered = list(enumerate(sorted(windows)))
    layer = {row: "".join(draw(i, *wd[:4]) for i, wd in ordered if wd[4] == row)
             for row in (0, 1)}
    body = (_defs(3, haze=.7) + _night(3, haze_y=356)
            + "".join(houses[0]) + layer[0] + "".join(houses[1]) + layer[1] + _finish(3))
    # 窓が順に灯る間隔。全体の区間（35%）を窓の数で割り振る（動きの CSS が使う）
    step = (35 - _WINDOW_SLICE) / max(n_sources - 1, 1)
    return _svg(body, "scene-windows", f"--step:{step:.3f}%")


_GRID_X0, _GRID_DX = 336, 88     # 日曜の列の x と、列の間隔
_GRID_Y0, _GRID_DY = 26, 62      # 1段目の綱の y と、段の間隔
_LAN = 1.25                      # 暦の提灯の大きさ（ここから少しずつ変える）
_CALENDAR_TONES = "aaaarrrwww"   # 橙4・朱3・黄白3 の割合で混ぜる


def _rope(xa: float, xb: float, y: float, sag: float) -> str:
    return (f'<path d="M{xa:g} {y:g}Q{(xa + xb) / 2:g} {y + 2 * sag:g} {xb:g} {y:g}" '
            f'stroke="{_ROPE}" stroke-width="1.4" fill="none"/>')


def scene_calendar(missing: str, n_towns: int) -> str:
    """第4〜6章。綱に下げた提灯が、暦の形に並ぶ。このページでいちばん華やかな絵。

    missing: "absent"（第4章。描かない）/ "unlit"（第5章。灯っていない提灯）/
             "lit"（第6章。灯りが入る）

    提灯の色（橙・朱・黄白）と大きさは混ぜるが、位置と数は暦のまま（7列・30個）。
    入り江の向こうには、第1章では暗かった町の灯りが、今度は明るくともっている
    （数は第1章と同じ。市町の数から自分の町を引いたもの）。
    """
    k = {"absent": 4, "unlit": 5, "lit": 6}[missing]
    weeks = calendar.Calendar(firstweekday=6).monthdayscalendar(_GRID_YEAR, _GRID_MONTH)
    ropes, lamps, hole, i = [], [], "", 0
    column_tone: dict[int, str] = {}
    for r, week in enumerate(weeks):
        y = _GRID_Y0 + r * _GRID_DY
        cols = [c for c, day in enumerate(week) if day and day != _MISSING_DAY]
        if cols:
            xa = _GRID_X0 + cols[0] * _GRID_DX - 70
            xb = _GRID_X0 + cols[-1] * _GRID_DX + 70
            sag = 16 if len(cols) > 2 else 6
            ropes.append(_rope(xa, xb, y, sag))
        for c, day in enumerate(week):
            if not day:
                continue
            x = _GRID_X0 + c * _GRID_DX
            if day == _MISSING_DAY:
                # 載らなかった日。短い綱ごと、第4章では描かない
                hy = y + 4 + 20 * _LAN
                off = (f'<g class="unlit">{_rope(x - 60, x + 70, y, 5)}'
                       f'{_use(f"off-{k}", x, hy, _LAN)}</g>')
                if missing == "unlit":
                    hole = off
                elif missing == "lit":
                    # 灯りが入る1つは、にじみを広く取る（差し色の橙。行動のボタンと同じ色）。
                    # 絵の上端で切れないよう、中心を少し下げる（残りは上端のぼかしが受ける）
                    hole = (off + _halo(k, x, hy + 18, 110, "halo")
                            + f'<g class="last">{_use(f"lan-a-{k}", x, hy, _LAN)}</g>')
                continue
            tone = _CALENDAR_TONES[(i * 7 + r * 3) % 10]
            size = _LAN * (0.92 + (i * 5) % 4 * 0.06)
            t = (x - xa) / (xb - xa)
            ly = y + 4 * sag * t * (1 - t) + 20 * size      # 綱のたるみに沿って下がる
            # 上の2段は過ぎた週。暗くはなるが、消えない
            cls = "lit gone" if r in (1, 2) else "lit"
            # 集まる前に散らばっている位置（綱からのずれ）。乱数ではなく番号から決める
            dx, dy = (i * 37) % 81 - 40, (i * 53 + 17) % 61 - 30
            lamps.append(_lantern(k, x, ly, size, cls, f"--dx:{dx}px;--dy:{dy}px", tone))
            column_tone[c] = tone          # 水面に映すのは、その列のいちばん下の色
            i += 1
    mirrors = "".join(_reflect(_GRID_X0 + c * _GRID_DX, tone, 30, rows=4, strength=.55)
                      for c, tone in sorted(column_tone.items()))
    far = "".join(_far_light(k, n, x, y)
                  for n, (x, y) in enumerate(_FAR_LIGHTS[:max(n_towns - 1, 0)]))
    top = (f'<linearGradient id="top-{k}" x1="0" y1="0" x2="0" y2="1">'
           f'<stop offset="0" stop-color="{NIGHT}"/>'
           f'<stop offset="1" stop-color="{NIGHT}" stop-opacity="0"/></linearGradient>')
    body = (_defs(k, _lantern_defs(k, "arw") + top, tones="arw", haze=.22)
            + _night(k, clear=(280, 60, 920, 260), big_stars=True)
            + far + mirrors + _houses(k, lit=True)
            + "".join(ropes) + "".join(lamps) + hole
            + f'<rect width="{_W}" height="22" fill="url(#top-{k})"/>' + _finish(k))
    return _svg(body, f"scene-calendar is-{missing}")


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
        "scene4": scene_calendar("absent", n_towns),
        "scene5": scene_calendar("unlit", n_towns),
        "scene6": scene_calendar("lit", n_towns),
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

  /* 余白は文字の側に持たせる。絵は左右の余白を越えて、画面の幅いっぱいに置く */
  .ch{padding:clamp(5rem,15vh,9rem) 0}
  .ch > *{max-width:calc(var(--col) + 2 * var(--gutter));margin-left:auto;margin-right:auto;
    padding-left:var(--gutter);padding-right:var(--gutter)}
  /* 絵は 12:5。幅の狭い画面では高さを保ち、左右を切って中央を見せる。
     切りすぎると暦の両端の提灯が欠けるので、高さは幅の83%まで */
  .ch > .scene{display:block;width:100%;max-width:90rem;padding:0;
    height:clamp(min(300px,83vw),41.67vw,600px)}
  /* 第1章もほかの章と同じ高さ。ただし背の低い画面では、見出しが最初の画面に
     入るところまで縮める（空を切り、家並みと提灯は残す） */
  .ch1 > .scene{height:min(clamp(min(300px,83vw),41.67vw,600px),max(300px,100svh - 19rem))}
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
  .gone{opacity:.5}
  .far{opacity:.6}
  .buried{opacity:.5}
  .frame{fill:none;stroke:var(--unlit);stroke-width:1.5}
  .pane{stroke:#0E1628;stroke-width:2;fill:none}

  .titles{list-style:none;padding-top:0;padding-bottom:0;margin-top:0;margin-bottom:1.8em}
  .titles li{display:flex;gap:1em;align-items:baseline;
    border-bottom:1px solid var(--rule);line-height:1.7}
  .titles li:first-child{border-top:1px solid var(--rule)}
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

    /* 第1章だけは時間で進む。ほかの町の灯りが、入り江の向こうに1つずつ現れる */
    .scene-towns .far{animation:appear 1200ms cubic-bezier(.2,.6,.3,1) both;
      animation-delay:calc(800ms + var(--i) * 600ms)}

    /* 第2〜6章は読者のスクロールに連動する。対応していないブラウザでは静止表示のまま */
    @supports (animation-timeline:view()){
      .scene{view-timeline-name:--scene}

      /* 第2章: お知らせの紙が奥から1枚ずつ重なる。提灯は暗いまま埋もれていく */
      .scene-notices .sheet{animation:appear linear both;animation-timeline:--scene;
        animation-range:cover calc(15% + var(--i) * var(--step))
                        cover calc(21% + var(--i) * var(--step))}

      /* 第3章: 窓に左から順に灯りが入る */
      .scene-windows .glow{animation:appear linear both;animation-timeline:--scene;
        animation-range:cover calc(15% + var(--i) * var(--step))
                        cover calc(20.25% + var(--i) * var(--step))}

      /* 第4章: 散らばっていた提灯が、綱に下がる位置へ集まる */
      .is-absent .lit{animation:gather cubic-bezier(.35,.1,.25,1) both;
        animation-timeline:--scene;animation-range:cover 0% cover 50%}
      .is-absent .gone{--from:.25}

      /* 第5章: 灯っていない提灯が1つ、ゆっくり見えてくる。ほかは何も動かさない */
      .is-unlit .unlit{animation:appear linear both;animation-timeline:--scene;
        animation-range:cover 30% cover 58%}

      /* 第6章: 行動のボタンが画面に入ると、灯っていなかった提灯に灯りが入る */
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
