# agent-tools — see AGENTS.md for the public-repo standard this enforces.
#
# `make setup` is the one command a fresh checkout needs.

SHELL := /bin/bash
DENYLIST := .check-public-private
SKILLS := explain-context design implement ship ddd vim-diff-tour
CLAUDE_SKILLS := $(HOME)/.claude/skills
BIN := $(HOME)/.local/bin
REPO := $(shell git rev-parse --show-toplevel)

.DEFAULT_GOAL := help
.PHONY: help setup hooks denylist check check-staged test link unlink doctor

help: ## Show this help
	@echo "agent-tools"
	@echo
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[1m%-14s\033[0m %s\n", $$1, $$2}'
	@echo
	@echo "  Start with: make setup"

setup: hooks ## Configure this checkout (hooks + denylist check)
	@if [ ! -s "$(DENYLIST)" ] || ! grep -qvE '^[[:space:]]*(#|$$)' "$(DENYLIST)" 2>/dev/null; then \
	  printf '\n\033[1;31mSetup incomplete: no denylist.\033[0m\n\n'; \
	  echo "The hooks require $(DENYLIST) and will refuse commits without it."; \
	  echo "It is gitignored on purpose — publishing a list of an employer's internal"; \
	  echo "names would leak exactly what this repo must not contain."; \
	  echo; \
	  echo "  make denylist     # scaffold it, then edit"; \
	  echo; \
	  exit 1; \
	fi
	@echo "Setup complete: hooks active, denylist has $$(grep -cvE '^[[:space:]]*(#|$$)' $(DENYLIST)) pattern(s)."

hooks: ## Activate the pre-commit and pre-push hooks
	@git config core.hooksPath scripts/hooks
	@echo "core.hooksPath = $$(git config core.hooksPath)"
	@echo "  pre-commit scans staged content; pre-push scans the range being published."
	@echo "  Git cannot activate hooks from a clone, so this is once per checkout."

denylist: ## Scaffold the untracked denylist (never overwrites)
	@if [ -e "$(DENYLIST)" ]; then \
	  echo "$(DENYLIST) already exists — not touching it."; \
	else \
	  printf '%s\n' \
	    '# Names that must never appear in tracked content. Untracked and gitignored.' \
	    '#' \
	    '# A REGRESSION TEST, not a detector: it catches names already removed from this repo' \
	    '# once. It cannot catch a new internal name, because a denylist only knows what someone' \
	    '# thought to add. Reading the diff is what covers that gap — see AGENTS.md.' \
	    '#' \
	    '# One extended-regex fragment per line. Examples, replace with your own:' \
	    '#   my-employer' \
	    '#   internal-service-name' \
	    '#   Namespace\.[A-Z][A-Za-z]*' \
	    '#   TICKETPREFIX-[0-9]+' \
	    > "$(DENYLIST)"; \
	  echo "Created $(DENYLIST) — now add your patterns (it has none yet, so hooks will fail)."; \
	fi

check: ## Scan all tracked files
	@./scripts/check-public.sh

check-staged: ## Scan staged content only, as the pre-commit hook does
	@./scripts/check-public.sh --staged --require-denylist

test: ## Run the verify test suite (no network)
	@./verify/tests/run-all.sh

link: ## Symlink skills into ~/.claude/skills and the CLIs into ~/.local/bin
	@mkdir -p "$(CLAUDE_SKILLS)" "$(BIN)"
	@for s in $(SKILLS); do ln -sfn "$(REPO)/$$s" "$(CLAUDE_SKILLS)/$$s"; echo "  $(CLAUDE_SKILLS)/$$s"; done
	@ln -sfn "$(REPO)/verify/verify-spec"  "$(BIN)/verify-spec";  echo "  $(BIN)/verify-spec"
	@ln -sfn "$(REPO)/verify/verify-board" "$(BIN)/verify-board"; echo "  $(BIN)/verify-board"

unlink: ## Remove those symlinks (only ones pointing at this checkout)
	@for s in $(SKILLS); do \
	  l="$(CLAUDE_SKILLS)/$$s"; \
	  if [ -L "$$l" ] && [ "$$(readlink $$l)" = "$(REPO)/$$s" ]; then rm "$$l"; echo "  removed $$l"; fi; \
	done
	@for b in verify-spec verify-board; do \
	  l="$(BIN)/$$b"; \
	  if [ -L "$$l" ] && [ "$$(readlink $$l)" = "$(REPO)/verify/$$b" ]; then rm "$$l"; echo "  removed $$l"; fi; \
	done

doctor: ## Report what is and isn't configured
	@printf 'repo:            %s\n' "$(REPO)"
	@hp=$$(git config core.hooksPath || true); \
	 if [ -n "$$hp" ]; then printf 'hooks:           %s\n' "$$hp"; \
	 else printf 'hooks:           \033[1;31mUNSET — not running. make hooks\033[0m\n'; fi
	@if [ -f "$(DENYLIST)" ]; then \
	   n=$$(grep -cvE '^[[:space:]]*(#|$$)' $(DENYLIST) || true); \
	   if [ "$$n" -gt 0 ]; then printf 'denylist:        %s pattern(s)\n' "$$n"; \
	   else printf 'denylist:        \033[1;31mempty — hooks will refuse to commit\033[0m\n'; fi; \
	 else printf 'denylist:        \033[1;31mmissing — hooks will refuse to commit. make denylist\033[0m\n'; fi
	@printf 'VERIFY_HOME:     %s\n' "$${VERIFY_HOME:-$$HOME/verify (default)}"
	@if [ -n "$${VERIFY_GH_OWNER:-}" ]; then printf 'VERIFY_GH_OWNER: %s\n' "$$VERIFY_GH_OWNER"; \
	 else printf 'VERIFY_GH_OWNER: \033[1;33munset — bare repo names in specs fail open\033[0m\n'; fi
	@n=0; for s in $(SKILLS); do [ -L "$(CLAUDE_SKILLS)/$$s" ] && n=$$((n+1)); done; \
	 printf 'skills linked:   %s/%s\n' "$$n" "$(words $(SKILLS))"
