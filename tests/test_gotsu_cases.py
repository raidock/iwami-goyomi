"""江津市を追加して実際に承認待ちに出た10件で仕分けを検証する。

浜田だけでチューニングした分類器に、江津を足すと何が起きるかの実測。
ここで見つかったのが「のお知らせ」問題（自治体サイトの定型句で判別力がない）。
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from collector.classify import classify

# 2026-07-27 の実運用で承認待ちに出た10件（浜田3・江津7）
CASES = [
    # (タイトル, 期待, 備考)
    ("救命講習定期開催のお知らせ", "keep", "消防の定期講習。住民が参加できる"),
    ("浜田市文化祭協賛行事", "keep", "文化祭の協賛行事"),
    ("一斉相談会（法律相談）のお知らせ", "keep", "無料法律相談"),
    ("令和8年度市長交際費支出状況", "drop", "情報公開もの"),
    ("出前講座をご利用ください", "keep", "随時利用できる制度。自治会に有用"),
    ("【夏季限定】萩・石見空港から大阪へ！", "drop", "交通案内であって催しではない"),
    ("地域おこし協力隊を募集します", "keep", "締切のある募集。移住系として拾いたい"),
    ("江津市ビジネスプランコンテスト「Go-Con2026」", "keep", "江津の看板イベント"),
    ("全面通行止めのお知らせ：市道新江川橋線（江津町・渡津町）", "drop", "道路情報"),
    ("低所得世帯緊急支援給付金のお知らせ", "drop", "世帯向け給付。催しではない"),
]


def main():
    ok = 0
    print(f"{'判定':<6}{'期待':<6}  タイトル")
    print("-" * 72)
    for title, expect, note in CASES:
        v = classify(title)
        got = "drop" if v.bucket == "drop" else "keep"
        mark = "✓" if got == expect else "✗"
        ok += got == expect
        print(f"{mark} {got:<5}{expect:<6}  {title[:34]}")
        if got != expect:
            print(f"        └ score={v.score} / {v.reason}")
            print(f"        └ {note}")

    asked = sum(1 for t, _, _ in CASES if classify(t).bucket != "drop")
    print("-" * 72)
    print(f"  正解 {ok}/{len(CASES)}")
    print(f"  承認作業に出る件数: {asked}件（修正前は10件）")
    return 0 if ok == len(CASES) else 1


def _run_extra():
    ok = 0
    for fn in (test_generic_verbs_need_event_noun, test_no_infra_notice_reaches_auto_publish):
        try:
            fn(); print(f"PASS {fn.__name__}"); ok += 1
        except AssertionError as e:
            print(f"FAIL {fn.__name__}: {e}")
    return ok == 2


if __name__ == "__main__":
    rc = main()
    print()
    ok = _run_extra()
    sys.exit(0 if rc == 0 and ok else 1)

# --- 追加ケース（2026-07 実サイトで発見）------------------------------------
# 「行います」は自治体があらゆる作業に使う汎用動詞。単独で強い根拠にすると
# 工事のお知らせが自動公開されてしまう。
EXTRA = [
    ("水道メーターの取り替えを行います", "drop", "生活インフラ工事。催しではない"),
    ("道路清掃を実施します", "drop", "汎用動詞のみ。催しの語がない"),
    ("危険物取扱者保安講習を行います", "keep", "催しの語（講習）を伴うので催し"),
    ("石見神楽公演を行います", "keep", "催しの語（神楽公演）を伴う"),
]


def test_generic_verbs_need_event_noun():
    for title, expect, note in EXTRA:
        from collector.classify import classify
        v = classify(title)
        got = "drop" if v.bucket == "drop" else "keep"
        assert got == expect, f"{title} → {got}（期待 {expect}）: {note}"


def test_no_infra_notice_reaches_auto_publish():
    """工事・断水の類が自動公開に混ざらないこと（安全性の要）。"""
    from collector.classify import classify
    for title in ["水道メーターの取り替えを行います", "道路清掃を実施します",
                  "全面通行止めのお知らせ：市道新江川橋線", "計画停電を実施します"]:
        assert classify(title).bucket != "auto", f"自動公開に混入: {title}"
