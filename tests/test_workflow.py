"""GitHub Actions のワークフローを手元で検証する。

2026-07 の事故: pushトリガーを足す編集で「変更を保存」ステップの3行が落ち、
`run: |` と git config の2行が消えて `m"` だけが残った。YAMLとして不正なため
ワークフローは開始すらせず 0s で失敗し、**毎朝6時の自動収集が2日間止まった。**
テストは全部緑、手元の生成物も正常で、GitHubのActions画面を見るまで
分からなかった。

CIの設定はコードと違って手元で動かないので、壊れても気づけない。
最低限の形をここで守る。PyYAML は既に依存にあるので追加はいらない。
"""
import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import yaml

WORKFLOW = pathlib.Path(__file__).resolve().parents[1] / ".github/workflows/collect.yml"


def _load():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_workflow_file_exists():
    assert WORKFLOW.exists(), f"ワークフローが無い: {WORKFLOW}"


def test_workflow_is_valid_yaml():
    """これが落ちていれば、今回の3行欠落はpushの前に分かった。"""
    try:
        doc = _load()
    except yaml.YAMLError as e:
        raise AssertionError(f"YAMLとして読めない（Actionsは0秒で失敗する）: {e}")
    assert isinstance(doc, dict), "トップレベルがマッピングではない"


def test_has_collect_and_deploy_jobs():
    jobs = _load()["jobs"]
    for name in ("collect", "deploy"):
        assert name in jobs, f"job「{name}」が無い: {list(jobs)}"


def test_deploy_needs_collect():
    """収集より先に公開されると、古い生成物が出てしまう。"""
    needs = _load()["jobs"]["deploy"].get("needs")
    needs = [needs] if isinstance(needs, str) else (needs or [])
    assert "collect" in needs, f"deploy が collect を needs していない: {needs}"


def test_deploy_does_not_need_health():
    """健康診断の失敗で公開が止まってはいけない。

    2026-08-08、川本町観光協会が一時的に0件になっただけで `deploy` が
    スキップされ、公開が止まった（`deploy` が `needs: collect` で待つ作りで、
    健康診断はその `collect` の中の1ステップだったため）。
    `health` を切り離した以上、`deploy` の `needs` に `health` が
    紛れ込んでいないことを守る。
    """
    needs = _load()["jobs"]["deploy"].get("needs")
    needs = [needs] if isinstance(needs, str) else (needs or [])
    assert "health" not in needs, f"deploy が health を待つ形に戻っている: {needs}"


def test_health_is_its_own_job():
    """健康診断は collect とは別ジョブ。collect が赤くなっても関係ない形。"""
    jobs = _load()["jobs"]
    assert "health" in jobs, f"health ジョブが無い: {list(jobs)}"
    steps = jobs["health"]["steps"]
    runs = "\n".join(s.get("run", "") for s in steps if isinstance(s, dict))
    assert "main.py health" in runs, "health ジョブに健康診断の run が無い"


def test_collect_job_no_longer_runs_health():
    """健康診断は collect の外に出ている（collect 内に残っていると二重に走る）。"""
    assert "main.py health" not in _collect_runs(), \
        "健康診断が collect ジョブにまだ残っている"


def _collect_runs() -> str:
    steps = _load()["jobs"]["collect"]["steps"]
    return "\n".join(s.get("run", "") for s in steps if isinstance(s, dict))


def test_collect_job_runs_collect_build_and_push():
    """収集・生成・保存の3つが揃っていること。

    今回落ちたのは「変更を保存」の run そのもの。ステップ名は残っていたので、
    名前ではなく中身（run）で見る。
    """
    runs = _collect_runs()
    for frag, why in [("main.py collect", "収集"),
                      ("main.py build", "サイト生成"),
                      ("git push", "変更の保存")]:
        assert frag in runs, f"{why} の run が無い（{frag}）"


def test_data_dir_is_the_repository_one():
    """ホームに置くとGitHub上では毎回消える。--data-dir ./data で上書きすること。"""
    runs = _collect_runs()
    for cmd in ("main.py collect", "main.py build"):
        line = next((l for l in runs.splitlines() if cmd in l), "")
        assert "--data-dir ./data" in line, f"{cmd} に --data-dir ./data が無い: {line!r}"


def test_bot_identity_is_configured():
    """コミット規約どおり iwami-goyomi-bot 名義で保存する。

    ここが落ちたのが今回の事故そのもの（git config の2行が消えた）。
    """
    runs = _collect_runs()
    assert "git config user.name" in runs, "ボット名の設定が無い"
    assert "iwami-goyomi-bot" in runs, "コミット作者が iwami-goyomi-bot でない"


def test_push_event_does_not_recollect():
    """pushでは収集しない。情報源への負荷と、ボットのpushでの自走を防ぐ。"""
    steps = _load()["jobs"]["collect"]["steps"]
    for s in steps:
        if isinstance(s, dict) and "main.py collect" in s.get("run", ""):
            assert "push" in str(s.get("if", "")), \
                f"収集ステップに push を除く条件が無い: {s.get('if')!r}"
            return
    raise AssertionError("収集ステップが見つからない")


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
