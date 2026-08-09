#!/usr/bin/env bash
# Every suite, no network. Connectors and gh are stubbed throughout, so this
# never touches prod.
cd "$(dirname "$0")"
total=0; failed=0
for t in test_*.py; do
  out=$(python3 "$t" 2>&1); n=$(echo "$out" | grep -c "^  ok")
  if echo "$out" | grep -qE "^  BAD|^  !!|FAILED|Traceback"; then
    printf "  %-24s %3d ok  FAIL\n" "$t" "$n"; echo "$out" | tail -20; failed=1
  else
    printf "  %-24s %3d ok  PASS\n" "$t" "$n"
  fi
  total=$((total+n))
done
echo "  TOTAL: $total assertions"
exit $failed
