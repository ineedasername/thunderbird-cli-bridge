"""tbcli — CLI command tree."""

import argparse
import json
import os
import sys
import winreg

from tbcli.bridge import send_command
from tbcli.output import output


def main():
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--pretty", action="store_true", help="Human-readable output")

    parser = argparse.ArgumentParser(prog="tbcli", description="Thunderbird CLI Bridge", parents=[parent])
    sub = parser.add_subparsers(dest="command")

    # status
    sub.add_parser("status", help="Check connection to Thunderbird", parents=[parent])

    # accounts
    sub.add_parser("accounts", help="List mail accounts", parents=[parent])

    # folders
    p = sub.add_parser("folders", help="List folders", parents=[parent])
    p.add_argument("--account", help="Filter by account name/id")

    # list
    p = sub.add_parser("list", help="List messages", parents=[parent])
    p.add_argument("--folder", default="Inbox", help="Folder name (default: Inbox)")
    p.add_argument("--unread", action="store_true", help="Unread only")
    p.add_argument("--flagged", action="store_true", help="Flagged/starred only")
    p.add_argument("--after", help="Messages after date (YYYY-MM-DD or ISO)")
    p.add_argument("--before", help="Messages before date (YYYY-MM-DD or ISO)")
    p.add_argument("--from", dest="from_addr", help="Filter by sender")
    p.add_argument("--to", dest="to_addr", help="Filter by recipient")
    p.add_argument("--subject", help="Filter by subject")
    p.add_argument("--body", help="Filter by body content")
    p.add_argument("--limit", type=int, default=25, help="Max messages (default: 25)")

    # read
    p = sub.add_parser("read", help="Read a message", parents=[parent])
    p.add_argument("id", help="Message ID")
    p.add_argument("--raw", action="store_true", help="Raw text body")
    p.add_argument("--html", action="store_true", help="HTML body")

    # search
    p = sub.add_parser("search", help="Search messages", parents=[parent])
    p.add_argument("query", help="Search query")
    p.add_argument("--folder", help="Restrict to folder")
    p.add_argument("--unread", action="store_true", help="Unread only")
    p.add_argument("--after", help="Messages after date (YYYY-MM-DD or ISO)")
    p.add_argument("--before", help="Messages before date (YYYY-MM-DD or ISO)")
    p.add_argument("--from", dest="from_addr", help="Filter by sender")
    p.add_argument("--to", dest="to_addr", help="Filter by recipient")
    p.add_argument("--subject", help="Filter by subject")
    p.add_argument("--body", dest="body_filter", help="Filter by body content")
    p.add_argument("--limit", type=int, default=25, help="Max results")

    # move
    p = sub.add_parser("move", help="Move message to folder", parents=[parent])
    p.add_argument("id", help="Message ID")
    p.add_argument("folder", help="Destination folder")

    # delete
    p = sub.add_parser("delete", help="Delete message", parents=[parent])
    p.add_argument("id", help="Message ID")
    p.add_argument("--permanent", action="store_true", help="Permanently delete")

    # flag
    p = sub.add_parser("flag", help="Flag/star a message", parents=[parent])
    p.add_argument("id", help="Message ID")

    # mark-read
    p = sub.add_parser("mark-read", help="Mark message as read", parents=[parent])
    p.add_argument("id", help="Message ID")

    # send
    p = sub.add_parser("send", help="Send a new message", parents=[parent])
    p.add_argument("--to", required=True, action="append", help="Recipient(s)")
    p.add_argument("--cc", action="append", help="CC recipient(s)")
    p.add_argument("--bcc", action="append", help="BCC recipient(s)")
    p.add_argument("--subject", "-s", required=True, help="Subject")
    p.add_argument("--body", "-b", help="Body text")
    p.add_argument("--body-file", help="Read body from file (- for stdin)")
    p.add_argument("--html", action="store_true", help="Send as HTML")

    # reply
    p = sub.add_parser("reply", help="Reply to a message", parents=[parent])
    p.add_argument("id", help="Message ID")
    p.add_argument("--body", "-b", help="Reply body")
    p.add_argument("--body-file", help="Read body from file (- for stdin)")
    p.add_argument("--all", action="store_true", help="Reply to all")
    p.add_argument("--html", action="store_true", help="Send as HTML")

    # forward
    p = sub.add_parser("forward", help="Forward a message", parents=[parent])
    p.add_argument("id", help="Message ID")
    p.add_argument("--to", required=True, action="append", help="Recipient(s)")

    # attachments
    p = sub.add_parser("attachments", help="List attachments", parents=[parent])
    p.add_argument("id", help="Message ID")

    # attachment
    p = sub.add_parser("attachment", help="Download attachment", parents=[parent])
    p.add_argument("id", help="Message ID")
    p.add_argument("part", help="Part name")
    p.add_argument("-o", "--output-dir", default=".", help="Output directory")

    # setup
    sub.add_parser("setup", help="Register native host with Thunderbird", parents=[parent])

    # commands (machine-readable command reference for LLM/agent use)
    sub.add_parser("commands", help="Print machine-readable command reference (JSON)", parents=[parent])

    # ask (natural language via Claude)
    p = sub.add_parser("ask", help="Natural language email task via Claude", parents=[parent])
    p.add_argument("prompt", nargs="+", help="What you want to do with your email")
    p.add_argument("--model", default="sonnet", help="Claude model (default: sonnet)")
    p.add_argument("--dry-run", action="store_true", help="Show the prompt that would be sent")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Resolve body from --body-file if needed
    if hasattr(args, "body_file") and args.body_file:
        if args.body_file == "-":
            args.body = sys.stdin.read()
        else:
            with open(args.body_file) as f:
                args.body = f.read()

    handler = COMMANDS.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


def cmd_status(args):
    data = send_command("status")
    output(data, args.pretty)


def cmd_accounts(args):
    data = send_command("accounts")
    output(data, args.pretty)


def cmd_folders(args):
    cmd_args = {}
    if args.account:
        cmd_args["account"] = args.account
    data = send_command("folders", cmd_args)
    if args.pretty:
        for acct in data:
            print(f"\n  {acct['account']} ({acct['accountId']})")
            for f in acct["folders"]:
                use = ",".join(f.get("specialUse", [])) or "-"
                print(f"    {use:12s}  {f['path']}")
    else:
        output(data)


def cmd_list(args):
    cmd_args = {
        "folder": args.folder,
        "limit": args.limit,
    }
    if args.unread:
        cmd_args["unread"] = True
    if args.flagged:
        cmd_args["flagged"] = True
    if args.after:
        cmd_args["after"] = args.after
    if args.before:
        cmd_args["before"] = args.before
    if args.from_addr:
        cmd_args["from"] = args.from_addr
    if args.to_addr:
        cmd_args["to"] = args.to_addr
    if args.subject:
        cmd_args["subject"] = args.subject
    if args.body:
        cmd_args["body"] = args.body
    data = send_command("list", cmd_args)
    output(data, args.pretty)


def cmd_read(args):
    fmt = "html" if args.html else "text"
    data = send_command("read", {"id": args.id, "format": fmt})
    if args.pretty:
        print(f"From:    {data['from']}")
        print(f"To:      {', '.join(data['to']) if data['to'] else ''}")
        print(f"Date:    {data['date']}")
        print(f"Subject: {data['subject']}")
        print("-" * 60)
        print(data.get("body", ""))
    else:
        output(data)


def cmd_search(args):
    cmd_args = {"query": args.query, "limit": args.limit}
    if args.folder:
        cmd_args["folder"] = args.folder
    if args.unread:
        cmd_args["unread"] = True
    if args.after:
        cmd_args["after"] = args.after
    if args.before:
        cmd_args["before"] = args.before
    if args.from_addr:
        cmd_args["from"] = args.from_addr
    if args.to_addr:
        cmd_args["to"] = args.to_addr
    if args.subject:
        cmd_args["subject"] = args.subject
    if args.body_filter:
        cmd_args["body"] = args.body_filter
    data = send_command("search", cmd_args, timeout=30)
    output(data, args.pretty)


def cmd_move(args):
    data = send_command("move", {"id": args.id, "folder": args.folder})
    output(data, args.pretty)


def cmd_delete(args):
    data = send_command("delete", {"id": args.id, "permanent": args.permanent})
    output(data, args.pretty)


def cmd_flag(args):
    data = send_command("flag", {"id": args.id})
    output(data, args.pretty)


def cmd_mark_read(args):
    data = send_command("mark-read", {"id": args.id})
    output(data, args.pretty)


def cmd_send(args):
    cmd_args = {"to": args.to, "subject": args.subject, "body": args.body or "", "html": args.html}
    if args.cc:
        cmd_args["cc"] = args.cc
    if args.bcc:
        cmd_args["bcc"] = args.bcc
    data = send_command("send", cmd_args)
    output(data, args.pretty)


def cmd_reply(args):
    data = send_command("reply", {
        "id": args.id,
        "body": args.body or "",
        "all": args.all,
        "html": args.html,
    })
    output(data, args.pretty)


def cmd_forward(args):
    data = send_command("forward", {"id": args.id, "to": args.to})
    output(data, args.pretty)


def cmd_attachments(args):
    data = send_command("attachments", {"id": args.id})
    output(data, args.pretty)


def cmd_attachment(args):
    import base64
    data = send_command("attachment", {"id": args.id, "partName": args.part})
    content = base64.b64decode(data["data"])
    out_path = os.path.join(args.output_dir, data["name"])
    with open(out_path, "wb") as f:
        f.write(content)
    print(f"Saved: {out_path} ({len(content)} bytes)")


def cmd_setup(args):
    """Register native messaging host with Thunderbird via Windows registry."""
    manifest_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "native-host", "tbcli_host.json")
    )

    # Update the manifest path to be absolute
    import json as _json
    with open(manifest_path) as f:
        manifest = _json.load(f)

    bat_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "native-host", "tbcli_host.bat")
    )
    manifest["path"] = bat_path
    with open(manifest_path, "w") as f:
        _json.dump(manifest, f, indent=2)

    # Register in Windows registry for Thunderbird
    reg_path = r"Software\Mozilla\NativeMessagingHosts\tbcli_host"
    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_path)
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, manifest_path)
        winreg.CloseKey(key)
        print(f"Registered native host in registry: HKCU\\{reg_path}")
        print(f"Manifest: {manifest_path}")
        print(f"Host:     {bat_path}")
        print("\nNext steps:")
        print("  1. Install the extension in Thunderbird:")
        print("     Add-ons Manager > gear icon > Install Add-on From File")
        print(f"     Select: {os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'extension'))}")
        print("  2. Restart Thunderbird")
        print("  3. Run: tbcli status")
    except Exception as e:
        print(f"Error registering native host: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_commands(args):
    """Print machine-readable command reference for LLM/agent discovery."""
    ref = {
        "tool": "tbcli",
        "description": "CLI bridge to Thunderbird mail. All output is JSON by default. Message IDs are integers, used to chain read/reply/move/delete after list/search.",
        "commands": [
            {
                "command": "tbcli status",
                "description": "Check connection to Thunderbird",
            },
            {
                "command": "tbcli accounts",
                "description": "List mail accounts and identities",
                "returns": "[{id, name, type, identities: [{email, name}]}]",
            },
            {
                "command": "tbcli folders [--account NAME]",
                "description": "List all mail folders",
                "returns": "[{account, accountId, folders: [{id, name, path, specialUse}]}]",
            },
            {
                "command": "tbcli list [OPTIONS]",
                "description": "List messages in a folder. Default: Inbox. Use filters for server-side query.",
                "options": {
                    "--folder NAME": "Folder name (default: Inbox)",
                    "--unread": "Unread only",
                    "--flagged": "Starred only",
                    "--after YYYY-MM-DD": "Messages after date",
                    "--before YYYY-MM-DD": "Messages before date",
                    "--from ADDR": "Filter by sender (partial match)",
                    "--to ADDR": "Filter by recipient (partial match)",
                    "--subject TEXT": "Filter by subject (partial match)",
                    "--body TEXT": "Filter by body content",
                    "--limit N": "Max messages (default: 25)",
                },
                "returns": "[{id, date, from, to, subject, read, flagged, tags, size}]",
                "examples": [
                    "tbcli list --unread --limit 10",
                    "tbcli list --after 2026-03-01 --from boss@company.com",
                ],
            },
            {
                "command": "tbcli read ID [--html]",
                "description": "Read full message by ID. Returns headers + body text.",
                "returns": "{id, date, from, to, subject, read, flagged, tags, size, body}",
                "examples": ["tbcli read 1156"],
            },
            {
                "command": "tbcli search QUERY [OPTIONS]",
                "description": "Full-text search. Same filter options as list.",
                "options": {
                    "QUERY": "Full-text search string (required)",
                    "--folder NAME": "Restrict to folder",
                    "--unread/--after/--before/--from/--to/--subject/--body": "Same as list",
                    "--limit N": "Max results (default: 25)",
                },
                "examples": ["tbcli search 'budget report' --after 2026-01-01"],
            },
            {
                "command": "tbcli send --to ADDR --subject TEXT --body TEXT",
                "description": "Send a new message",
                "options": {
                    "--to ADDR": "Recipient (repeatable)",
                    "--cc ADDR": "CC (repeatable)",
                    "--bcc ADDR": "BCC (repeatable)",
                    "--subject TEXT": "Subject line",
                    "--body TEXT": "Body text",
                    "--body-file PATH": "Read body from file (use - for stdin)",
                    "--html": "Send as HTML",
                },
            },
            {
                "command": "tbcli reply ID --body TEXT [--all]",
                "description": "Reply to a message. --all for reply-all.",
            },
            {
                "command": "tbcli forward ID --to ADDR",
                "description": "Forward a message to recipient(s)",
            },
            {
                "command": "tbcli move ID FOLDER",
                "description": "Move message to folder",
            },
            {
                "command": "tbcli delete ID [--permanent]",
                "description": "Delete message. Default: move to trash. --permanent: skip trash.",
            },
            {
                "command": "tbcli flag ID",
                "description": "Star/flag a message",
            },
            {
                "command": "tbcli mark-read ID",
                "description": "Mark message as read",
            },
            {
                "command": "tbcli attachments ID",
                "description": "List attachments on a message",
                "returns": "[{partName, name, contentType, size}]",
            },
            {
                "command": "tbcli attachment ID PART [-o DIR]",
                "description": "Download attachment by part name to directory",
            },
        ],
        "workflow_tips": [
            "Use 'list' with date/unread filters to find messages, then 'read ID' for details",
            "Message IDs are session-scoped integers — get them from list/search output",
            "Chain operations: list -> read -> reply/forward/move/delete/flag/mark-read",
            "All commands return JSON. Pipe to jq for extraction: tbcli list | jq '.[].subject'",
        ],
    }
    output(ref)


def _build_system_prompt():
    """Build the system prompt for Claude, including tbcli reference."""
    import subprocess
    # Get the commands reference
    result = subprocess.run(
        [sys.executable, "-m", "tbcli", "commands"],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    commands_ref = result.stdout.strip()

    return f"""You are an email assistant with access to Thunderbird mail via the tbcli CLI tool.
You can run tbcli commands using bash to read, search, send, reply, organize, and manage email.

Today's date: {__import__('datetime').date.today().isoformat()}

## tbcli reference
{commands_ref}

## Guidelines
- Always use tbcli commands via bash to interact with email. All output is JSON.
- When listing messages, use appropriate filters (--after, --unread, --from, etc.) to be efficient.
- When the user asks to "check email" or similar, default to today's unread messages.
- Read message bodies with 'tbcli read ID' when you need content details.
- For actions like send/reply/delete, confirm with the user before executing unless they were explicit.
- Summarize results in natural language. Don't dump raw JSON at the user.
- You can chain multiple tbcli commands to accomplish complex tasks.
- NEVER use --body-file - for stdin piping. Always use --body "text" directly.
"""


def cmd_ask(args):
    """Natural language email task via Claude."""
    import subprocess
    prompt = " ".join(args.prompt)
    system = _build_system_prompt()

    if args.dry_run:
        print("=== SYSTEM PROMPT ===")
        print(system)
        print("\n=== USER PROMPT ===")
        print(prompt)
        return

    import shutil

    # Find claude binary (it's a .cmd on Windows, needs full path for subprocess)
    claude_path = shutil.which("claude")
    if not claude_path:
        print("Error: 'claude' CLI not found. Install Claude Code: npm install -g @anthropic-ai/claude-code", file=sys.stderr)
        sys.exit(1)

    cmd = [
        claude_path, "-p",
        "--model", args.model,
        "--allowedTools", "Bash",
        "--append-system-prompt", system,
    ]
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    proc = subprocess.run(cmd, input=prompt, env=env, encoding="utf-8", errors="replace")
    sys.exit(proc.returncode)


COMMANDS = {
    "status": cmd_status,
    "accounts": cmd_accounts,
    "folders": cmd_folders,
    "list": cmd_list,
    "read": cmd_read,
    "search": cmd_search,
    "move": cmd_move,
    "delete": cmd_delete,
    "flag": cmd_flag,
    "mark-read": cmd_mark_read,
    "send": cmd_send,
    "reply": cmd_reply,
    "forward": cmd_forward,
    "attachments": cmd_attachments,
    "attachment": cmd_attachment,
    "setup": cmd_setup,
    "commands": cmd_commands,
    "ask": cmd_ask,
}
