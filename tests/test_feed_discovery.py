"""RSS自動発見のテスト。

江津市は<head>のautodiscoveryを持たず、本文の<a>にRSSを3本並べていた。
実運用で自動発見が失敗した実例なので、その構造を再現して回帰テストにする。
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from collector.sources.municipal_rss import MunicipalRSS

# 江津市トップページの実際の構造（2026-07 curl で確認）
GOTSU_HTML = """
<html><head><title>江津市ホームページ</title></head><body>
  <div class="box">
    <span class="link_rss"><a href="/rss/10/list3.xml">重要なお知らせのRSS</a></span>
  </div>
  <div class="box">
    <span class="link_rss"><a href="/rss/10/list1.xml">新着情報のRSS</a></span>
  </div>
  <div class="box">
    <span class="link_rss"><a href="/rss/10/list6.xml">トピックスのRSS</a></span>
  </div>
</body></html>
"""

# 浜田市のような、<head>にautodiscoveryを持つ標準的な形
HAMADA_HTML = """
<html><head>
  <link rel="alternate" type="application/rss+xml" title="新着情報"
        href="/www/rss/news.rdf">
</head><body></body></html>
"""

# RSSリンクがまったく無いサイト
NO_FEED_HTML = "<html><head></head><body><a href='/about'>市について</a></body></html>"

# プロトコル相対URL（`//host/path`）。CMSがCDNを挟むと出てくる標準的な書き方で、
# http で始まらないため site と直結され壊れていた。
PROTO_RELATIVE_HTML = """
<html><head>
  <link rel="alternate" type="application/rss+xml" title="新着情報"
        href="//cdn.example.jp/rss/news.rdf">
</head><body></body></html>
"""


def _src(html, site="https://www.city.gotsu.lg.jp"):
    s = MunicipalRSS(key="t", site=site, municipality="テスト市")
    s.get = lambda url: html          # ネットに出ずに差し替える
    return s


def test_finds_rss_in_body_anchors():
    """江津市パターン: 本文の<a>から見つけられる"""
    url = _src(GOTSU_HTML).discover_feed()
    assert url is not None, "本文の<a>からRSSを見つけられていない"
    assert url.endswith(".xml"), url


def test_prefers_shinchaku_over_others():
    """RSSが複数あるとき「新着情報」を選ぶ（重要なお知らせでは催しが拾えない）"""
    url = _src(GOTSU_HTML).discover_feed()
    assert url.endswith("/rss/10/list1.xml"), f"新着情報を選べていない: {url}"


def test_head_autodiscovery_still_works():
    """浜田市パターン: <head>のautodiscoveryは従来どおり優先される"""
    url = _src(HAMADA_HTML, "https://www.city.hamada.shimane.jp").discover_feed()
    assert url == "https://www.city.hamada.shimane.jp/www/rss/news.rdf", url


def test_explicit_feed_url_wins():
    """config.yaml で明示したURLが最優先"""
    s = MunicipalRSS(key="t", site="https://x.jp", municipality="市",
                     feed_url="https://x.jp/my.xml")
    assert s.discover_feed() == "https://x.jp/my.xml"


def test_abs_protocol_relative():
    """`//host/path` はサイトのスキームを引き継ぐ（site と直結してはいけない）"""
    s = _src("", "https://www.city.hamada.shimane.jp")
    assert s._abs("//cdn.example.jp/rss.xml") == "https://cdn.example.jp/rss.xml"


def test_abs_absolute_url_untouched():
    """絶対URLはそのまま"""
    s = _src("", "https://www.city.hamada.shimane.jp")
    assert s._abs("https://other.example.jp/a.rdf") == "https://other.example.jp/a.rdf"
    assert s._abs("http://other.example.jp/a.rdf") == "http://other.example.jp/a.rdf"


def test_abs_relative_paths():
    """ルート相対も、先頭スラッシュ無しの相対パスも繋がる"""
    s = _src("", "https://www.city.hamada.shimane.jp")
    assert s._abs("/www/rss/news.rdf") == "https://www.city.hamada.shimane.jp/www/rss/news.rdf"
    assert s._abs("rss/news.rdf") == "https://www.city.hamada.shimane.jp/rss/news.rdf"


def test_discover_feed_with_protocol_relative_href():
    """自動発見の経路でもプロトコル相対URLが正しく解ける"""
    url = _src(PROTO_RELATIVE_HTML, "https://www.city.hamada.shimane.jp").discover_feed()
    assert url == "https://cdn.example.jp/rss/news.rdf", url


def test_no_feed_returns_none_gracefully():
    """見つからないときは落ちずに None を返す（fallbackも失敗する想定）"""
    s = _src(NO_FEED_HTML)
    s.get = lambda url: (_ for _ in ()).throw(Exception("404")) if "rss" in url \
        or "feed" in url else NO_FEED_HTML
    assert s.discover_feed() is None


def test_user_agent_names_this_project():
    """名乗る名前が実体と合っていること（設計判断12）。

    かつて base.py は蚤の市時代の sanin-nomi-collector、main.py は
    iwami-events-collector/1.5 を名乗っていた。相手のサーバの管理者が
    見て誰が来ているか辿れないなら、名乗った意味がない。
    """
    from collector import USER_AGENT, __version__
    from collector.sources.base import USER_AGENT as UA_SOURCES
    assert USER_AGENT.startswith(f"iwami-goyomi/{__version__}"), USER_AGENT
    assert "https://" in USER_AGENT, USER_AGENT   # 連絡先が辿れること
    assert UA_SOURCES is USER_AGENT               # 定義は1か所だけ


def test_user_agent_is_not_hardcoded_anywhere():
    """UAの文字列を直書きした箇所が増えていないこと。

    2か所に別々の名前が書かれて両方古びたのが元の事故なので、
    「1か所にまとまっている」ことをテストで押さえる。
    """
    root = pathlib.Path(__file__).resolve().parents[1]
    hits = []
    for path in list(root.glob("*.py")) + list(root.glob("collector/**/*.py")):
        if path.name == "__init__.py" and path.parent.name == "collector":
            continue                              # ここが唯一の定義
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "User-Agent" in line and ("collector/" in line or "goyomi/" in line):
                hits.append(f"{path.relative_to(root)}:{i} {line.strip()}")
    assert not hits, "UAの直書き: " + " / ".join(hits)


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
