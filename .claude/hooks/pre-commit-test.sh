#!/usr/bin/env bash
# git commit の直前にテストを走らせ、赤ならコミットを止める。
#
# tests/test_check_links.py は外部サイトを叩くので除外する（CLAUDE.md 設計判断12）。
# 残り17本は手元で 2 秒弱。コミットのたびに回しても負担にならない。

cmd=$(python3 -c 'import sys, json; print(json.load(sys.stdin).get("tool_input", {}).get("command", ""))' 2>/dev/null)

case "$cmd" in
  *"git commit"*) ;;
  *) exit 0 ;;
esac

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
[ -d tests ] || exit 0

py=python3
[ -x .venv/bin/python ] && py=.venv/bin/python

failed=""
for f in tests/test_*.py; do
  case "$f" in
    *check_links*) continue ;;
  esac
  if ! out=$("$py" "$f" 2>&1); then
    failed="$failed
--- $f ---
$(printf '%s\n' "$out" | tail -15)"
  fi
done

if [ -n "$failed" ]; then
  {
    echo "テストが失敗しているため、コミットを止めました。"
    echo "先にテストを緑にしてから、もう一度コミットしてください。"
    printf '%s\n' "$failed"
  } >&2
  exit 2
fi

exit 0
