"""Client LSP minimale per i test end-to-end.

Lancia ``python -m glls`` come subprocess e parla il protocollo vero
(JSON-RPC con framing Content-Length su stdio): quello che fanno VS Code,
Neovim e Pulsar. Nessuna dipendenza oltre la stdlib.
"""
from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
from typing import Any, Dict, List, Optional


class LspClient:
    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "glls"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._id = 0
        self._incoming: "queue.Queue[dict]" = queue.Queue()
        self.notifications: List[dict] = []
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    # ------------------------------------------------------------------
    def _read_loop(self) -> None:
        stdout = self.proc.stdout
        while True:
            headers: Dict[str, str] = {}
            line = stdout.readline()
            if not line:
                return
            while line and line.strip():
                name, _, value = line.decode("ascii").partition(":")
                headers[name.strip().lower()] = value.strip()
                line = stdout.readline()
            length = int(headers.get("content-length", 0))
            if length <= 0:
                continue
            body = stdout.read(length)
            try:
                self._incoming.put(json.loads(body.decode("utf-8")))
            except json.JSONDecodeError:
                continue

    def _send(self, msg: dict) -> None:
        body = json.dumps(msg).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self.proc.stdin.write(header + body)
        self.proc.stdin.flush()

    # ------------------------------------------------------------------
    def notify(self, method: str, params: Any = None) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def request(self, method: str, params: Any = None) -> Any:
        self._id += 1
        rid = self._id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method,
                    "params": params or {}})
        while True:
            msg = self._incoming.get(timeout=self.timeout)
            if msg.get("id") == rid and ("result" in msg or "error" in msg):
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg["result"]
            if "method" in msg and "id" not in msg:
                self.notifications.append(msg)
            elif "method" in msg and "id" in msg:
                # richiesta server->client: rispondi null
                self._send({"jsonrpc": "2.0", "id": msg["id"], "result": None})

    def wait_notification(self, method: str) -> dict:
        for n in self.notifications:
            if n["method"] == method:
                self.notifications.remove(n)
                return n
        while True:
            msg = self._incoming.get(timeout=self.timeout)
            if msg.get("method") == method and "id" not in msg:
                return msg
            if "method" in msg and "id" not in msg:
                self.notifications.append(msg)
            elif "method" in msg and "id" in msg:
                self._send({"jsonrpc": "2.0", "id": msg["id"], "result": None})

    # ------------------------------------------------------------------
    def initialize(self) -> dict:
        result = self.request("initialize", {
            "processId": None,
            "rootUri": None,
            "capabilities": {
                "textDocument": {
                    "publishDiagnostics": {},
                    "completion": {"completionItem": {"snippetSupport": True}},
                    "hover": {"contentFormat": ["markdown"]},
                    "semanticTokens": {
                        "requests": {"full": True},
                        "tokenTypes": [], "tokenModifiers": [], "formats": ["relative"],
                    },
                    "codeAction": {}, "inlayHint": {}, "codeLens": {},
                    "documentSymbol": {"hierarchicalDocumentSymbolSupport": True},
                },
            },
        })
        self.notify("initialized", {})
        return result

    def open(self, uri: str, text: str, version: int = 1) -> List[dict]:
        self.notify("textDocument/didOpen", {
            "textDocument": {"uri": uri, "languageId": "yaml",
                             "version": version, "text": text},
        })
        note = self.wait_notification("textDocument/publishDiagnostics")
        return note["params"]["diagnostics"]

    def change(self, uri: str, text: str, version: int) -> List[dict]:
        self.notify("textDocument/didChange", {
            "textDocument": {"uri": uri, "version": version},
            "contentChanges": [{"text": text}],
        })
        note = self.wait_notification("textDocument/publishDiagnostics")
        return note["params"]["diagnostics"]

    def shutdown(self) -> None:
        try:
            self.request("shutdown")
            self.notify("exit")
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.kill()
        finally:
            for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
                try:
                    stream.close()
                except Exception:
                    pass


def apply_edits(text: str, edits: List[dict]) -> str:
    """Applica TextEdit LSP a un testo (per verificare le code action)."""
    lines = text.split("\n")

    def offset(pos: dict) -> int:
        return sum(len(l) + 1 for l in lines[:pos["line"]]) + pos["character"]

    ordered = sorted(edits, key=lambda e: (e["range"]["start"]["line"],
                                           e["range"]["start"]["character"]),
                     reverse=True)
    for e in ordered:
        s, t = offset(e["range"]["start"]), offset(e["range"]["end"])
        text = text[:s] + e["newText"] + text[t:]
        lines = text.split("\n")
    return text
