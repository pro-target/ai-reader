# Migration from `ai-local-reader`

The `ai-local-reader` skill (`~/.agents/skills/ai-local-reader/`) and
the `ai-reader` package share goals but are implemented differently.
This guide covers three scenarios:

1. **You use the skill scripts directly** — they still work.
2. **You depend on the skill's internal API** — switch to the package.
3. **You want to remove the skill entirely** — how to clean up.

## 1. Scripts still work as wrappers

The two main entry points — `get_latest_context.py` and
`agent-audit.py` — are **drop-in replacements** over the new
`ai-reader` CLI. Their public CLI surface (arguments, stdout shape)
is unchanged. You don't have to migrate.

Example — old vs new, same arguments:

```bash
# old
python ~/.agents/skills/ai-local-reader/scripts/get_latest_context.py \
    --agent claude --days 7

# new
ai-reader list --agent claude
# then format/parse with `jq` or pipe through the legacy wrapper
```

If your tooling shells out to the script, you don't need to do
anything — `bash install.sh` installs the package and the wrappers
keep working.

## 2. Migrating internal API calls

The skill's internal modules (e.g. `parsers/claude.py`) were thin
wrappers over filesystem reads. They have been replaced by:

| Old (skill) | New (package) |
|---|---|
| `from ai_local_reader.parsers.claude import list_sessions` | `from ai_reader.parsers import claude; claude.list_sessions()` |
| `Session(uuid, agent, title, date, path, n)` | `ai_reader.parsers.models.Session` — same shape, but `message_count` instead of `n`, plus `parent_uuid` and `extra` |
| Hand-rolled `is_subagent()` checks | `ai_reader.access.detector.EnvDetector().is_subagent()` |
| `Read` of session files in agent code | MCP tool call: `mcp.call_tool("read_session", {"uuid": ..., "agent": ...})` |

Quick port example:

```python
# before
from ai_local_reader.parsers import claude
sessions = claude.list_sessions()

# after
from ai_reader.parsers import claude
sessions = claude.list_sessions()  # same signature
```

The function signatures are stable across 0.1.x. See
[docs/parsers.md](./parsers.md) for the full parser API.

## 3. Removing the legacy skill (optional)

If you no longer want the `ai-local-reader` skill:

```bash
# remove the skill directory
rm -rf ~/.agents/skills/ai-local-reader

# verify nothing imports it
grep -rn "ai_local_reader" ~/.agents/ || echo "no references"
```

The skill is **not** a hard dependency of `ai-reader`. The package
uses its own parsers; the skill was the seed.

## Compatibility matrix

| ai-reader | ai-local-reader | Status |
|---|---|---|
| 0.1.x | any | Skill scripts continue to work as wrappers |
| 0.2.x | any | Same — wrappers are updated for 0.2 API |
| 1.0+ | any | Skill may be marked deprecated; no removal planned |

## When **not** to migrate

- If your agent only does occasional session reads and you don't
  care about the access guard, the skill is fine. Stay where you are.
- If you need the access guard (most multi-agent setups), install
  the package. The skill has no guard.
