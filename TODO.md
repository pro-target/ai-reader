# TODO — ai-reader (as of 2026-06-21)

Read `_docs/handoff/2026-06-21_session-end.md` first for full context.

## NOW (do before anything else next session)

- [ ] **Commit the 8 PRs.** Verify `git status` shows no secrets.
      Pick strategy: per-PR atomic (8 commits, recommended for review)
      or 1 squash commit.
- [ ] **Wire `_quarantine` into 4 other parsers** (claude/opencode/
      antigravity/pi). Replace bare `continue` on bad JSON with
      `QuarantineSink(agent, uuid).quarantine(line_no, raw, reason)`.

## NEXT (after NOW)

- [ ] **Add `privacy_scan` module** (PR18 cherry-pick, MIT).
      Copy `agent-continuity/scripts/privacy-scan.py` (175 LOC)
      to `src/ai_reader/privacy_scan.py` + add `ai-reader scan <path>`
      CLI subcommand.
- [ ] **Code review** — run cavecrew-reviewer on each of 8 PRs.
      8 parallel subagents, one per PR diff.
- [ ] **Generate remaining per-cherry-pick reports** (8 more files in
      `_docs/audit/2026-06-21-32-repo-scan/reports/`). Optional —
      SUMMARY.md is sufficient to act on.

## DEFERRED (triggered by user request or specific condition)

- **FTS5 hybrid search** — trigger: title-substring search complaints.
- **Hash-chained audit ledger** — trigger: enterprise/regulated use.

## DONE (this session 2026-06-21)

- [x] 32-repo scan (10 cherry-pick, 21 reference-only, 1 avoid)
- [x] PR1 codex event_msg + archived_sessions
- [x] PR2 claude title priority + claude_derive (extract_decisions, summarize_task)
- [x] PR3 claude incremental byte-offset reader
- [x] PR4 _quarantine.py module
- [x] PR5 registry find_sessions + ambiguous-query fallback
- [x] PR6 agents.py + `ai-reader detect-agent` CLI
- [x] PR7a exporters/rounds.py + `ai-reader export rounds` CLI
- [x] PR7b session_note template + validator
- [x] codex dedup key 64→256 chars + env override + system-noise filter
- [x] 237/237 tests pass
- [x] SUMMARY.md + 2 detailed reports + handoff packet
