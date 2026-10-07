# テストの時限爆弾 — 今日を進めて全テストを回す（2026-10-07）

- **測ったもの**: テストに書いた固定の日付が、実際の今日を過ぎたときに落ちるテストはどれか・いつ落ちるか
- **データ**: `tests/` の全テスト（`test_check_links.py` を除く）。今日を 2026-10-07 から 2031-12-31 まで1日刻み、2040-12-31 まで1週間刻みで進めた
- **結論**: 落ちるのは2本だった。どちらも `today=` を渡して直し、**直したあとは2040年末まで1本も落ちない**

背景は `CLAUDE.md`「開発のしかた」の「テストの『今日』は固定する」。

## 結果（直す前）

| テスト | 落ち始める日 | 原因 |
|---|---|---|
| `test_dedup.py` の2件 | **2026-09-13**（気づいたのは 10-07） | `ingest()` に `today` を渡しておらず、9/12 の催しが `is_finished()` で弾かれた |
| `test_feed_pages.py` の1件 | 2027-08-16 | フィードの足切り（`MunicipalRSS.parse_feed`）が実際の今日を見ていた。掲載日 2024-05-02 ＋ 1200日 |
| `test_feed_pages.py` の8件 | 2027-08-26 | 同上。掲載日 2026-07-21 ＋ 400日 |

ほかの15本は、2040年末まで1日も落ちなかった。

今日より後の日付を書いているテストは、ほかにもある（2026-10-07 時点で `test_extract` `test_kinds` `test_oda_city` `test_wareki`）。
ただし、どれも抽出の基準日（`ref=`）や固定した `today=` と比べているだけで、実際の今日には依存しない。
**日付が書いてあること自体は問題ではない。** 問題は、実際の今日と比べる経路に、固定した日付が流れ込むことだった。

## やり方（次に確かめるとき用）

「今日」は全部 `collector/models.py` の `now_jst()` を通る（`today_jst()` もこれを呼ぶ）。
そこで、テストより先に `now_jst` を差し替えてからテストを実行すれば、時間だけを進められる。
`now_jst` を名前で取り込むモジュール（`publish` / `renderers` / `about`）にも効くよう、
差し替える関数は外に置いた1つの日付を読む形にする。

```python
# python timewarp.py <リポジトリ> <テスト> <開始日> <終了日> <刻み日数>
import sys, runpy, io, contextlib, json
from datetime import datetime, date, timedelta
ROOT, test, start, end, step = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])
sys.path.insert(0, ROOT)
import collector.models as M
CUR = {"d": None}
M.now_jst = lambda: datetime(CUR["d"].year, CUR["d"].month, CUR["d"].day, 12, 0, tzinfo=M.JST)
d, last, res = date.fromisoformat(start), date.fromisoformat(end), {}
while d <= last:
    CUR["d"], buf, code = d, io.StringIO(), 0
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            runpy.run_path(test, run_name="__main__")
        except SystemExit as e:
            code = e.code or 0
        except Exception:
            code = 99
    res[d.isoformat()] = [code, [l[5:] for l in buf.getvalue().splitlines() if l.startswith("FAIL ")]]
    d += timedelta(days=step)
print(json.dumps(res, ensure_ascii=False))
```

17本を1週間刻み（274日分）で回して、手元で約35秒。ネットワークには出ない。
**動くことの確かめ方**: 直す前の `test_dedup.py`（`17777d3`）をこのスクリプトで回すと、9/12 までは通り、9/13 から実際と同じ2件が落ちた。
