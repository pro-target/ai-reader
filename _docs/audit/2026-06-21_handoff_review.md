# Repo audit: ramonclaudio/handoff

**Date:** 2026-06-21
**Target:** https://github.com/ramonclaudio/handoff
**Verdict:** reference-only

## TL;DR

`handoff` is a **Claude Code plugin** that **writes** session-continuity state
into a project's `.handoff/` directory using an SBAR-shaped HANDOFF.md +
auto/curated-split CONTEXT.md, with severity 🟢/🟡/🔴 and a
"file:line resume" discipline. Skill-first architecture: one ~600-line
`SKILL.md` is the source of truth, a thin `agents/handoff.md` dispatches
intent, and four bash hooks (`SessionStart`, `SessionEnd`, `SubagentStart`,
`SubagentStop`) log subagent activity to `.handoff/.subagents.log`.

**The repo is a redirect stub.** The README points at
`ramonclaudio/skills` monorepo (commit `da98dfe` "docs: redirect to
ramonclaudio/skills monorepo", 2026-01-31). All active development lives
elsewhere; this clone is frozen at v1.2.0 (2026-01-24).

`ai-reader` is the **inverse** surface — read-only multi-agent parser
exposing Claude/Codex/OpenCode/Antigravity sessions through CLI + MCP +
Python pkg. Zero code overlap (different language, different dir, different
direction). Useful design patterns to reference; no code to import. License
compatible (MIT ↔ MIT).

---

## Snapshot

| Field | Value |
|---|---|
| Repo | https://github.com/ramonclaudio/handoff |
| Purpose | Session continuity for Claude Code (write structured handoff to `.handoff/`) |
| Version | v1.2.0 (2026-01-24) |
| Last commit | `da98dfe` 2026-01-31 — "docs: redirect to ramonclaudio/skills monorepo" |
| Author | Ray (ramonclaudio) |
| License | MIT (2026) — **compatible with ai-reader (MIT)** |
| Status | **Migrated** — active work is at `ramonclaudio/skills`; this repo is a redirect stub |
| Files (excl. `.git`/logo) | 10 source files |
| Total source LOC | ~860 (excl. binary logo) |
| Language split | markdown 85% (~750 LOC) + bash 6% (~53 LOC) + json 6% (~54 LOC) |
| Stars | not resolved (no badge in README; gh auth + webfetch blocked in this session) |
| Repo size | 4 KB `.github/assets/logo.png` (binary) dominates `find`; otherwise tiny |

## Architecture

- **Form factor:** Claude Code **plugin** (not a Python pkg, not a CLI, not an
  MCP server). Distributed via `.claude-plugin/{plugin,marketplace}.json`.
  Install path: `/plugin marketplace add ramonclaudio/skills && /plugin
  install handoff@skills`.
- **Skill-first** design (CHANGELOG 1.0.0 — explicit "skill as source of
  truth" choice; replaced earlier 4-5 background-agent architecture that
  cost ~55k tokens per START):
  ```
  handoff/
  ├── .claude-plugin/{plugin,marketplace}.json  ← distribution manifest
  ├── agents/handoff.md          ← thin dispatcher: maps "start|end|init" → /handoff <arg>
  ├── skills/handoff/SKILL.md    ← ~600 LOC prompt; full implementation
  ├── hooks/hooks.json           ← 4 event hooks
  └── scripts/{session,subagent}-{start,end,stop}.sh
  ```
- **Three actions** in `SKILL.md` (driven by `$ARGUMENTS`):
  1. `init` — scaffold `.handoff/{sessions,CURRENT}` and write boilerplate
     CONTEXT.md (auto/curated split) + HANDOFF.md (severity placeholder).
  2. `start` — 6-phase read-back: timeline → validate CONTEXT → drift
     detection (paths in `## Structure` vs actual `test -e`) → gather
     state (git, PRs, Linear issues, subagent log) → assess health →
     output read-back panel.
  3. `end` — 9-phase archive: snapshot HANDOFF.md to
     `.handoff/sessions/${CLAUDE_SESSION_ID}.md` → run health (build/test/
     lint) → capture git → regenerate auto sections of CONTEXT.md →
     analyze session (severity inference, done/failed/blockers/watch-outs/
     resume) → validate required fields → create persistent TaskCreate
     with `metadata: {handoff: true, session: <id>}` → confirm panel.
- **CONTEXT.md has two section classes** marked by HTML comments:
  - `<!-- AUTO: Regenerated on END -->` → `## Structure`, `## Invocation`
  - `<!-- CURATED: Edit manually -->` → `## Stack`, `## Patterns`, `## What Never Works`
  This split is the **load-bearing idea** of the whole plugin — auto parts
  get machine-rewritten safely, curated parts stay human-owned.
- **HANDOFF.md schema** (SBAR-derived): severity (🔴/🟡/🟢) → health
  (build/tests/lint) → git → done (concrete items) → failed (Tried/Error/
  Why/Need) → blockers → watch-outs → resume (next + files + context,
  **must include specific file:line**).
- **Subagent tracking:** `SubagentStart`/`SubagentStop` hooks append
  `TIMESTAMP | START/STOP | AGENT_TYPE` lines to `.handoff/.subagents.log`.
  Cleared on END. START surfaces last-20 lines of the log in the read-back.
- **Session ID as archive key (v1.1.0):** `${CLAUDE_SESSION_ID}.md` replaces
  timestamp naming — fixes minute-collision, enables direct correlation
  with Claude transcripts.
- **Task system (v1.2.0):** replaced deprecated `TodoWrite` with
  `TaskCreate`/`TaskList`/`TaskUpdate`; cross-session persistence lives in
  `~/.claude/tasks`, with `handoff: true` metadata as the marker.
- **Hooks (4):**
  | Event | Script | Action |
  |---|---|---|
  | `SessionStart` | `session-start.sh` | Detect `.handoff/HANDOFF.md`, echo session id, suggest `/handoff start\|init` |
  | `SessionEnd` | `session-end.sh` | One-line reminder: run `/handoff end` |
  | `SubagentStart` | `subagent-start.sh` | Log `TIMESTAMP \| START \| <agent_type>` to `.subagents.log` |
  | `SubagentStop` | `subagent-stop.sh` | Log `TIMESTAMP \| STOP \| <agent_type>` to `.subagents.log` |
- **External integrations:** `gh` for PR activity, `git` for state, optional
  `mcp__plugin_linear_linear__list_issues` for issue surfacing. No external
  HTTP, no auth tokens, no DB.
- **Allowed tools (in skill):** `Bash(git:*)`, `Bash(gh:*)`, `Bash(npm:*)`,
  `Bash(bun:*)`, `Bash(pnpm:*)`, `Bash(yarn:*)`, `Bash(mkdir:*)`, `Bash(cp:*)`,
  `Bash(rm:*)`, `Bash(date:*)`, `Bash(ls:*)`, `Bash(test:*)`, `Bash(wc:*)`,
  `Read`, `Write`, `Edit`, `Glob`, `Grep`, `TaskCreate`, `TaskUpdate`,
  `TaskGet`, `TaskList`, `mcp__plugin_linear_linear__list_issues`.
  Note: broad `Bash(<pkg>:*)` wildcards are a security smell (full namespace
  access to package managers), but in-skill and not a runtime risk to
  ai-reader.
- **Anti-patterns list** (SKILL.md §Anti-Patterns) is itself worth
  reading: don't skip health checks, no vague resume, no omitted root
  cause, no lying about severity, no stale CONTEXT.md.

## What it is NOT

- Not a Python package, not a CLI binary, not an MCP server.
- Not multi-agent — Claude Code only (uses `CLAUDE_SESSION_ID`,
  `~/.claude/tasks`, SubagentStart hooks). Codex/OpenCode/Antigravity
  layouts are unknown to it; the plugin.json's `claude-code, codex, cursor`
  keywords are aspirational/aspirational-wrong (no codex support in the
  actual SKILL.md).
- Not a session **reader** — it writes `.handoff/` and reads it back in
  the next session. It does not parse Claude's `~/.claude/projects/*.jsonl`
  transcripts (it has zero parser code).
- Not cross-session search/retrieval — purely a per-project markdown
  write/read cycle.
- Not a published archive — last commit is a redirect, repo is effectively
  frozen. Anyone reading this should treat the v1.2.0 code as a snapshot,
  not a maintained project.

---

## Overlap matrix vs `ai-reader`

| Axis | handoff | ai-reader | Overlap |
|---|---|---|---|
| Direction | **writes** session-continuity state | **reads** session transcripts | inverse surfaces |
| Form factor | Claude Code plugin (skill + agent + hooks) | Python pkg + CLI + MCP server | none |
| Agents supported | Claude Code only (Claude session id, `~/.claude/tasks`, SubagentStart hooks) | Claude, Codex, OpenCode, Antigravity | handoff = 1 of 4 |
| Parsers | none (just `test -e` and `git log`) | `src/ai_reader/parsers/{claude,codex,opencode,antigravity}.py` | none |
| MCP server | none (consumer of Linear MCP only) | yes (`src/ai_reader/mcp_server*.py`) | none |
| Python package | no | yes (`pyproject.toml` + `src/ai_reader/`) | none |
| CLI | no (`/handoff` slash command) | yes (`ai-reader` CLI) | none |
| Storage layout | writes `.handoff/` (cwd-relative) | reads `~/.claude/projects/`, `~/.codex/sessions/`, `~/.local/share/opencode/opencode.db`, `~/.gemini/antigravity/brain/` | **no collision** — disjoint paths |
| Multi-agent | no | yes (4 parsers, unified `Session` projection) | none |
| Memory layer | owns one (markdown in cwd) | none (read-only by design) | none |
| Hooks | 4 bash hooks (Session/Subagent) | none | none |
| Severity model | 🔴 CRITICAL / 🟡 IN PROGRESS / 🟢 READY (handoff severity) | not formalized | **borrow** |
| Failure schema | Tried / Error / Why / Need (4-tuple) | not formalized | **borrow** |
| Auto/curated split | `<!-- AUTO -->` / `<!-- CURATED -->` HTML comments | not used (CONTEXT.md is hand-written) | **borrow as design pattern** |
| Drift detection | file-tree vs CONTEXT.md `## Structure` | not present | **borrow as `ai-reader check-context`** |
| file:line resume discipline | required, validated on END | used informally in our own audit docs | **reinforce** |
| Subagent activity log | `.subagents.log` (TIMESTAMP \| STATE \| AGENT_TYPE) | not parsed (no parser surfaces subagent info) | **gap to fill** |
| Task system persistence | `~/.claude/tasks` + `handoff: true` metadata | n/a | reference only |
| License | MIT | MIT | **compatible** |
| Deps | bash, git, gh, optional Linear MCP | pydantic, mcp, sqlite3 | none shared |
| Status | **archived/redirect** to `ramonclaudio/skills` | active | n/a |

## Compatibility analysis

- **License:** MIT ↔ MIT, fully compatible. If we ever copy a snippet
  (e.g., the severity legend), attribute in source comment.
- **Runtime:** handoff has no Python package, so no version-conflict surface.
- **Storage collision:** none — handoff writes to `.handoff/` (cwd-relative),
  ai-reader reads from agent home dirs. No shared path. If a user
  coincidentally has both installed, the handoff's `## Structure` section
  will *include* ai-reader's source files (which is correct, since they
  are project files).
- **Behavioural risk:** none — handoff only runs as a Claude Code plugin
  inside a Claude Code session, ai-reader is a separate CLI/MCP process.
  They cannot interfere.
- **Maintenance risk:** this repo is a redirect. Any reference design
  patterns should be re-validated against `ramonclaudio/skills` monorepo
  if we ever want to pull new ideas; the v1.2.0 snapshot here may diverge.

---

## Verdict: **reference-only**

Reasons:
1. **Repo is a redirect stub.** The README points at `ramonclaudio/skills`
   and the last commit is "redirect to monorepo". Tracking this URL
   pins us to a frozen snapshot; the live project is elsewhere.
2. **Zero code overlap.** handoff is bash + markdown + 4 hooks;
   ai-reader is a Python parser + MCP server. No import, no extension,
   no shared deps.
3. **Inverse problem domain.** handoff captures *operator* state
   (decisions, resume pointers, gotchas) by *writing*. ai-reader exposes
   raw agent *session logs* by *reading*. They complement but do not
   overlap functionally.
4. **No multi-agent reach.** handoff is Claude-Code-only. Adopting its
   patterns without porting them to Codex/OpenCode/Antigravity would
   regress ai-reader's multi-agent stance.
5. **Write-side is out of contract.** ai-reader is read-only by design
   (Design boundaries in README). The whole handoff model is *write
   markdown files in cwd*; importing the surface would violate the
   read-only contract.
6. **Operator-style design is a reference, not a dependency.** handoff's
   SBAR severity scale, `Tried/Error/Why/Need` failure schema,
   auto/curated section split, file:line resume discipline, and
   drift-detection loop are high-quality patterns worth studying.

---

## What we can take / improve

Tied to concrete `ai-reader` files/modules:

- **SBAR severity scale in `docs/parsers.md` (or a new
  `docs/parser-audit.md`):** 🔴 CRITICAL / 🟡 IN PROGRESS / 🟢 READY
  is a clean, emoji-stable, machine-parseable legend. If we ever add
  an `ai-reader audit <session>` command that surfaces a parser-error
  panel, this is the legend. Drop-in: ~10 lines of markdown.
- **`Tried / Error / Why / Need` failure schema in `src/ai_reader/parsers/
  __init__.py`:** ai-reader's parser errors currently surface as raw
  exception text. Borrow the 4-tuple as a `ParserError` pydantic model
  (or just a docstring convention in `ParserError` subclasses). Keeps
  output grep-friendly for the session-summarizer skill. ~20 LOC.
- **Auto/curated split in our own `CONTEXT.md`:** add `<!-- AUTO -->` /
  `<!-- CURATED -->` HTML-comment markers to `_docs/CONTEXT.md` (the
  ai-reader-internal one, not `/home/dmitrii/dev/ai-reader/CONTEXT.md` —
  different file) so future auto-regenerators know what to overwrite.
  One-time doc edit, no code.
- **Drift detection — add `src/ai_reader/check.py::check_context(path) -> list[Drift]`:**
  handoff's `test -e` against `## Structure` is a 5-line algorithm. We
  could expose it as `ai-reader check-context` for users who keep a
  notes file in their repo. Trivially testable.
- **file:line resume discipline in `_docs/audit/*.md`:** handoff
  validates "Resume has specific file:line" as a required field on
  END. Our existing audit reports already use `file:line` refs (e.g.,
  the bro audit cites `src/ai_reader/parsers/claude.py`); formalize
  this as a `_docs/audit/TEMPLATE.md` heading and add a
  `validate-audit.py` linter that greps for missing `file:line` in
  the `## What we can take` section.
- **Subagent activity — extend `src/ai_reader/parsers/opencode.py` (and
  possibly `claude.py`):** handoff proves that subagent timing is
  valuable session metadata. Our `Session` projection doesn't surface
  subagent events at all. Add `Session.subagents: list[SubagentEvent]`
  with `{ts, kind: "start"|"stop", agent_type}` so the
  session-summarizer skill can render them in the L1 wiki page.
  OpenCode's SQLite may already have this; the parser doesn't read it.
  ~30 LOC + a join.
- **`metadata: {handoff: true}` cross-persistence tag:** ai-reader
  doesn't write anywhere, so this doesn't apply directly. But the
  pattern (a stable tag inside a foreign system's metadata slot) is
  the same shape we use for `ses_` UUIDs in our own audit
  cross-references. Reinforce the convention: any time we annotate
  a third-party artifact, use a stable kebab-case tag and document
  it in `CONTEXT.md`.
- **Severity inference rules (handoff's "build failing → 🔴" etc.)
  as a `docs/audit-severity.md` reference** so the git-log-auditor
  skill has a documented legend for its 15-category report.

## What we should NOT take

- The "write markdown in cwd" model. ai-reader is read-only by design;
  importing a writer surface would conflict with the read-only contract
  and surprise users.
- The `Bash(<pkg>:*)` wildcard allowed-tools. Even inside a skill,
  blanket `npm:*` / `git:*` / `gh:*` access is too permissive for
  any ai-reader MCP tool. We restrict to specific command prefixes.
- The Claude-Code-only assumptions (`CLAUDE_SESSION_ID`,
  `~/.claude/tasks`, SubagentStart/Stop hooks). ai-reader must remain
  agent-agnostic; if a handoff-style feature ever lands in ai-reader
  it has to work for Codex/OpenCode/Antigravity too.
- The redirect-repo habit. This URL is a frozen stub — anyone pinning
  to it will fall behind the live `ramonclaudio/skills` monorepo. We
  should not depend on this repo for any future change tracking.
- The "vague resume point" anti-pattern is something to actively
  defend against in our own audit docs; not a thing to copy.

---

## Receipt

```
path:    /home/dmitrii/dev/ai-reader/_docs/audit/2026-06-21_handoff_review.md
verdict: reference-only
take:    SBAR severity + Tried/Error/Why/Need failure schema for parser audit output
```
