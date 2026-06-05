#!/usr/bin/env python3
"""tbcli native messaging host — bridges Thunderbird native messaging to a TCP socket."""

import json
import struct
import sys
import socket
import threading
import os
import time

HOST = "127.0.0.1"
PORT = 47200
LOCK_FILE = os.path.join(os.path.expanduser("~"), ".tbcli_host.lock")


def read_native_message(stream):
    """Read a native messaging message from stdin."""
    raw_len = stream.buffer.read(4)
    if not raw_len or len(raw_len) < 4:
        return None
    msg_len = struct.unpack("<I", raw_len)[0]
    data = stream.buffer.read(msg_len)
    if not data:
        return None
    return json.loads(data.decode("utf-8"))


def write_native_message(stream, msg):
    """Write a native messaging message to stdout."""
    data = json.dumps(msg).encode("utf-8")
    stream.buffer.write(struct.pack("<I", len(data)))
    stream.buffer.write(data)
    stream.buffer.flush()


class NativeHost:
    def __init__(self):
        self.pending = {}  # id -> client socket
        self.lock = threading.Lock()
        self.msg_id = 0
        self.server = None
        self.running = True

    def next_id(self):
        with self.lock:
            self.msg_id += 1
            return str(self.msg_id)

    def start_tcp_server(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((HOST, PORT))
        self.server.listen(4)
        self.server.settimeout(1.0)
        # Write lock file so CLI knows I'm alive
        with open(LOCK_FILE, "w") as f:
            f.write(str(PORT))
        while self.running:
            try:
                client, addr = self.server.accept()
                t = threading.Thread(target=self.handle_client, args=(client,), daemon=True)
                t.start()
            except socket.timeout:
                continue
            except OSError:
                break

    def handle_client(self, client):
        """Handle a TCP client connection (one request-response per connection)."""
        try:
            data = b""
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                data += chunk
                # Try to parse — simple framing: one JSON object per connection
                try:
                    request = json.loads(data.decode("utf-8"))
                    break
                except json.JSONDecodeError:
                    continue

            if not data:
                client.close()
                return

            msg_id = self.next_id()
            request["id"] = msg_id

            with self.lock:
                self.pending[msg_id] = client

            # Forward to extension via native messaging
            write_native_message(sys.stdout, request)

        except Exception as e:
            try:
                client.sendall(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))
                client.close()
            except:
                pass

    def read_extension_responses(self):
        """Read responses from the extension via stdin and route to TCP clients."""
        while self.running:
            try:
                msg = read_native_message(sys.stdin)
                if msg is None:
                    break
                msg_id = msg.get("id")
                with self.lock:
                    client = self.pending.pop(msg_id, None)
                if client:
                    try:
                        client.sendall(json.dumps(msg).encode("utf-8"))
                        client.close()
                    except:
                        pass
            except Exception:
                break
        self.running = False

    def run(self):
        # Start TCP server in a thread
        tcp_thread = threading.Thread(target=self.start_tcp_server, daemon=True)
        tcp_thread.start()

        # Read extension messages on main thread (stdin)
        try:
            self.read_extension_responses()
        finally:
            self.running = False
            try:
                os.unlink(LOCK_FILE)
            except:
                pass
            if self.server:
                self.server.close()


if __name__ == "__main__":
    host = NativeHost()
    host.run()
