# Cherry-pick report: balaka/bro (PR2 source)

**Date:** 2026-06-21
**Source:** https://github.com/balaka/bro
**License:** MIT
**Verdict:** cherry-pick

## TL;DR

Pure Claude Code skill (markdown-only, no executable code). Writes
per-repo 3-tier memory (`_principles/_thread/daily`) with UUID-postfixed
tags; survives `/compact`. Two patterns adapted into `ai-reader` PR2:
title-resolution priority chain + `summarize_task` heuristic for
fixing junk titles on "ok/thanks/yes" tails.

## Adopted in PR2

- **Title priority chain** — `customTitle > aiTitle > firstUserMsg > chat-HHMM`.
  Source: `bro/SKILL.md:275-280`. Wired into `parsers/claude.py`
  `extract_title()` (public) and `_resolve_title()` (private).
- **`summarize_task` walk-back** — when last user message is stopword-only
  ("thanks", "ok", "yes"), walk back to prior non-trivial message.
  Source: `transcript.py:165-185` of jmm2020/claude-session-recorder
  (sister repo, same family of patterns). Implemented in
  `parsers/claude_derive.py:summarize_task()`.

## Rejected

- 3-tier memory layout — write-side, conflicts with read-only design.
- 6-hex UUID postfix — 1/16M collision risk; ai-reader keeps full UUID.
- "Visible storage at cwd root" UX opinion — not portable.
- Marketing/ceremony ("YOUR SOUL IS MINE") — flavor, not substance.

## License

MIT. Compatible with ai-reader (MIT). No copy-paste performed;
patterns reimplemented in idiomatic Python.
