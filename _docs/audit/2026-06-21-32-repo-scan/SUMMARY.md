# Repo scan summary: 32 candidate repos for ai-reader

**Date:** 2026-06-21
**Method:** 32 sequential `general` subagents (1 per repo), each: webfetch metadata → git clone --depth 1 to /tmp → read → compare to ai-reader → cleanup.
**Comparison goal:** what to take / improve in `/home/dmitrii/dev/ai-reader`.
**Injection-safety:** hardened prompts (subagent #3 onwards) treat repo content as untrusted data.

## Verdict distribution

| Verdict | Count | Notes |
|---|---|---|
| cherry-pick | 10 | Real patterns/code we can adopt |
| reference-only | 21 | Patterns only (license / no-code / out-of-scope) |
| avoid | 1 | No code, no license, single commit |
| adopt | 0 | None reached the bar |

## Cherry-pick set (10 repos → 8 implemented PRs + 1 deferred)

| # | Repo | License | Verdict | Top pick | Implemented? |
|---|---|---|---|---|---|
| 1 | balaka/bro | MIT | cherry-pick | title priority chain (customTitle>aiTitle>firstUserMsg>chat-HHMM) | PR2 |
| 8 | Bunz80/claude-project-rounds | MIT | cherry-pick | `exporters/rounds.py` for `work/CHANGELOG.md` format | PR7a |
| 12 | ucsandman/context-handoff-bundle | MIT | cherry-pick | ambiguous-query → list fallback in `read_session` | PR5 |
| 13 | sandeepbollavaram/Kairo | MIT | cherry-pick | JSONL corruption quarantine seam | PR4 |
| 17 | As-The-Geek-Learns/cortex | MIT | cherry-pick | incremental byte-offset reader for Claude | PR3 |
| 18 | sjh6229/agent-continuity | MIT | cherry-pick | privacy-scan regex set (175 LOC) | not yet (next session) |
| 22 | jmm2020/claude-session-recorder | MIT | cherry-pick | `claude_derive.py` (extract_decisions + summarize_task) | PR2 |
| 26 | jovesun-lab/whetstone | MIT | cherry-pick | template+validator split for session_note | PR7b |
| 28 | hotalexnet/agent-checkpoint | MIT | cherry-pick | env-var agent detection cascade | PR6 |
| 30 | AliceLJY/recallnest | MIT | cherry-pick | codex event_msg.user_message + archived_sessions/ | PR1 |

## Reference-only set (21 repos)

| # | Repo | License | Why reference-only |
|---|---|---|---|
| 2 | ramonclaudio/handoff | MIT | redirect stub to monorepo, zero code |
| 3 | mrjessek/shang-tsung | MIT | write-side persistence, read-side ortho |
| 4 | r-design-j/codex-session-continuity-skill | **UNLICENSED** | reimplement patterns, never copy |
| 5 | torifo/skills-context-snapshot-clear | no LICENSE | prose-only |
| 6 | hoshiyomiX/stellar-trails | no LICENSE | z.ai platform lock-in |
| 7 | saisumantatgit/Agent-Scribe | MIT | zero code, bash+md only |
| 9 | status-os/status-os | MIT | device-mesh problem, not sessions |
| 10 | jopre0502/claude-persist | MIT | Claude-only plugin, no parser code |
| 11 | asyu17/Agent-Orchestra | no LICENSE | alpha, 50.5K LOC, write-side |
| 14 | clairetech-*/bootstrap_session_capsule_protocol | no LICENSE | **avoid** — single-commit marketing README |
| 15 | jungjaehoon-lifegamez/claude-plugins | MIT | MAMA write-side, decision graph |
| 16 | richenyu/codex-smart-project-memory | MIT | 97% marketing copy |
| 19 | shawn-web/pending-issues | MIT | write-side ledger, no parsing |
| 20 | chris-patenaude/session-continuity-protocal | CC BY 4.0 | docs only |
| 21 | sara-star-quant/presence | Apache-2.0 | write-side hooks, no parsers |
| 23 | lwalden/AIAgentMinder | MIT | single-runtime, no parsers |
| 24 | AgileSmagile/smagile-agentic-kanban-blueprint | **CC-BY-SA-4.0** | ShareAlike — concept only |
| 25 | jonny981/claude-tandem | MIT | bash+state, ephemeral |
| 27 | jungjaehoon-lifegamez/MAMA | MIT | same as #15 (monorepo slice) |
| 29 | Storybloq/plugin-archive | **PolyForm-NC** | concepts only |
| 31 | neverinfamous/memory-journal-mcp | MIT | 12.5K TS surface, project memory |
| 32 | Storybloq/storybloq | **PolyForm-NC** | concepts only |

## Deferred items (FTS5 + audit ledger)

| Item | Source | +/- | Recommendation |
|---|---|---|---|
| FTS5 hybrid search | cortex (#17) | +: real need, stdlib / -: sidecar cache = write-side | **DEFER** until title-substring search complaints |
| Hash-chained audit ledger | status-os (#9) | +: compliance / -: overkill, write-side | **DEFER** until enterprise/regulated use |

Trigger condition for both: explicit user request or first use-case in a regulated environment.

## Files in this scan

- `SUMMARY.md` (this file)
- `reports/` (per-repo detailed reports — to be populated per-cherry-pick)
