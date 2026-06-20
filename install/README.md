# Install `ai-reader`

`ai-reader` ships with an idempotent installer. It works in three modes and
patches the four agent configs (Claude, Codex, OpenCode, Antigravity) in place.

## Quick start

```bash
git clone https://github.com/pro-target/ai-reader.git ~/dev/ai-reader
cd ~/dev/ai-reader
bash install.sh
```

If `sudo -n` works (NOPASSWD) the installer prefers `/opt/ai-reader/`. Otherwise
it falls back to `~/.local/share/ai-reader/`. Override with the first argument
or `INSTALL_MODE=...`.

## Modes

| Mode     | Install dir                       | Binaries                              | Needs sudo |
|----------|-----------------------------------|---------------------------------------|------------|
| `opt`    | `/opt/ai-reader/`                 | `/opt/ai-reader/.venv/bin/ai-reader*` | yes        |
| `user`   | `~/.local/share/ai-reader/`       | `~/.local/share/ai-reader/.venv/bin/` | no         |
| `auto`   | (default — picks `opt` or `user`) |                                       | maybe      |

In both modes, two symlinks land in `~/.local/bin/` (so `ai-reader` is on
`$PATH` for the current user):

- `~/.local/bin/ai-reader`      → entry point in venv
- `~/.local/bin/ai-reader-mcp`  → MCP server entry point in venv

If `python3 -m venv` is unavailable (e.g. on systems without
`python3-venv`), the installer falls back to
`pip install --break-system-packages` and places entry points in
`~/.local/bin/` directly.

## What gets patched

`install/agent-configs.sh` adds an `ai-reader` entry to the MCP config of
each installed agent. Existing entries are preserved untouched.

| Agent       | Config file                                    | Format | Key added               |
|-------------|------------------------------------------------|--------|-------------------------|
| Claude      | `~/.claude/settings.json`                      | JSON   | `mcpServers["ai-reader"]` |
| Codex       | `~/.codex/config.toml`                         | TOML   | `[mcp_servers.ai-reader]` |
| OpenCode    | `~/.config/opencode/opencode.jsonc`            | JSONC  | `mcp["ai-reader"]`        |
| Antigravity | `~/.gemini/antigravity/mcp_config.json`        | JSON   | `mcpServers["ai-reader"]` |

Re-running `bash install.sh` is safe — already-present entries are detected
and skipped.

## Verify

```bash
which ai-reader ai-reader-mcp
ai-reader --version
ai-reader list --agent claude | head -5
```

And confirm the four configs are intact:

```bash
jq  '.mcpServers | keys'                          ~/.claude/settings.json
grep 'mcp_servers.ai-reader'                      ~/.codex/config.toml
grep 'ai-reader'                                  ~/.config/opencode/opencode.jsonc
jq  '.mcpServers | keys'                          ~/.gemini/antigravity/mcp_config.json
```

## Uninstall

```bash
bash uninstall.sh           # remove symlinks + 4 config entries
bash uninstall.sh --purge   # also remove /opt/ai-reader or ~/.local/share/ai-reader
```

The source repo at `~/dev/ai-reader/` is never touched.

## Troubleshooting

**`sudo` keeps prompting.** Set `INSTALL_MODE=user` (no sudo needed):

```bash
INSTALL_MODE=user bash install.sh
```

**`python3 -m venv` fails with "ensurepip not available".** Install
`python3-venv` (or the matching `python3.X-venv` package), or accept the
`--break-system-packages` fallback the installer uses automatically.

**A config file is missing.** The installer skips that agent and prints
a warning. It does not abort the run.

**Re-install after a config rewrite.** Just re-run `bash install.sh` — it
detects existing entries and reuses the venv.

## Files

| Path                          | Purpose                                              |
|-------------------------------|------------------------------------------------------|
| `install.sh`                  | Main installer                                       |
| `install/agent-configs.sh`    | Patches 4 agent MCP configs (called by install.sh)  |
| `install/README.md`           | This file                                            |
| `uninstall.sh`                | Reverse of install                                   |
