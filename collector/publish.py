"""公開サイトのレンダラー（種別対応版）。

種別ごとに時間軸が違うので、並べ方も表示も分ける。

  催し  開催日の昇順   「8月9日(日)」        行く
  募集  締切の昇順      「締切まであと3日」    申し込む
  制度  並べていない    「随時」               使う

制度はいま件数が少なく、意味のある並び順がまだ無い（`_sort_key` は
無条件に `date.max` を返し、取り込んだ順のまま並ぶ）。カテゴリ順に
していた時期もあったが、実装と食い違っていたので2026-08-08に
ドキュメント側を実態に合わせた。

締切が近いものがあるときだけ、募集を最上段に繰り上げる。
ふだんは催しが主役、締切が迫っているときだけ順序が入れ替わる。
"""
from __future__ import annotations

import html as _html
from collections import Counter, defaultdict
from datetime import date, datetime

from .models import Event, now_jst, today_jst

_WD = ["月", "火", "水", "木", "金", "土", "日"]
URGENT_DAYS = 14          # これ以内の締切があれば募集を最上段へ
ALERT_DAYS = 7            # これ以内は赤く出す

STATUS_BADGE = {"中止": "中止", "終了": "終了", "最後の開催": "最後の開催"}

# 市町別の絞り込み（#gotsu のようにURLで共有できる）で使う短い記号。
# config.yaml の情報源キー（hamada_city / gotsu_city / kawamoto_kanko …）の
# 頭に揃えてある。並び順がそのままナビの表示順になる。
# 石見9市町が出そろった時点のもの（CLAUDE.md「収集」の並びに吉賀町を足した形）。
CITY_SLUG = {
    "浜田市": "hamada", "江津市": "gotsu", "益田市": "masuda",
    "大田市": "oda", "津和野町": "tsuwano", "邑南町": "ohnan",
    "川本町": "kawamoto", "美郷町": "misato", "吉賀町": "yoshika",
}


def _days_left(d: date, today: date) -> int:
    return (d - today).days


def is_past(ev: Event, today: date) -> bool:
    """終わったものか。

    日付が分からないものは「終わった」とは判定しない（消してはいけない）。
    期間があるものは終わりの日で見る（年間通しの定期公演などを消さないため）。
    """
    if ev.kind == "制度":
        return False
    if ev.kind == "募集":
        # 締切が主役だが、締切が取れなくても開催日は取れていることがある
        # （表示側と同じ「持っている情報で判断する」方針。2026-08-06、
        # 締切不明の募集が開催日を過ぎても「これから」に居座っていた）
        end = ev.deadline or ev.date_start
        return end is not None and end < today
    end = ev.date_end or ev.date_start
    return end is not None and end < today


def _when_html(ev: Event, today: date) -> str:
    if ev.kind == "制度":
        return "<span class='anytime'>随時</span>"

    if ev.kind == "募集":
        if not ev.deadline:
            if not ev.date_start:
                return "<span class='tbd'>締切は詳細ページで</span>"
            # 締切は取れなくても開催日は取れている（例: パブリックビューイング）。
            # 「持っている情報は出す」— date.max に落として最後尾に沈めない
            s = ev.date_start
            return (f"<span class='tbd'>開催 {s.month}/{s.day}"
                    f"<span class='wd'>{_WD[s.weekday()]}</span>"
                    f"・締切は詳細ページで</span>")
        n = _days_left(ev.deadline, today)
        d = ev.deadline
        label = f"締切 {d.month}/{d.day}"
        if n < 0:
            return f"<span class='over'>{label}・終了</span>"
        if n == 0:
            return f"<span class='alert'>{label}・<b>本日まで</b></span>"
        cls = "alert" if n <= ALERT_DAYS else "soon"
        return f"<span class='{cls}'>{label}・<b>あと{n}日</b></span>"

    if ev.date_start:
        s = ev.date_start
        txt = f"{s.month}月{s.day}日<span class='wd'>{_WD[s.weekday()]}</span>"
        if ev.date_end and ev.date_end != s:
            txt += f"〜{ev.date_end.month}月{ev.date_end.day}日"
        # 飛び石で複数回あるものは、次回の日付に回数を添える。
        # 期間として「9月12日〜翌3月17日」とは書かない（6か月続くと誤解される）
        if ev.session_count and ev.session_count > 1:
            txt += f"<span class='sessions'>（全{ev.session_count}回）</span>"
        # 会場違いなどで別の日程もあるものは「ほか」と添える。
        # **「全N回」とは別物。** 救命講習は同じ催しが6回繰り返されるが、
        # 天領さんは1つの祭りが大田8/1・久手8/4・大森8/30 と会場を変えて開かれる。
        # 「全3回」と書くと、同じものが3回あると誤解される
        elif ev.other_dates:
            txt += "<span class='sessions'>ほか</span>"
        return txt
    return "<span class='tbd'>日程は詳細ページで</span>"


def _sort_key(ev: Event):
    if ev.kind == "募集":
        # 締切が近い順。締切が無くても開催日は取れていることがあるので、
        # date.max に落とすのは「日付を何も持っていない」ときだけにする
        return ev.deadline or ev.date_start or date.max
    if ev.kind == "催し":
        return ev.date_start or date.max        # 開催日が近い順
    return date.max


def _deadline_note(ev: Event, today: date) -> str:
    """催しにも申込締切、募集にも開催日はある。主役の日付とは別に小さく添える。

    （締切を拾えているのに催しだと画面に出ない、という漏れがあった）
    """
    if ev.kind == "催し" and ev.deadline:
        # 期間の終わりと締切が同じ日なら、開催日の行にすでに「〜12月15日」と
        # 出ている。二重に見せない（スタンプラリーは実施期間の終わり＝応募締切）
        if ev.date_end and ev.deadline == ev.date_end:
            return ""
        n = _days_left(ev.deadline, today)
        if n < 0:
            return "<div class='dl-note over'>申込は終了しています</div>"
        d = ev.deadline
        cls = "alert" if n <= ALERT_DAYS else ""
        left = "本日まで" if n == 0 else f"あと{n}日"
        return f"<div class='dl-note {cls}'>申込締切 {d.month}/{d.day}・{left}</div>"
    if ev.kind == "募集" and ev.deadline and ev.date_start:
        # 締切が主役の行に出ているので、開催日は従として添える（催しの逆）
        s = ev.date_start
        return (f"<div class='dl-note'>開催 {s.month}/{s.day}"
                f"<span class='wd'>{_WD[s.weekday()]}</span></div>")
    return ""


def _card(ev: Event, today: date) -> str:
    badge = STATUS_BADGE.get(ev.status, "")
    badge_html = f"<span class='badge'>{badge}</span>" if badge else ""
    # かつて「締切あり」タグを会期末と同じ日のときだけ隠していたが、タグ自体を
    # 廃止したので抑制も要らなくなった（理由は classify.py）。
    # 隠していたのは誤爆の一部だけで、`deadline` が取れなかった側は素通りしていた
    tags = "".join(f"<span class='tg'>{_html.escape(t)}</span>" for t in (ev.tags or []))
    cls = {"中止": "cancelled", "終了": "ended", "最後の開催": "last"}.get(ev.status, "")
    fetched = ev.published_at.strftime("%Y/%m/%d") if ev.published_at else "—"
    # カテゴリが空のときは中黒も出さない。「大田市 ・掲載 2026/07/22」と
    # 先頭に「・」が浮いていた（カテゴリ未判定は公開59件中8件ある）
    cat = f"{_html.escape(ev.category)}・" if ev.category else ""
    return f"""
    <article class="card {cls}" data-city="{_html.escape(ev.city or '')}">
      <div class="when" title="{_html.escape(ev.date_source or ev.deadline_source or '')}">{_when_html(ev, today)}{badge_html}</div>
      <h3><a href="{_html.escape(ev.url)}" target="_blank" rel="noopener">{_html.escape(ev.title)}</a></h3>
      {_deadline_note(ev, today)}
      <div class="tags">{tags}</div>
      <div class="foot"><span class="muni">{_html.escape(ev.city or '')}</span>
        <span class="src">{cat}掲載 {fetched}</span></div>
    </article>"""


def _filter_nav(upcoming: list[Event]) -> tuple[str, str]:
    """市町別の絞り込み。JSは使わず `:target` + CSS だけで動かす。

    `#gotsu` のようにURLで共有できる（告知のときに市町ごとのリンクを配れる）。
    既定（ハッシュ無し）は絞り込み無しで、全市町を表示する。

    件数はいまの「これから」（催し＋募集＋制度）だけで数える。0件の市町は
    畳んだ節にしか無いことがあるので「載っていません」と決めつけず、
    メッセージは出さない（畳んだ節を開けば見える）。
    """
    counts = Counter(e.city for e in upcoming if e.city)
    links = [f"<a href=\"#all\" class=\"all\">ぜんぶ<span class='c'>"
             f"{len(upcoming)}</span></a>"]
    rules = []
    empties = []
    for city, slug in CITY_SLUG.items():
        n = counts.get(city, 0)
        esc = _html.escape(city)
        links.append(f"<a href=\"#{slug}\">{esc}<span class='c'>{n}</span></a>")
        rules.append(
            f"#{slug}:target ~ * .card:not([data-city=\"{esc}\"]){{display:none}}"
            f"#{slug}:target ~ .block:not(:has(.card[data-city=\"{esc}\"])),"
            f"#{slug}:target ~ details.past:not(:has(.card[data-city=\"{esc}\"]))"
            "{display:none}"
        )
        if n == 0:
            rules.append(f"#{slug}:target ~ .empty-city#empty-{slug}{{display:block}}")
            empties.append(f"<p class='empty-city' id='empty-{slug}'>"
                           f"いま {esc} に載っている催し・募集はありません。"
                           f"下の畳んだ節（終わった分）には残っているかもしれません。</p>")
    anchors = "".join(f"<span id=\"{s}\" class=\"anchor\"></span>"
                      for s in ["all"] + list(CITY_SLUG.values()))
    nav = (f"<nav class='pick' aria-label='市町で絞り込む'>{''.join(links)}</nav>"
           f"{anchors}{''.join(empties)}")
    return nav, "".join(rules)


def _block(title: str, lead: str, evs: list[Event], today: date, kind_cls: str) -> str:
    if not evs:
        return ""
    cards = "".join(_card(e, today) for e in evs)
    return (f"<section class='block {kind_cls}'>"
            f"<h2>{_html.escape(title)}<span class='n'>{len(evs)}</span></h2>"
            f"<p class='lead2'>{_html.escape(lead)}</p>"
            f"<div class='grid'>{cards}</div></section>")


def to_public_site(events: list[Event], region: str = "石見",
                   today: date | None = None, site: dict | None = None) -> str:
    today = today or today_jst()
    generated = now_jst().strftime("%Y年%m月%d日 %H:%M")

    by_kind: dict[str, list[Event]] = defaultdict(list)
    for ev in events:
        by_kind[ev.kind or "催し"].append(ev)
    for k in by_kind:
        by_kind[k].sort(key=_sort_key)

    moyoshi, boshu, seido = by_kind["催し"], by_kind["募集"], by_kind["制度"]

    # 終わったものは「これから」から外す。ただし消さずに下へ畳んで残す
    # （「今年はやらない」も記録として残す方針のため）
    past = [e for e in moyoshi + boshu if is_past(e, today)]
    moyoshi = [e for e in moyoshi if not is_past(e, today)]
    boshu = [e for e in boshu if not is_past(e, today)]
    for e in past:
        if e.status == "開催予定":
            e.status = "終了"
    past.sort(key=lambda e: (e.date_start or e.deadline or date.min), reverse=True)

    # 締切が迫っているものがあるときだけ、募集を先頭に繰り上げる
    urgent = any(e.deadline and 0 <= _days_left(e.deadline, today) <= URGENT_DAYS
                 for e in boshu)

    b_m = _block("これからの催し", "行ってみるもの。開催日の近い順。",
                 moyoshi, today, "k-moyoshi")
    b_b = _block("募集・締切のあるもの", "申し込むもの。締切の近い順。",
                 boshu, today, "k-boshu")
    b_s = _block("いつでも使えるもの", "頼めば使える制度。日程はありません。",
                 seido, today, "k-seido")

    b_p = ""
    if past:
        cards = "".join(_card(e, today) for e in past)
        b_p = (f"<details class='past'><summary>終わった催し・締切"
               f"<span class='n'>{len(past)}</span></summary>"
               f"<p class='lead2'>記録として残しています。</p>"
               f"<div class='grid'>{cards}</div></details>")

    body = (b_b + b_m if urgent else b_m + b_b) + b_s + b_p
    if not body:
        body = "<p class='empty'>いまのところ掲載できるものがありません。</p>"

    filter_nav, filter_css = _filter_nav(moyoshi + boshu + seido)

    site = site or {}
    title = site.get("title") or f"{region}の催し"
    reading = site.get("reading") or ""
    accent = site.get("title_accent") or ""

    # 見出しの組み立て。読みにくい名前なのでふりがなを振れるようにする
    shown = _html.escape(title)
    if accent and accent in title:
        shown = shown.replace(_html.escape(accent),
                              f"<span class='r'>{_html.escape(accent)}</span>", 1)
    if reading:
        h1_html = (f"<ruby>{shown}<rp>（</rp>"
                   f"<rt>{_html.escape(reading)}</rt><rp>）</rp></ruby>")
    else:
        h1_html = shown
    tagline = site.get("tagline") or "市町のお知らせから、催し・募集・使える制度を拾って並べています。"
    url = site.get("url") or ""
    contact = site.get("contact") or ""
    operator = site.get("operator") or ""

    # 連絡先は公開物の必須要素。空なら運用者に見える形で警告を出す
    if contact:
        c = contact.strip()
        if c.startswith(("http://", "https://")):
            link = f'<a href="{_html.escape(c)}" target="_blank" rel="noopener">お問い合わせフォーム</a>'
        elif "@" in c and " " not in c:
            link = f'<a href="mailto:{_html.escape(c)}">{_html.escape(c)}</a>'
        else:
            link = f"<strong>{_html.escape(c)}</strong>"
        contact_html = ("掲載の追加・修正、掲載を望まれない場合は "
                        f"{link} からご連絡ください。")
    else:
        contact_html = ("<span style='color:#a8321f'>【要設定】config.yaml の "
                        "site.contact に連絡先を入れてください。"
                        "連絡先のない公開はおすすめしません。</span>")
    operator_html = f"運営: {_html.escape(operator)}<br>" if operator else ""
    canonical = f'<link rel="canonical" href="{_html.escape(url)}">' if url else ""
    og_url = f'<meta property="og:url" content="{_html.escape(url)}">' if url else ""

    return _TPL.format(region=_html.escape(region), generated=generated,
                       total=len(moyoshi) + len(boshu) + len(seido), body=body,
                       n_m=len(moyoshi), n_b=len(boshu), n_s=len(seido),
                       title=_html.escape(title), tagline=_html.escape(tagline),
                       h1_html=h1_html,
                       contact_html=contact_html, operator_html=operator_html,
                       canonical=canonical, og_url=og_url,
                       filter_nav=filter_nav, filter_css=filter_css)


_TPL = """<!doctype html>
<html lang="ja"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{tagline}">
{canonical}
<meta property="og:type" content="website">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{tagline}">
<meta property="og:locale" content="ja_JP">
{og_url}
<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Zen+Old+Mincho:wght@700;900&family=Zen+Kaku+Gothic+New:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  :root {{
    --paper:#eae6dc; --card:#f6f3ec; --ink:#23211c; --soft:#5f5a4f;
    --sekishu:#8a3a2b; --ai:#33595c; --line:#d2ccbd; --alert:#a8321f;
  }}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--paper);color:var(--ink);
    font-family:"Zen Kaku Gothic New",system-ui,sans-serif;line-height:1.65}}
  .wrap{{max-width:1040px;margin:0 auto;padding:clamp(1.2rem,4vw,3rem) 1.1rem 4rem}}
  header{{border-bottom:2px solid var(--ink);padding-bottom:.9rem}}
  h1{{font-family:"Zen Old Mincho",serif;font-weight:900;margin:0;
    font-size:clamp(1.8rem,5.5vw,3rem);letter-spacing:.05em}}
  h1 .r{{color:var(--sekishu)}}
  h1 ruby rt{{font-family:"Zen Kaku Gothic New",sans-serif;font-weight:400;
    font-size:.26em;color:var(--soft);letter-spacing:.26em;
    text-indent:.26em;transform:translateY(.35em)}}
  .lead{{color:var(--soft);font-size:.8rem;margin-top:.4rem}}
  .counts{{display:flex;gap:.5rem;flex-wrap:wrap;margin:.8rem 0 1.4rem;font-size:.72rem}}
  .counts span{{border:1px solid var(--line);border-radius:999px;padding:.1rem .6rem;
    background:var(--card)}}
  .notice{{background:var(--card);border-left:3px solid var(--sekishu);
    padding:.7rem .9rem;font-size:.75rem;color:var(--soft);margin-bottom:1.6rem;
    border-radius:0 4px 4px 0}}
  .block{{margin-top:2.4rem}}
  .block h2{{font-family:"Zen Old Mincho",serif;font-size:1.15rem;margin:0;
    display:flex;align-items:center;gap:.6rem;border-left:4px solid var(--sekishu);
    padding-left:.6rem}}
  .block.k-boshu h2{{border-color:var(--alert)}}
  .block.k-seido h2{{border-color:var(--ai)}}
  .block h2 .n{{font-family:"Zen Kaku Gothic New";font-size:.7rem;color:var(--soft);
    border:1px solid var(--line);border-radius:999px;padding:.05rem .5rem}}
  .lead2{{font-size:.75rem;color:var(--soft);margin:.35rem 0 .9rem;padding-left:.85rem}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(268px,1fr));gap:.85rem}}
  .card{{background:var(--card);border:1px solid var(--line);border-radius:4px;
    padding:.95rem 1rem;display:flex;flex-direction:column;gap:.35rem}}
  .when{{font-family:"Zen Old Mincho",serif;font-weight:700;color:var(--sekishu);
    font-size:1.05rem;display:flex;align-items:center;gap:.5rem;flex-wrap:wrap}}
  .when .wd{{font-size:.7rem;color:var(--soft);margin-left:.1rem}}
  .when .alert{{color:var(--alert)}}
  .when .alert b{{border-bottom:2px solid var(--alert)}}
  .when .soon{{color:var(--ai)}}
  .when .over{{color:var(--soft);text-decoration:line-through}}
  .when .anytime{{color:var(--ai);font-size:.9rem}}
  .when .tbd{{color:var(--soft);font-size:.85rem;font-weight:400}}
  .when .sessions{{font-size:.72rem;color:var(--soft);margin-left:.2rem;font-weight:400}}
  .card h3{{margin:0;font-size:.97rem;font-weight:500;line-height:1.45}}
  .card h3 a{{color:inherit;text-decoration:none}}
  .card h3 a:hover{{text-decoration:underline}}
  .dl-note{{font-size:.72rem;color:var(--ai);border-left:2px solid var(--ai);
    padding-left:.45rem}}
  .dl-note.alert{{color:var(--alert);border-color:var(--alert);font-weight:700}}
  .dl-note.over{{color:var(--soft);border-color:var(--line)}}
  .tags{{display:flex;gap:.3rem;flex-wrap:wrap}}
  .tg{{font-size:.66rem;color:var(--ai);border:1px solid var(--ai);
    border-radius:999px;padding:.02rem .45rem}}
  .foot{{display:flex;justify-content:space-between;gap:.5rem;flex-wrap:wrap;
    margin-top:auto;padding-top:.5rem;border-top:1px dashed var(--line);
    font-size:.66rem;color:var(--soft)}}
  .muni{{font-weight:700;color:var(--ink)}}
  .badge{{font-size:.65rem;border-radius:999px;padding:.05rem .5rem;
    background:var(--sekishu);color:var(--card)}}
  .card.cancelled,.card.ended{{opacity:.62}}
  .card.cancelled .when{{text-decoration:line-through}}
  .card.last{{border-color:var(--sekishu);border-width:1.5px}}
  details.past{{margin-top:3rem;border-top:1px solid var(--line);padding-top:1.2rem}}
  details.past summary{{font-family:"Zen Old Mincho",serif;font-size:.95rem;
    color:var(--soft);cursor:pointer;display:flex;align-items:center;gap:.6rem}}
  details.past summary .n{{font-family:"Zen Kaku Gothic New";font-size:.7rem;
    border:1px solid var(--line);border-radius:999px;padding:.05rem .5rem}}
  details.past .grid{{margin-top:.9rem;opacity:.6}}
  details.past[open] summary{{margin-bottom:.3rem}}
  .empty{{color:var(--soft);padding:3rem 0}}
  .pick{{display:flex;flex-wrap:wrap;gap:.4rem;margin:0 0 1.1rem}}
  .pick a{{display:inline-flex;align-items:center;gap:.35rem;font-size:.72rem;
    color:var(--ink);text-decoration:none;border:1px solid var(--line);
    border-radius:999px;padding:.25rem .8rem .25rem .7rem;background:var(--card)}}
  .pick a:hover{{border-color:var(--sekishu)}}
  .pick a.all{{font-weight:700}}
  .pick a .c{{font-size:.64rem;color:var(--soft);background:var(--paper);
    border-radius:999px;padding:.02rem .42rem}}
  .anchor{{display:block}}
  .empty-city{{display:none;color:var(--soft);font-size:.8rem;text-align:center;
    padding:2.2rem 1rem;margin:1rem 0;border:1px dashed var(--line);border-radius:4px}}
  {filter_css}
  footer{{margin-top:3rem;padding-top:1rem;border-top:1px solid var(--line);
    font-size:.7rem;color:var(--soft)}}
  a:focus-visible{{outline:2px solid var(--ai);outline-offset:2px}}
</style></head>
<body><div class="wrap">
  <header>
    <h1>{h1_html}</h1>
    <div class="lead">{tagline}　{generated} 更新</div>
  </header>
  <div class="counts">
    <span>催し {n_m}</span><span>募集 {n_b}</span><span>制度 {n_s}</span><span>ぜんぶで {total}</span>
  </div>
  {filter_nav}
  <p class="notice">
    自動で集めた情報です。日時・会場・締切・申込方法は、必ず各カードのリンク先（主催者の公式ページ）で
    最終確認してください。中止や変更が反映されていない場合があります。
  </p>
  {body}
  <footer>
    {operator_html}
    <a href="about.html">このサイトについて・掲載方針・修正/削除のご依頼</a><br>
    各情報の権利は発信元に帰属します。掲載内容は各リンク先の公式ページでご確認ください。<br>
    {contact_html}
  </footer>
</div></body></html>"""
