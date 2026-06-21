# TODO — ai-reader (as of 2026-06-21, updated after audit session 13163330)

Read `_docs/handoff/2026-06-21_session-end.md` first for full context
(8-PR session). The addendum at the bottom of that file covers the
follow-up git-audit session `13163330`.

## NOW (do before anything else next session)

- [ ] **Commit session 13163330's test-recovery + safe-fix work.** This
      is the entire current uncommitted working tree (7 files):
      `.github/workflows/ci.yml`, `src/ai_reader/cli.py`,
      `tests/exporters/test_rounds.py`,
      `tests/test_parsers/{test_codex,test_opencode,test_registry}.py`,
      `tests/test_session.py`. **345 tests pass** (verified).
      Confirm `git status` holds no secrets. Recommended single commit
      subject: `test: recover coverage after access-control removal
      (+ CI perms, dedup fix)`. The 8 PRs from the prior session are
      already committed (agents/exporters/templates/search/multi-candidate
      are tracked, absent from working tree).
- [ ] **Bad-JSON handling for 4 other parsers** (claude/opencode/
      antigravity/pi). The dropped-line branch currently does a bare
      `continue`; wiring it to the PR4 sink module (`parsers/_quarantine.py`)
      captures malformed lines instead of silently skipping them.

## SETTLED — not to be re-audited

- **access-control removal (commit `ee72961`)** — intentional and
  user-approved. `ee72961` ("Refactor CLI tests to remove subagent
  environment dependencies") removed the entire `access/` module
  (406 LOC: guard/detector/models/proc/__init__), `tests/test_access/`
  (613 LOC, 5 files), `docs/access-control.md` (134),
  `examples/custom_detector.py` (101), and the `is_caller_subagent` gate
  in `legacy_compat.py`. Net 332+/1917−. The commit message placed a
  security-control removal inside a test-refactor message (commit-hygiene
  violation), but the decision stands: **repo is public →
  caller-authorization is redundant.** Identity ("which session is mine")
  is a separate concern, handled by `session.py` multi-candidate detection
  (4dbb438). Restoring access-control or re-running this audit is not
  wanted; revisit only if the repo becomes private/restricted. Found +
  verified against git by session `13163330` (audit report:
  `/tmp/audit-13163330-.../reports/report.md`).

## NEXT (after NOW)

- [ ] **`privacy_scan` module** (PR18 cherry-pick, MIT). Source lives at
      `agent-continuity/scripts/privacy-scan.py` (175 LOC); mirror it to
      `src/ai_reader/privacy_scan.py` and expose an `ai-reader scan <path>`
      CLI subcommand.
- [ ] **Code review** — cavecrew-reviewer over each of the 8 landed PRs.
      8 parallel subagents, one per PR diff.
- [ ] **`ee72961` decision recorded in `docs/architecture.md` / ADR**
      (audit rec #2, MED) — so future reviewers skip re-auditing. Skippable
      if the SETTLED note above is enough.

## DEFERRED (triggered by user request or specific condition)

- **FTS5 hybrid search** — trigger: title-substring search complaints.
- **Hash-chained audit ledger** — trigger: enterprise/regulated use.

## DONE

- [x] 8 PRs from prior session — landed/committed (agents, exporters/rounds,
      templates+validator, body search, multi-candidate detection; see handoff)
- [x] git-audit of repo over 24h (session 13163330): 4-zone parallel audit,
      surfaced hidden `ee72961` access-control removal
- [x] test recovery after access-control removal (session 13163330, uncommitted):
      17 new tests — identity / multi-candidate / cross-agent / locked-DB /
      codex-filter; **345 pass**
- [x] safe-fixes (session 13163330, uncommitted): ci.yml permissions, dup
      `_parse_date`
- [x] codex dedup key 64→256 chars + env override + system-noise filter
- [x] SUMMARY.md + per-repo reports + handoff packet
- [x] memory rule `explain-tradeoffs-and-recommend` extended with
      dependency/consequence mapping ("что на что влияет")
