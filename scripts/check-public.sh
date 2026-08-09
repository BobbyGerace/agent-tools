#!/usr/bin/env bash
# Secret-shape scan for a public repo. See AGENTS.md for the actual standard.
#
# WHAT THIS CATCHES: strings whose *form* identifies them, regardless of content — token
# formats, connection strings with embedded credentials, personal absolute paths, internal
# hostnames. No knowledge of your employer is needed for any of it.
#
# WHAT THIS CANNOT CATCH, AND WHY READING THE DIFF IS THE REAL CHECK: whether a sentence is
# company-specific is semantic, not lexical. All three of these are private and no regex finds
# them, because none contains an identifier:
#
#   "three divergent definitions of whether an update was actionable"
#   "the 24-business-hour clock doesn't start until Monday 9am"
#   "the daily 72-hour digest, 8 files"
#
# So: a clean run means "no credential-shaped string", not "safe to publish". GitHub's own secret
# scanning and push protection run server-side on public repos and are better maintained than
# this file; treat this as the local pre-commit convenience, not the defence.
#
# Usage:
#   ./scripts/check-public.sh              # all tracked files
#   ./scripts/check-public.sh --diff       # only what changed vs HEAD
#   ./scripts/check-public.sh --staged     # only what's staged

set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

MODE=all
RANGE=""
REQUIRE_DENYLIST=0
while [ $# -gt 0 ]; do
  case "$1" in
    --diff|--staged|all) MODE="$1" ;;
    --range) MODE=--range; RANGE="${2:-}"; shift ;;
    --require-denylist) REQUIRE_DENYLIST=1 ;;
    *) echo "usage: $0 [--diff|--staged|--range A..B] [--require-denylist]" >&2; exit 2 ;;
  esac
  shift
done

case "$MODE" in
  --diff)   FILES=$(git diff --name-only --diff-filter=d HEAD) ;;
  --staged) FILES=$(git diff --cached --name-only --diff-filter=d) ;;
  --range)
    [ -n "$RANGE" ] || { echo "--range needs A..B" >&2; exit 2; }
    FILES=$(git diff --name-only --diff-filter=d "$RANGE") ;;
  *)        FILES=$(git ls-files) ;;
esac

# This script documents the patterns it looks for, so it would match itself. CLAUDE.md is a
# symlink to AGENTS.md and has to be named too, since grep follows the link.
FILES=$(printf '%s\n' "$FILES" | grep -vE '^(scripts/check-public\.sh|AGENTS\.md|CLAUDE\.md)$')

if [ -z "${FILES//[[:space:]]/}" ]; then echo "nothing to scan"; exit 0; fi

hits=0

# Documentation placeholders are not secrets.
PLACEHOLDER='user:pass|USER:PASS|username:password|<[^>]+>:|:pass@|:password@|xxx|yyy|changeme|REDACTED|example\.com'

scan() {
  local label="$1" pattern="$2" allow="${3:-}" out
  out=$(printf '%s\n' "$FILES" | tr '\n' '\0' | xargs -0 grep -nEI --color=never "$pattern" 2>/dev/null)
  [ -n "$allow" ] && out=$(printf '%s\n' "$out" | grep -vE "$allow")
  out=$(printf '%s\n' "$out" | grep -v '^$')
  [ -z "$out" ] && return 0
  printf '\n--- %s ---\n%s\n' "$label" "$out"
  hits=$((hits + 1))
}

scan "credentials and tokens" \
  '(ghp|gho|ghs|ghu)_[A-Za-z0-9]{16,}|sk-[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY'

scan "connection strings with real-looking credentials" \
  '(postgres|postgresql|mysql|mongodb(\+srv)?|redis|amqp)://[^[:space:]"'"'"']*:[^[:space:]"'"'"'@]+@' \
  "$PLACEHOLDER"

scan "assigned secrets" \
  '(password|passwd|secret|api[_-]?key|app[_-]?key|auth[_-]?token|access[_-]?token|bearer)[[:space:]]*[:=][[:space:]]*["'"'"'][^"'"'"'[:space:]]{8,}' \
  "$PLACEHOLDER"

scan "personal absolute paths" \
  '/Users/[a-z]|/home/[a-z]'

scan "internal hostnames" \
  '[a-z0-9-]+\.(internal|corp|local|lan|intra)\b'

# Optional, and a REGRESSION TEST rather than a detector: names you have already removed once.
# It cannot catch a new internal name, because a denylist only knows what you thought to add.
# The list has to stay untracked — publishing a list of an employer's internal names would leak
# exactly what this repo must not contain. One extended-regex fragment per line, `#` comments ok.
PRIVATE_FILE=".check-public-private"
PRIVATE_PATTERN=""
[ -f "$PRIVATE_FILE" ] && PRIVATE_PATTERN=$(grep -vE '^[[:space:]]*(#|$)' "$PRIVATE_FILE" | paste -sd '|' -)

if [ -n "$PRIVATE_PATTERN" ]; then
  scan "previously-removed private names ($PRIVATE_FILE)" "$PRIVATE_PATTERN"
elif [ "$REQUIRE_DENYLIST" -eq 1 ]; then
  # The hooks pass --require-denylist, so a missing or empty list fails instead of passing
  # quietly. A green run with this category silently switched off is the exact false confidence
  # the whole script exists to avoid — and it is invisible precisely when it matters, on a fresh
  # clone where nobody has set it up yet.
  if [ -f "$PRIVATE_FILE" ]; then
    reason="$PRIVATE_FILE exists but defines no patterns (only comments or blanks)"
  else
    reason="$PRIVATE_FILE does not exist"
  fi
  cat >&2 <<EOF

FAIL — no denylist configured: $reason

The shape-based checks above cannot recognize an employer's internal names; the denylist is what
catches a name that was already removed from this repo once. Without it that category is off, and
a pass here would mean less than it appears to.

Create it (untracked — it is gitignored, and publishing a list of internal names would leak
exactly what this repo must not contain), one extended-regex fragment per line:

    make denylist        # scaffolds the file, then edit it
    \$EDITOR $PRIVATE_FILE

If you genuinely have nothing to list — a fork with no private history behind it — run the
script without --require-denylist, or commit with --no-verify and know why you did.
EOF
  exit 1
else
  echo "note: no $PRIVATE_FILE — the previously-removed-names check is not running."
  echo "      See AGENTS.md; it is one regex per line and must stay untracked."
fi

echo
if [ "$hits" -gt 0 ]; then
  cat <<'EOF'
FAIL — do not commit.

If a hit is in a change you did not author, stop and ask rather than deciding for the person
whose material it is.
EOF
  exit 1
fi

cat <<'EOF'
No credential-shaped strings found.

That is NOT a pass. Whether a line is company-specific is a judgment this script cannot make —
read the diff against the portability test in AGENTS.md.
EOF
