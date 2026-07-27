"""出力レンダラー: JSON / ICS(カレンダー取込) / HTMLダッシュボード。"""
from __future__ import annotations

import html as _html
import json
from datetime import date, datetime, timedelta

from .filters import TIER_LABEL
from .models import Event


def dedup(events: list[Event]) -> list[Event]:
    seen, out = set(), []
    for ev in events:
        if ev.uid in seen:
            continue
        seen.add(ev.uid)
        out.append(ev)
    return out


# ---- JSON ---------------------------------------------------------------
def to_json(events: list[Event]) -> str:
    return json.dumps([e.to_dict() for e in events], ensure_ascii=False, indent=2)


# ---- ICS ----------------------------------------------------------------
def _ics_escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;")
                .replace(",", "\\,").replace("\n", "\\n"))


def to_ics(events: list[Event], cal_name: str = "山陰の蚤の市") -> str:
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//sanin-nomi-collector//JP",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_ics_escape(cal_name)}",
    ]
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    for ev in events:
        if not ev.date_start:
            continue
        end = (ev.date_end or ev.date_start) + timedelta(days=1)  # 終日は翌日を指定
        loc = " ".join(filter(None, [ev.prefecture, ev.city, ev.venue])) or (ev.prefecture or "")
        lines += [
            "BEGIN:VEVENT",
            f"UID:{ev.uid}@sanin-nomi",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{ev.date_start.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{end.strftime('%Y%m%d')}",
            f"SUMMARY:{_ics_escape(ev.title)}",
            f"LOCATION:{_ics_escape(loc)}",
            f"DESCRIPTION:{_ics_escape(TIER_LABEL.get(ev.distance_tier or '', ''))} / {_ics_escape(ev.url)}",
            f"URL:{ev.url}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


# ---- HTML ダッシュボード -------------------------------------------------
_WD = ["月", "火", "水", "木", "金", "土", "日"]
_TIER_ORDER = ["daytrip_easy", "daytrip", "daytrip_far", "excursion", "far"]


def _fmt_date(ev: Event) -> str:
    s = ev.date_start
    if not s:
        return ev.raw_date_text or "日程未定"
    txt = f"{s.month}/{s.day}<span class='wd'>{_WD[s.weekday()]}</span>"
    if ev.date_end and ev.date_end != s:
        e = ev.date_end
        txt += f" – {e.month}/{e.day}<span class='wd'>{_WD[e.weekday()]}</span>"
    return txt


def _tag_card(ev: Event) -> str:
    tier = ev.distance_tier or "far"
    tier_label = TIER_LABEL.get(tier, "")
    pref = _html.escape(ev.prefecture or "")
    title = _html.escape(ev.title)
    return f"""
    <a class="tag" href="{_html.escape(ev.url)}" data-tier="{tier}" target="_blank" rel="noopener">
      <span class="tag-hole"></span>
      <span class="seal">{pref}</span>
      <span class="date">{_fmt_date(ev)}</span>
      <span class="name">{title}</span>
      <span class="tier">{tier_label}</span>
    </a>"""


def to_html(events: list[Event], home_base: str = "浜田") -> str:
    generated = datetime.now().strftime("%Y.%m.%d %H:%M")
    events = sorted(
        events,
        key=lambda e: (e.date_start or date.max,
                       _TIER_ORDER.index(e.distance_tier) if e.distance_tier in _TIER_ORDER else 99),
    )
    # 月ごとに束ねる
    groups: dict[str, list[Event]] = {}
    for ev in events:
        key = f"{ev.date_start.year}年{ev.date_start.month}月" if ev.date_start else "日程未定"
        groups.setdefault(key, []).append(ev)

    sections = []
    for month, evs in groups.items():
        cards = "\n".join(_tag_card(e) for e in evs)
        sections.append(
            f'<section class="month"><h2 class="month-head">'
            f'<span class="ma">{_html.escape(month)}</span>'
            f'<span class="count">{len(evs)}件</span></h2>'
            f'<div class="tags">{cards}</div></section>'
        )
    body = "\n".join(sections) if sections else \
        '<p class="empty">対象期間の山陰イベントは見つかりませんでした。' \
        '次回更新でまた拾いにいきます。</p>'

    return _TEMPLATE.format(
        home_base=_html.escape(home_base),
        generated=generated,
        total=len(events),
        body=body,
    )


_TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>山陰の蚤の市 · 荷札台帳</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Zen+Old+Mincho:wght@500;700;900&family=Zen+Kaku+Gothic+New:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  :root {{
    --washi: #e9e5da;      /* 和紙のような冷たいベージュ */
    --washi-2: #f3f0e8;
    --ink: #22201b;        /* 墨に少し緑を落とした黒 */
    --ink-soft: #5c574c;
    --sekishu: #8a3a2b;    /* 石州瓦のオックスブラッド */
    --ai: #33595c;         /* 藍鉄／日本海の翳り */
    --brass: #9c7c3a;      /* 真鍮の光 */
    --line: #cdc7b8;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background:
      radial-gradient(circle at 12% -5%, rgba(138,58,43,.05), transparent 40%),
      var(--washi);
    color: var(--ink);
    font-family: "Zen Kaku Gothic New", system-ui, sans-serif;
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
  }}
  .wrap {{ max-width: 940px; margin: 0 auto; padding: clamp(1.5rem, 4vw, 3.5rem) 1.25rem 5rem; }}

  header.masthead {{
    border-bottom: 2px solid var(--ink);
    padding-bottom: 1rem; margin-bottom: 2.5rem;
    display: flex; align-items: flex-end; justify-content: space-between; gap: 1rem;
    flex-wrap: wrap;
  }}
  .title-block h1 {{
    font-family: "Zen Old Mincho", serif; font-weight: 900;
    font-size: clamp(2rem, 6vw, 3.4rem); margin: 0; letter-spacing: .04em;
  }}
  .title-block h1 .of {{ color: var(--sekishu); }}
  .title-block .sub {{
    font-family: "Zen Old Mincho", serif; color: var(--ink-soft);
    letter-spacing: .28em; font-size: .78rem; margin-top: .35rem;
    text-transform: none;
  }}
  .meta {{ text-align: right; font-size: .72rem; color: var(--ink-soft); letter-spacing: .04em; }}
  .meta .big {{
    display:block; font-family:"Zen Old Mincho",serif; font-size:2.2rem;
    color: var(--ai); line-height:1; font-weight:700;
  }}

  .legend {{ display:flex; gap:.5rem 1rem; flex-wrap:wrap; margin-bottom:2.5rem; font-size:.72rem; color:var(--ink-soft); }}
  .legend b {{ color: var(--ink); font-weight:700; }}

  .month-head {{
    font-family: "Zen Old Mincho", serif; font-weight:700;
    display:flex; align-items:baseline; gap:.9rem;
    font-size: 1.15rem; margin: 2.4rem 0 1.1rem;
  }}
  .month-head .ma {{
    border-left: 4px solid var(--sekishu); padding-left:.6rem; letter-spacing:.06em;
  }}
  .month-head .count {{ font-family:"Zen Kaku Gothic New"; font-size:.72rem; color:var(--ink-soft); }}

  .tags {{ display:grid; grid-template-columns: repeat(auto-fill, minmax(240px,1fr)); gap: .9rem; }}

  /* 荷札（にふだ）カード = このページの署名要素 */
  .tag {{
    position: relative; display:block; text-decoration:none; color:inherit;
    background: linear-gradient(180deg, var(--washi-2), #eee9de);
    border: 1px solid var(--line);
    border-radius: 3px 14px 14px 3px;
    padding: 1.1rem 1.1rem 1rem 1.6rem;
    box-shadow: 0 1px 0 #fff inset, 0 2px 6px rgba(34,32,27,.06);
    transition: transform .16s ease, box-shadow .16s ease;
  }}
  .tag::before {{  /* 綴じ紐の走る左端 */
    content:""; position:absolute; left:.55rem; top:.6rem; bottom:.6rem; width:2px;
    background: repeating-linear-gradient(180deg, var(--line) 0 4px, transparent 4px 8px);
  }}
  .tag-hole {{ position:absolute; top:.7rem; left:.7rem; width:9px; height:9px; border-radius:50%;
    background: var(--washi); border:1px solid var(--ink-soft); box-shadow:0 0 0 2px var(--washi-2); }}
  .tag:hover {{ transform: translateY(-3px) rotate(-.4deg); box-shadow: 0 8px 18px rgba(34,32,27,.14); }}

  .seal {{
    position:absolute; top:.7rem; right:.7rem;
    font-family:"Zen Old Mincho",serif; font-size:.62rem; font-weight:700;
    color: var(--sekishu); border:1.5px solid var(--sekishu);
    border-radius:50%; width:2.6rem; height:2.6rem;
    display:flex; align-items:center; justify-content:center; text-align:center;
    line-height:1.05; transform: rotate(-6deg); opacity:.9;
  }}
  .date {{
    display:block; font-family:"Zen Old Mincho",serif; font-weight:700;
    font-size:1.5rem; color:var(--ink); letter-spacing:.02em; margin-bottom:.15rem;
  }}
  .date .wd {{ font-size:.7rem; color:var(--ink-soft); margin-left:.15rem; vertical-align:.15em; }}
  .name {{ display:block; font-weight:500; font-size:1rem; margin:.15rem 0 .7rem; padding-right:2.2rem; }}
  .tier {{
    display:inline-block; font-size:.68rem; letter-spacing:.06em;
    color: var(--ai); border:1px solid var(--ai); border-radius:999px; padding:.1rem .55rem;
  }}
  .tag[data-tier="daytrip_easy"] .tier {{ color:#2f6b3c; border-color:#2f6b3c; }}
  .tag[data-tier="excursion"] .tier,
  .tag[data-tier="far"] .tier {{ color: var(--brass); border-color: var(--brass); }}

  .empty {{ font-family:"Zen Old Mincho",serif; color:var(--ink-soft); padding:3rem 0; }}
  footer {{ margin-top:3.5rem; padding-top:1rem; border-top:1px solid var(--line);
    font-size:.7rem; color:var(--ink-soft); letter-spacing:.03em; }}
  a.tag:focus-visible {{ outline:2px solid var(--ai); outline-offset:2px; }}
  @media (prefers-reduced-motion: reduce) {{ .tag {{ transition:none; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header class="masthead">
    <div class="title-block">
      <h1>山陰 蚤<span class="of">乃</span>市 台帳</h1>
      <div class="sub">{home_base} を起点にした 蚤の市 荷札帳</div>
    </div>
    <div class="meta">
      <span class="big">{total}</span>
      件を採取<br>{generated} 更新
    </div>
  </header>

  <div class="legend">
    <span><b>荷札の色帯</b>＝浜田からの距離感：</span>
    <span><b style="color:#2f6b3c">日帰り◎</b> 石見・近隣</span>
    <span><b style="color:#33595c">日帰り○</b> 島根内</span>
    <span><b style="color:#9c7c3a">小遠征</b> 鳥取ほか</span>
  </div>

  {body}

  <footer>
    出典: GOOD ANTIQUES 中国・四国編 ほか ／ 日程・会場は各詳細ページで必ずご確認ください。<br>
    sanin-nomi-collector — 自動収集。荷札をタップすると主催の詳細ページへ飛びます。
  </footer>
</div>
</body>
</html>"""
