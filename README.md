# tbcli — Thunderbird CLI Bridge

**A command-line interface to your Thunderbird mailbox — built to be driven by an AI agent.** It bridges the gap when a Google Workspace (or other) admin blocks App Passwords and third-party OAuth, so there is no credential to script with: Thunderbird already holds your authenticated session, and this exposes it to the terminal as a clean, JSON-first, **self-describing** tool — so an agent (or you) can read, search, send, organize, and script your mail without ever touching a credential. The interface was designed agent-first: every command emits JSON, and `tbcli commands` hands an LLM a machine-readable contract of the whole tool.

> **What it demonstrates:** end-to-end systems plumbing across four runtimes in one small project — a Python CLI, a long-lived Python native-messaging host, a Thunderbird MV3 WebExtension, and a localhost TCP bridge between them — plus a pragmatic "auth lives in the app, not in my code" security posture and a JSON-first, agent-friendly interface design. It is a focused integration artifact, built to solve a real blocker.

## Why it exists

Some IT environments disable App Passwords and refuse third-party OAuth clients, which makes the usual `imaplib`/SMTP scripting route impossible — there is simply no credential to script with. Thunderbird, however, is already logged in. `tbcli` reuses that live session through Thunderbird's own WebExtension APIs, so the terminal gets mail access with **no passwords, tokens, or OAuth flows stored anywhere in this project**. The auth boundary stays entirely inside Thunderbird.

## Architecture

```
  tbcli  ──TCP(127.0.0.1:47200)──►  Native Host (Python)  ──stdin/stdout──►  TB Extension  ──WebExtension APIs──►  Mail
 (CLI)                              (long-lived bridge)     (native messaging)  (MV3 background)
```

Three moving parts, four runtime boundaries:

1. **`tbcli` (CLI)** — an `argparse` command tree. Serializes each command to JSON and sends it over a localhost TCP socket. One request/response per connection. (`tbcli/`)
2. **Native messaging host** — a small Python process Thunderbird launches. It runs a TCP server on `127.0.0.1:47200`, forwards each incoming request to the extension over the native-messaging stdin/stdout framing (4-byte little-endian length prefix + JSON), and routes the reply back to the waiting TCP client. (`native-host/`)
3. **WebExtension** — an MV3 Thunderbird add-on. Its background script dispatches each command to the relevant `browser.messages` / `browser.folders` / `browser.accounts` / `browser.compose` API and returns the result. (`extension/`)

The localhost TCP hop is what lets *any* terminal process (or agent) talk to a single shared, already-running native host, rather than each invocation spawning its own.

## Quick start

```bash
# 1. Install the CLI
cd thunderbird-cli-bridge
pip install -e .

# 2. Register the native messaging host (writes an absolute path into the
#    host manifest and an HKCU registry key so Thunderbird can find it)
tbcli setup

# 3. Install the extension in Thunderbird
#    Add-ons Manager  >  gear icon  >  "Install Add-on From File…"
#    Select the extension/ folder (or the packaged tbcli-bridge.xpi)

# 4. Restart Thunderbird, then verify the bridge is live:
tbcli status
tbcli accounts
tbcli list --limit 5 --pretty
```

> **Platform note:** `tbcli setup` is currently **Windows-only** — it registers the host via `winreg` under `HKCU\Software\Mozilla\NativeMessagingHosts`. macOS/Linux use Mozilla's per-user native-messaging-host JSON directories instead; wiring that path is a known gap (see **Status**). The CLI, host, and extension logic are otherwise platform-neutral.

## Commands

```
tbcli status                            tbcli accounts
tbcli folders [--account X]             tbcli list [--folder F] [--unread] [--limit N] [filters]
tbcli read ID [--html]                  tbcli search QUERY [--folder F] [--limit N] [filters]
tbcli send --to X --subject S --body T  tbcli reply ID --body T [--all]
tbcli forward ID --to X                 tbcli move ID FOLDER
tbcli delete ID [--permanent]           tbcli flag ID
tbcli mark-read ID                      tbcli attachments ID
tbcli attachment ID PART [-o DIR]       tbcli setup
tbcli commands                          tbcli ask "..." [--model M] [--dry-run]
```

Shared filters on `list` / `search`: `--unread`, `--flagged`, `--after YYYY-MM-DD`, `--before YYYY-MM-DD`, `--from`, `--to`, `--subject`, `--body` (server-side via Thunderbird's `messages.query`).

### Output: JSON-first by design

Every command prints JSON by default; add `--pretty` for aligned human tables. That makes the tool trivially scriptable:

```bash
tbcli list --unread | jq '.[].subject'
tbcli list --after 2026-03-01 --from someone@example.com --limit 10 --pretty
echo "body from stdin" | tbcli send --to x@example.com -s "hi" --body-file -
```

### Agent-oriented surface

Two commands lean into LLM/agent use:

- **`tbcli commands`** emits a machine-readable JSON reference of the whole command tree (descriptions, options, return shapes, examples, workflow tips) — a self-describing contract an agent can read to learn the tool.
- **`tbcli ask "..."`** is an experimental wrapper that hands that reference to the Claude Code CLI as a system prompt and lets it drive `tbcli` over Bash to satisfy a natural-language request. **Status: experimental** — it shells out to a locally installed `claude` binary; see **Status** below.

## Status (honest)

| Area | State |
|---|---|
| Core mail ops (status, accounts, folders, list, read, search, move, delete, flag, mark-read) | **Working** |
| Compose ops (send, reply, forward) | **Working** — sends immediately (`sendNow`); no draft/confirm step |
| Attachments (list + download by part) | **Working** |
| Server-side filtering via `messages.query` | **Working** |
| `tbcli setup` host registration | **Working on Windows only** (registry via `winreg`); macOS/Linux path **not yet implemented** |
| `tbcli ask` (NL via Claude Code) | **Experimental** — depends on a locally installed `claude` CLI; not part of the core bridge |
| Tests | **None checked in** — verified by manual exercise against a live Thunderbird |
| Packaging | Installable (`pip install -e .`), `tbcli` console-script entry point, v1.0.0 |

### Known limitations / rough edges

- **No authentication on the TCP port.** The host listens on `127.0.0.1:47200` with no auth, so any local process can drive your mailbox while the host is running. Acceptable for a single-user workstation; would need a token/handshake before any multi-user or untrusted-local context. (Flagged as the first thing to harden.)
- **Single-user, single-host assumption** — fixed port, single lock file at `~/.tbcli_host.lock`.
- **Message IDs are session-scoped integers** from Thunderbird and do not persist across restarts; treat them as ephemeral within a `list`→`read`→act chain.
- Sends are immediate — there is intentionally no "save to Drafts" mode yet.

## Repo layout

```
tbcli/            Python CLI package (argparse tree, TCP client, output formatting)
native-host/      Native messaging host: TCP server <-> TB native-messaging stdio bridge
extension/        Thunderbird MV3 WebExtension (manifest + background dispatcher)
docs/             Condensed Thunderbird WebExtension API reference used while building
pyproject.toml    Packaging / console-script entry point
```

## Security model

- **No credentials in this repo.** All mail authentication lives inside Thunderbird; `tbcli` never sees a password, token, or OAuth grant. That is the entire point of the design.
- The native host binds to **loopback only** (`127.0.0.1`). It does not accept remote connections.
- `tbcli setup` writes a machine-specific absolute path into `native-host/tbcli_host.json` and an `HKCU` registry value. The checked-in manifest ships with a **placeholder path** — running `setup` rewrites it for your machine.

## License

MIT — see [LICENSE](LICENSE).

---

*Built by James J. Davison as a focused integration tool to unblock terminal/agent mail access in a locked-down auth environment. Original work; not a fork.*
