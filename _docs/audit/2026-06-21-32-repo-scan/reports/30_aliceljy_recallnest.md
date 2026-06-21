# Cherry-pick report: AliceLJY/recallnest (PR1 source)

**Date:** 2026-06-21
**Source:** https://github.com/AliceLJY/recallnest
**License:** MIT
**Verdict:** cherry-pick

## TL;DR

MCP-native local-first memory/distillation layer on top of parsed
AI agent sessions (Claude/Codex/Gemini). TS monorepo, ~87K LOC.
Provides one rare data-point on Codex `event_msg.user_message` payload
shape — the only witness we found, since OpenAI does not publish a spec
for this record type. Two patterns adapted into ai-reader PR1:
event_msg extraction + archived_sessions/ scanning.

## Adopted in PR1

- **`event_msg.user_message` extraction** — `payload.type == "user_message"`
  → `payload.message` (string) → user-role `Message`. Source:
  `recallnest/src/ingest.ts:996`. Implemented in
  `parsers/codex.py:_extract_messages_from_rollout()` (lines 353+).
- **`~/.codex/archived_sessions/` scanning** — sibling of
  `~/.codex/sessions/`. Source: `recallnest/src/ingest.ts:1029-1060`.
  Implemented in `parsers/codex.py:_resolve_base_dir()` returning
  `List[Path]` instead of single `Path`.

## Improvements over recallnest

- **Dedup key** — recallnest uses `length > 10` filter + last-turn text
  comparison (fragile: misses duplicates that differ in tail). ai-reader
  uses seen-set keyed on first `$AI_READER_DEDUP_KEY_LEN` chars
  (default 256, env-configurable). Catches duplicates that differ in
  the middle/latter portion of the prompt.
- **System-noise filter** — ai-reader applies `_is_system_noise()`
  to event_msg payloads. Skips `<command-message>`, `<system-reminder>`,
  `<permissions>`, `## Apps` prefixes that Codex injects.
- **Strict glob** — recallnest uses `*.jsonl` (catches garbage).
  ai-reader keeps `rollout-*.jsonl` (canonical Codex naming).
- **Version-pinning comment** — `# verified against Codex CLI 2026-05
  snapshot; recheck on schema change`. Mandatory per project rules.

## Open gaps in PR1

- Dedup key 256 chars: chosen as balance between collision safety
  and memory. User can raise via `AI_READER_DEDUP_KEY_LEN=1024`.
- `_is_system_noise` regex list is small (4 patterns). If Codex adds
  new system prefixes, they leak through until list is extended.
- `archived_sessions/` content (e.g. encryption, compression) not
  probed on real installations — only synthetic fixture tested.

## License

MIT. Compatible with ai-reader (MIT). No copy-paste performed;
patterns reimplemented in idiomatic Python with stricter semantics.
