# Repo audit: balaka/bro

**Date:** 2026-06-21
**Target:** https://github.com/balaka/bro
**Verdict:** reference-only

## TL;DR

`bro` is a single-file Claude Desktop/Code slash command (a `SKILL.md` for
`~/.claude/commands/`) that **writes** session-continuity memory into
`{cwd}/bro/` with a three-tier layout (repo-wide `_principles.md`, thread-wide
`_thread.md`, daily `{date}.md`). Tag = slug(chat title) + 6-hex UUID postfix
for collision safety. Includes `/bro migrate` for LLM-driven semantic
conversion of legacy logs.

`ai-reader` is the **inverse** surface — read-only multi-agent parser
exposing sessions from Claude/Codex/OpenCode/Antigravity through CLI + MCP
+ Python pkg. Zero code overlap. Useful design patterns to reference, no code
to import. License compatible (MIT ↔ MIT).

---

## Snapshot

| Field | Value |
|---|---|
| Repo | https://github.com/balaka/bro |
| Purpose | Session continuity memory for Claude Desktop/Code |
| Version | v2.1.1 |
| Last commit | 2026-04-29 21:29 +0300 (`261b231 v2.1.1 — remove hidden .claude/bro/ storage option`) |
| Author | Yuriy Balaka (@balaka) |
| License | MIT (2026) — **compatible with ai-reader (MIT)** |
| Files | 4: `LICENSE`, `README.md`, `SKILL.md`, `bro.md` |
| Total LOC | ~2 700 lines (mostly markdown prose + bash snippets + one python3 heredoc) |
| Language | bash (90%) + python3 (5% inline slugify) + markdown (5%) |
| Stars | unknown (gh auth + webfetch blocked; 0+ from visual badge) |
| Stars badge | present in README, count not resolvable in this session |

## Architecture

- **Form factor:** pure skill file (`bro.md` ≈ 1 170 lines). Claude Desktop
  auto-discovers `~/.claude/commands/bro.md` as slash command `/bro`. No
  executable code; bro.md is a prompt that Claude reads and follows.
- **Storage root:** single canonical visible `{cwd}/bro/` (v2.1.1 removed
  hidden `.claude/bro/` to eliminate invisible-data-loss class of bug).
- **Three-tier layout:**
  ```
  {cwd}/bro/
  ├── .gitignore
  ├── _principles.md        ← repo-lifetime: project descriptor, sticky rules, universal discipline
  └── {tag-with-postfix}/
      ├── .session.json     ← sessionUuid, title history, rename tracking
      ├── _thread.md        ← topic-lifetime: architecture, vocabulary, roadmap
      └── {YYYY-MM-DD}.md   ← session-lifetime: today's state, decisions
  ```
- **Tag derivation** (Step 2 in skill):
  1. `customTitle` (manual UI rename) — highest
  2. `aiTitle` (Claude auto-summary) — second
  3. First user message — fallback
  4. `chat-{HHMM}` — last resort
  → slugify with RU+EN stop-word filter → append `${UUID:0:6}` postfix
- **Session UUID lookup:** PPID walk through `~/.claude/sessions/{pid}.json`,
  fallback to mtime of newest jsonl in `~/.claude/projects/{encoded-cwd}/`.
- **Migration:** `/bro migrate` does LLM-driven semantic classification of
  v1 single-file or v2.0 partial layouts into the three-tier v2.1 form.
  Originals preserved in `{tag}/_legacy-pre-v2.1/`.
- **Markers vocabulary:** `(sticky)`, `(carried since YYYY-MM-DD)`,
  `(reinforced)`, `(new)`, `(refined)`, `(consolidated from N files)`,
  `(чтобы не возвращались)`, `(P0)..(PN)`, `(WAIT: <reason>)`,
  `(parking-lot)`, `(deferred)`, `(YAGNI)`, `(supersedes prior, dated)`,
  `(renamed from {old-tag} since)`, `(observed in tags: ...; carried since)`.
- **Bilingual:** headers English (predictable parsing), operator quotes
  preserved verbatim, RU/EN mix in body, code/paths/URLs unchanged.
- **Self-update:** weekly GitHub poll, atomic swap with major-version bump
  warning, env `BRO_NO_UPDATE_CHECK=1` to disable.

## What it is NOT

- No Python package, no CLI binary, no MCP server, no hooks, no install script.
- No multi-agent support — Claude Desktop/Code only. Codex/OpenCode/Antigravity
  layouts are unknown to it.
- No cross-session search/retrieval API — purely a slash command driven by
  Claude reading/writing markdown files in the same repo.
- No tests (skill is prompt-only).

---

## Overlap matrix vs `ai-reader`

| Axis | bro | ai-reader | Overlap |
|---|---|---|---|
| Direction | **writes** session memory | **reads** session logs | inverse surfaces |
| Agents supported | Claude Desktop/Code | Claude, Codex, OpenCode, Antigravity | bro = 1 of 4 |
| Parsers | none (Claude jsonl grep + jq) | `src/ai_reader/parsers/{claude,codex,opencode,antigravity}.py` | none |
| MCP server | none | yes (`src/ai_reader/mcp_server*.py`) | none |
| Python package | no | yes (`pyproject.toml` + `src/ai_reader/`) | none |
| CLI | no (slash command) | yes (`ai-reader` CLI) | none |
| Storage layout | `{cwd}/bro/` (own) | reads `~/.claude/projects/`, `~/.codex/sessions/`, `~/.local/share/opencode/opencode.db`, `~/.gemini/antigravity/brain/` | none — different scope |
| Multi-agent | no | yes (4 parsers, unified `Session` projection) | none |
| Memory layer | owns one | none (read-only) | none |
| Hooks | none | none | none |
| License | MIT | MIT | **compatible** |
| Deps | `jq`, `python3`, `curl`, `bash` (all stdlib) | pydantic, mcp, sqlite3 | none shared |
| Bilingual | explicit RU+EN rules | not addressed | reference pattern |
| Title-priority chain | customTitle > aiTitle > first-msg | not formalized | **borrow** |
| Slug + UUID-postfix naming | yes (collision-safe per thread) | not used | **borrow** |
| Three-tier memory model | principles/thread/daily | not present | **borrow as design ref** |
| LLM-driven migration | `/bro migrate` | not present | **borrow pattern** |
| Markers vocabulary | 15+ standard markers | not present | **borrow as cross-audit glossary** |

## Compatibility analysis

- **License:** MIT ↔ MIT, fully compatible. If we ever copy a snippet
  (e.g., slugify Python helper), attribute in source comment.
- **Runtime:** bro has no Python package, so no version-conflict surface.
- **Storage collision:** none — bro writes to `{cwd}/bro/`, ai-reader
  reads from agent home dirs. No shared path.
- **Behavioural risk:** none — bro only runs in Claude Desktop slash-command
  context, ai-reader is a separate CLI/MCP process. They cannot interfere.

---

## Verdict: **reference-only**

Reasons:
1. **Zero code overlap.** bro is a prompt-skill; ai-reader is a Python parser.
   Cannot import, cannot extend, cannot share deps.
2. **Inverse problem domain.** bro captures ephemeral interpretation
   (operator state, decisions) by *writing*. ai-reader exposes raw session
   logs by *reading*. They complement but do not overlap functionally.
3. **No multi-agent reach.** bro is Claude-only. ai-reader supports 4 agents.
   Adopting bro's ideas without porting them to Codex/OpenCode/Antigravity
   would regress ai-reader's multi-agent stance.
4. **Operator-style design is a reference, not a dependency.** bro's
   three-tier memory, title-priority chain, UUID-postfix naming, and
   markers vocabulary are high-quality patterns worth studying.

---

## What we can take / improve

Tied to concrete `ai-reader` files/modules:

- **Title-priority chain in `src/ai_reader/parsers/claude.py`:**
  bro's `customTitle > aiTitle > first-message > fallback` chain is the
  canonical Claude-title resolution. ai-reader's Claude parser currently
  surfaces raw session metadata; add a small helper that returns the
  effective title using this priority. Drop-in: ~15 LOC.
- **UUID-postfix as a per-thread identifier in `src/ai_reader/models.py`:
  `Session.uuid_short = uuid[:6]`.** Cheap (computed property), useful for
  the L1 audit-grade summary in the session-summarizer skill (file naming
  `wiki/sessions/<ses_id>.md` mirrors bro's tag-postfix convention).
- **Three-tier memory model — add to `docs/architecture.md` as a "design
  reference: session state tiers".** One paragraph, not a code change. Helps
  future contributors understand why ai-reader doesn't *write* session
  summaries (bro already covers that niche for Claude-only workflows).
- **Markers vocabulary — import the stable subset (`(sticky)`,
  `(carried since)`, `(supersedes)`, `(WAIT:)`) as a `Reference` block in
  `CONTEXT.md`** so the ai-local-reader skill can recognize them when
  cross-auditing sessions that mention bro storage paths.
- **Slugify helper in `src/ai_reader/text.py`:** lift bro's RU+EN
  stop-word filter + first-5-words + 40-char boundary truncation into a
  reusable `slugify(title: str) -> str`. Trivially testable, useful for
  any future title-derived naming.
- **LLM-driven migration pattern → `docs/parsers.md` as a "future-work"
  note.** When ai-reader ever supports re-emitting sessions in a different
  agent's layout, bro's `/bro migrate` is a reference for the
  backup-originals → classify-by-LLM → verify-counts pattern.

## What we should NOT take

- bro's "write a markdown file in cwd" model. ai-reader is read-only by
  design (Design boundaries in README). Adding a writer would conflict with
  the read-only contract and surprise users.
- bro's hidden-storage / custom-path fallback UX. ai-reader has a single
  base-dir contract (`AI_READER_HOME`).
- bro's Claude-only assumptions (PPID walk, `~/.claude/sessions/`,
  `~/.claude/projects/`). ai-reader must remain agent-agnostic.

---

## Receipt

```
path:    /home/dmitrii/dev/ai-reader/_docs/audit/2026-06-21_bro_review.md
verdict: reference-only
take:    title-priority chain + UUID-postfix slugify into parsers/claude.py
```
