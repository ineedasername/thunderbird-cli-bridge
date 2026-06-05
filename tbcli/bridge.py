"""TCP client to the tbcli native messaging host."""

import json
import socket
import sys
import os

HOST = "127.0.0.1"
PORT = 47200
TIMEOUT = 15


def send_command(command, args=None, timeout=TIMEOUT):
    """Send a command to the native host and return the response."""
    msg = {"command": command}
    if args:
        msg["args"] = args

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((HOST, PORT))
        sock.sendall(json.dumps(msg).encode("utf-8"))
        sock.shutdown(socket.SHUT_WR)

        data = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
        sock.close()

        response = json.loads(data.decode("utf-8"))
        if not response.get("ok"):
            err = {"ok": False, "error": response.get("error", "unknown error")}
            print(json.dumps(err), file=sys.stderr)
            sys.exit(1)
        return response.get("data")

    except ConnectionRefusedError:
        print(json.dumps({
            "ok": False,
            "error": "Cannot connect to tbcli host on port 47200",
            "hint": "Ensure Thunderbird is running with tbcli-bridge extension installed. Run 'tbcli setup' if not yet configured."
        }), file=sys.stderr)
        sys.exit(1)
    except socket.timeout:
        print(json.dumps({
            "ok": False,
            "error": "Request timed out after {}s".format(timeout),
            "hint": "Thunderbird may be busy. Try again or increase timeout."
        }), file=sys.stderr)
        sys.exit(1)
