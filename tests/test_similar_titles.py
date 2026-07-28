"""市またぎ重複の「気づき」表示のテスト。

県全体の催しは市町ごとに違う切り口で流れてくる。しまねふるさとフェアは
浜田市が「参加申込」、益田市が「出展者募集」で載せていた（2026-07 の下調べ）。
対象読者も種別も違うので機械的に寄せてはいけないが、人が気づけるようにする。

しきい値は意図的に緩い。気づけないほうが、似ていないものに警告が出るより痛い。
"""
import sys, pathlib, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from collector.models import Event
from collector.review import ReviewQueue, normalize_title, title_similarity


def _ev(title, city, url, kind="催し"):
    return Event(title=title, prefecture="島根県", date_start=None, date_end=None,
                 url=url, source="t", city=city, kind=kind)


def _queue(pending=(), approved=()):
    q = ReviewQueue(pathlib.Path(tempfile.mkdtemp()))
    q._save(q.pending_path, list(pending))
    q._save(q.approved_path, list(approved))
    return q


# ---- 似ていると判定してほしいもの ------------------------------------
def test_shimane_furusato_fair_across_cities():
    """浜田の参加申込と益田の出展者募集（下調べで見つかった実例）"""
    s = title_similarity("しまねふるさとフェア２０２７（広島市）参加申込について",
                         "しまねふるさとフェア2027 出展者募集")
    assert s >= 0.5, f"市またぎの重複に気づけていない: {s:.2f}"


def test_osakana_ryori_kyoshitsu():
    """公開中の実データにあった同一催しの2枚（日程 / 受講者募集）"""
    s = title_similarity("令和8年度山陰浜田港お魚料理教室の開催日程について",
                         "「山陰浜田港お魚料理教室」の開催について（受講者募集）")
    assert s >= 0.5, f"同じ催しに気づけていない: {s:.2f}"


def test_zenkaku_hankaku_only_difference():
    """全角半角・空白・記号だけの違いは同じものとして扱う"""
    assert title_similarity("第１３回　小さな世界展", "第13回 小さな世界展") == 1.0


def test_one_contains_the_other():
    """片方がもう片方を含む形（募集がついただけ）"""
    assert title_similarity("さざんか祭り", "さざんか祭り 参加者募集") == 1.0


# ---- 似ていないと判定してほしいもの ----------------------------------
def test_unrelated_events_do_not_warn():
    """承認待ちにあった別々の催し同士は鳴らない"""
    s = title_similarity("夏のファミリーアートタイム", "第13回 小さな世界展")
    assert s < 0.5, f"無関係なものに警告が出ている: {s:.2f}"


def test_leading_boilerplate_alone_is_not_similar():
    """「令和8年度」「第3回」が揃っただけでは似ていると言わない"""
    s = title_similarity("令和8年度浜田市総合防災訓練", "令和8年度江津市成人式のご案内")
    assert s < 0.5, f"頭の定型句だけで鳴っている: {s:.2f}"


def test_normalize_drops_symbols_and_space():
    assert normalize_title("【浜田市】　石見神楽・定期公演！") == "浜田市石見神楽定期公演"


# ---- キューの上での挙動 ----------------------------------------------
def test_warns_against_approved():
    """公開中のものと似ていれば警告する"""
    pend = [_ev("しまねふるさとフェア2027 出展者募集", "益田市", "https://a.jp/1")]
    appr = [_ev("しまねふるさとフェア２０２７（広島市）参加申込について",
                "浜田市", "https://b.jp/2")]
    w = _queue(pend, appr).similarity_warnings()
    hits = w.get(pend[0].uid, [])
    assert hits, "公開中との重複に気づけていない"
    assert hits[0][1] == "公開中", hits[0][1]


def test_warns_against_other_pending():
    """同じ日の収集で両市から入ると、どちらも未承認のまま並ぶ"""
    a = _ev("しまねふるさとフェア2027 出展者募集", "益田市", "https://a.jp/1")
    b = _ev("しまねふるさとフェア２０２７（広島市）参加申込について",
            "浜田市", "https://b.jp/2")
    w = _queue([a, b]).similarity_warnings()
    assert a.uid in w and b.uid in w, "承認待ち同士を見ていない"
    assert w[a.uid][0][1] == "承認待ち"


def test_does_not_warn_about_itself():
    """自分自身は似ているものに数えない"""
    a = _ev("夏のファミリーアートタイム", "浜田市", "https://a.jp/1")
    assert _queue([a]).similarity_warnings() == {}


def test_data_is_not_modified():
    """表示専用。データは一切変更しない"""
    a = _ev("しまねふるさとフェア2027 出展者募集", "益田市", "https://a.jp/1")
    b = _ev("しまねふるさとフェア２０２７（広島市）参加申込について",
            "浜田市", "https://b.jp/2")
    q = _queue([a], [b])
    before = (q.pending_path.read_text("utf-8"), q.approved_path.read_text("utf-8"))
    q.similarity_warnings()
    after = (q.pending_path.read_text("utf-8"), q.approved_path.read_text("utf-8"))
    assert before == after, "警告の副作用でデータが書き換わっている"
    assert [e.review_state for e in q.pending] == ["pending"]


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
