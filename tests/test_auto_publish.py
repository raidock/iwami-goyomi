"""どこへ入れるか（auto / review / drop）の判断。`classify.decide_bucket`。

**人を通さず公開するなら、タイトルに根拠が要る。**

本文は「拾う」には十分でも、「人が見ずに公開する」には足りません。
本文は別の話題を語りうるからです。実際に踏みました（邑南町 2026-08-01）:

    【大切なお知らせ】いわみスタジアム・瑞穂球場を改修します
      タイトルだけなら score 0。RSS要約に「2030年に国民スポーツ大会が
      開催されます」と**改修の理由として**書かれているため score 7 で自動公開。

水道メーター事故と同じ形です。語を1つずつ潰すのは対症療法なので
（`を改修します` を一度入れて、この規則ができた時点で外しました）、
**根拠の置き場所そのもの**を条件にしています。

**観光協会には課しません**（設計判断11）。あちらは情報源そのものが根拠で、
「8/9 鮎小屋」のようにタイトルが短い催しが普通にあります。
課すと実データ173件で15件が承認待ちに移り、**全部が本物**でした。
自治体だけに課せば、同じ実データで移るものは **0件**（2026-08-01 実測）。
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from collector.classify import classify, decide_bucket


def route(title, body="", trust="normal"):
    return decide_bucket(classify(title, body), title, trust)


# --- 本文だけを根拠に自動公開しない -----------------------------------------

BALLPARK = ("【大切なお知らせ】いわみスタジアム・瑞穂球場を改修します",
            "いわみスタジアム・瑞穂球場の施設利用をされるみなさま "
            "2030年（令和12年）に島根県で「国民スポーツ大会」が開催されます")


def test_body_only_evidence_is_not_auto_published():
    """実データ。タイトル score 0 / 全体 score 7 で自動公開されていた。"""
    assert classify(*BALLPARK).score >= 4, "前提が変わっている（本文で高得点のはず）"
    assert classify(BALLPARK[0]).score <= 0, "前提が変わっている（タイトルは無根拠のはず）"
    assert route(*BALLPARK) == "review"


def test_title_evidence_still_auto_publishes():
    """タイトルに根拠があるものは、これまでどおり自動公開する。"""
    assert route("さざんか祭りを開催します", "今年も開催します") == "auto"


def test_body_only_does_not_become_drop():
    """**捨ててはいけない。** 人が見る場所へ回すだけ（取りこぼしゼロが最優先）。"""
    assert route(*BALLPARK) != "drop"


# --- 観光協会には課さない（設計判断11）--------------------------------------

def test_tourism_short_titles_still_auto():
    """観光協会はタイトルが短い。課すと本物が15件も承認待ちに移る（実測）。

    本文は実データから写したもの。**合成データに置き換えないこと** —
    点の付き方が変わって、守りたいものを守れなくなる。
    """
    for title, body in [
        # はまナビ「和紙と灯りの夕べ2026夏」（全体2 / タイトル0）
        ("和紙と灯りの夕べ2026夏",
         "今できること、和紙に触れて、つながろう夜を和紙と灯りで彩る特別な日。"
         "和紙の灯りとともに、うちわアートやワークショップなどをお楽しみください。"),
        # 邑南町観光協会「8/9 鮎小屋」（全体3 / タイトル0）
        ("8/9 鮎小屋", "8/9（土）鮎小屋が開催されます"),
    ]:
        assert classify(title).score <= 0, f"前提が変わっている: {title}"
        assert classify(title, body).score >= 2, f"前提が変わっている: {title}"
        assert route(title, body, trust="high") == "auto", title
        # **同じものを自治体の情報源として見ると承認待ちへ回る。** これが狙い
        assert route(title, body, trust="normal") == "review", title


def test_tourism_threshold_is_unchanged():
    """`trust: high` のしきい値（score>=2 で auto）を変えていないこと。"""
    v = classify("ぶどうまつり")
    assert 2 <= v.score < 4, f"前提が変わっている: {v.score}"
    assert decide_bucket(v, "ぶどうまつり", "high") == "auto"
    assert decide_bucket(v, "ぶどうまつり", "normal") == "review"


def test_tourism_does_not_swallow_hard_exclusions():
    """除外語を踏んだ -10 は観光協会でも通さない（既存の穴ふさぎの回帰）。"""
    assert route("市道○○線の通行止めについて", "", trust="high") == "drop"


# --- 対症療法を外したことの確認 ---------------------------------------------

def test_renovation_word_is_gone():
    """`を改修します` を除外語に戻さないこと。**原因を直したら語は外す。**

    戻すと「改修記念コンサート」のような本物を巻き込む方向へ育ちやすい。
    """
    from collector.classify import HARD_EXCLUDE
    assert "を改修します" not in HARD_EXCLUDE
    assert route("石央文化ホール改修記念コンサートを開催します") == "auto"


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
