"""Serve the local D&D table. No external packages, cloud calls, or API keys."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import socket
import sys
from urllib.parse import unquote, urlsplit

from engine import CampaignError, StateStore, object_field, require
from character_builder import BUILD_FIELDS
from runtime_info import runtime_fingerprint


BASE_DIR = Path(__file__).resolve().parent
MAX_BODY_BYTES = 1024 * 1024
APP_MARKER = "dnd-local-master"


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, root: str | Path = BASE_DIR):
        self.root = Path(root).resolve()
        self.store = StateStore(self.root)
        self.runtime_fingerprint = runtime_fingerprint(self.root)
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = "DNDLocal/1.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(8)

    def log_message(self, message, *args):
        # BaseHTTPRequestHandler on Python >= 3.11 sanitizes control characters.
        super().log_message(message, *args)

    def _headers(self, status: int, content_type: str, length: int, *, json_response=False,
                 attachment=False):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if json_response:
            self.send_header("Cache-Control", "no-store")
        else:
            self.send_header("Cache-Control", "no-cache")
        if attachment:
            self.send_header("Content-Disposition", 'attachment; filename="dnd-campagna.json"')
        self.end_headers()

    def _json(self, value, status=200, *, attachment=False, head=False):
        body = (json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(body), json_response=True,
                      attachment=attachment)
        if not head:
            self.wfile.write(body)

    def _error(self, exc: CampaignError, *, head=False):
        self._json({"error": str(exc), "code": exc.code}, exc.status, head=head)

    def _check_origin(self):
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if port == 80:
            hosts.update(("127.0.0.1", "localhost"))
        host_values = self.headers.get_all("Host", [])
        if len(host_values) != 1 or host_values[0].lower() not in hosts:
            raise CampaignError("Host non consentito: usa localhost o 127.0.0.1 e la porta del tavolo.", "forbidden_host", 403)
        origins = self.headers.get_all("Origin", [])
        if len(origins) > 1:
            raise CampaignError("Origine non consentita.", "forbidden_origin", 403)
        if origins:
            try:
                origin = urlsplit(origins[0])
                allowed = (origin.scheme == "http" and origin.hostname in ("localhost", "127.0.0.1")
                           and (origin.port or 80) == port and not origin.username and not origin.password
                           and origin.path in ("", "/") and not origin.query and not origin.fragment)
            except ValueError:
                allowed = False
            if not allowed:
                raise CampaignError("Origine non consentita.", "forbidden_origin", 403)
        if self.headers.get("Sec-Fetch-Site", "") == "cross-site":
            raise CampaignError("Richiesta da un altro sito non consentita.", "forbidden_origin", 403)

    def _body(self) -> dict:
        if self.headers.get_content_type().lower() != "application/json":
            raise CampaignError("Usa Content-Type: application/json.", "unsupported_content_type", 415)
        if self.headers.get("Transfer-Encoding"):
            self.close_connection = True
            raise CampaignError("Transfer-Encoding non supportato.", "invalid_input", 400)
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1:
            raise CampaignError("Serve un singolo Content-Length.", "length_required", 411)
        try:
            length = int(lengths[0])
        except ValueError:
            raise CampaignError("Content-Length non valido.") from None
        if length < 1:
            raise CampaignError("Corpo JSON vuoto.")
        if length > MAX_BODY_BYTES:
            self.close_connection = True
            raise CampaignError("Richiesta troppo grande (massimo 1 MiB).", "body_too_large", 413)
        try:
            raw = self.rfile.read(length)
            require(len(raw) == length, "Corpo JSON incompleto.")
            body = json.loads(raw.decode("utf-8-sig"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite")))
        except (UnicodeError, ValueError, RecursionError):
            raise CampaignError("JSON non valido.") from None
        return object_field(body, "request")

    @staticmethod
    def _fields(body: dict, allowed: set[str], required: set[str]):
        require(set(body).issubset(allowed) and required.issubset(body),
                "Campi della richiesta mancanti o sconosciuti.")

    def do_GET(self):
        self._get()

    def do_HEAD(self):
        self._get(head=True)

    def _get(self, head=False):
        try:
            self._check_origin()
            path = urlsplit(self.path).path
            store = self.server.store
            if path == "/api/health":
                state = store.read()
                self._json({"ok": True, "app": APP_MARKER, "workspace": str(self.server.root),
                            "campaign_id": state["campaign_id"], "api_version": 3,
                            "pid": os.getpid(), "runtime_fingerprint": self.server.runtime_fingerprint,
                            "features": ["character_builder", "character_rebuild", "live_status",
                                         "atomic_table", "safe_import", "master_start", "dynamic_map"]}, head=head)
            elif path == "/api/state":
                self._json(store.read(), head=head)
            elif path == "/api/table":
                self._json(store.table(), head=head)
            elif path == "/api/status":
                self._json(store.status(), head=head)
            elif path == "/api/world":
                self._json(store.table()["world"], head=head)
            elif path == "/api/character-options":
                self._json(store.character_options(), head=head)
            elif path == "/api/export":
                self._json(store.read(), attachment=True, head=head)
            elif path.startswith("/api/"):
                raise CampaignError("Endpoint non trovato.", "not_found", 404)
            else:
                self._static(path, head=head)
        except CampaignError as exc:
            self._error(exc, head=head)
        except (ConnectionError, socket.timeout):
            self.close_connection = True
        except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
            self.log_error("Local read error: %s", type(exc).__name__)
            self._error(CampaignError("Errore nella lettura dei file locali.", "storage_error", 500), head=head)

    def _static(self, path: str, head=False):
        try:
            path = unquote(path, errors="strict")
        except UnicodeError:
            raise CampaignError("Percorso non valido.", "not_found", 404) from None
        if not path.startswith("/") or "\\" in path or "\0" in path:
            raise CampaignError("File non trovato.", "not_found", 404)
        segments = path.split("/")
        if any(segment.startswith(".") for segment in segments if segment):
            raise CampaignError("File non trovato.", "not_found", 404)
        web_root = (self.server.root / "web").resolve()
        relative = "index.html" if path == "/" else path.lstrip("/")
        target = (web_root / relative).resolve()
        allowed = {".html", ".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico", ".woff", ".woff2"}
        public_map_catalog = target == web_root / "assets" / "maps" / "library.json"
        if not target.is_relative_to(web_root) or not target.is_file() or (target.suffix.lower() not in allowed and not public_map_catalog):
            raise CampaignError("File non trovato.", "not_found", 404)
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if target.suffix.lower() in (".js", ".css", ".html", ".svg"):
            content_type += "; charset=utf-8"
        body = target.read_bytes()
        self._headers(200, content_type, len(body))
        if not head:
            self.wfile.write(body)

    def do_POST(self):
        try:
            self._check_origin()
            path = urlsplit(self.path).path
            if path not in ("/api/action", "/api/character", "/api/character-rebuild", "/api/active-character", "/api/roll", "/api/import", "/api/note"):
                raise CampaignError("Endpoint non trovato.", "not_found", 404)
            body = self._body()
            store = self.server.store
            if path == "/api/action":
                self._fields(body, {"text"}, {"text"})
                state, action = store.queue_action(body["text"])
                result = {"state": state, "action": action}
            elif path == "/api/character":
                if "template_id" in body:
                    self._fields(body, {"template_id", "name", "expected_revision"}, {"template_id"})
                    state, character = store.choose_character(body["template_id"], body.get("name"), body.get("expected_revision"))
                else:
                    self._fields(body, BUILD_FIELDS | {"expected_revision"}, {"class_id", "species_id", "name"})
                    payload = {key: value for key, value in body.items() if key != "expected_revision"}
                    state, character = store.create_character(payload, body.get("expected_revision"))
                result = {"state": state, "character": character}
            elif path == "/api/character-rebuild":
                self._fields(body, BUILD_FIELDS | {"character_id", "expected_revision"},
                             {"character_id", "expected_revision", "class_id", "species_id", "name"})
                payload = {key: value for key, value in body.items() if key in BUILD_FIELDS}
                state, character = store.rebuild_character(body["character_id"], payload, body["expected_revision"])
                result = {"state": state, "character": character}
            elif path == "/api/active-character":
                self._fields(body, {"character_id"}, {"character_id"})
                state, character = store.active_character(body["character_id"])
                result = {"state": state, "character": character}
            elif path == "/api/roll":
                self._fields(body, {"expression", "label", "mode"}, {"expression"})
                state, roll = store.roll(body["expression"], body.get("label", "Tiro"), body.get("mode", "normal"))
                result = {"state": state, "roll": roll}
            elif path == "/api/note":
                self._fields(body, {"text"}, {"text"})
                state, note = store.note(body["text"])
                result = {"state": state, "note": note}
            else:
                self._fields(body, {"state", "expected_revision"}, {"state", "expected_revision"})
                require(type(body["expected_revision"]) is int, "expected_revision: serve la revisione corrente.")
                state, _ = store.restore(body["state"], body["expected_revision"])
                result = {"state": state}
            self._json(result)
        except CampaignError as exc:
            self._error(exc)
        except (ConnectionError, socket.timeout):
            self.close_connection = True
        except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
            self.log_error("Local write error: %s", type(exc).__name__)
            self._error(CampaignError("Errore nel salvataggio locale.", "storage_error", 500))

    def do_OPTIONS(self):
        self._error(CampaignError("Metodo non consentito.", "method_not_allowed", 405))

    do_PUT = do_OPTIONS
    do_PATCH = do_OPTIONS
    do_DELETE = do_OPTIONS


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Tavolo D&D locale — il master è la chat.")
    parser.add_argument("--port", type=int, default=8765, help="Porta locale (default: 8765).")
    parser.add_argument("--root", type=Path, default=BASE_DIR, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("La porta deve essere tra 1 e 65535.")
    try:
        if not (args.root / "data" / "campaign.json").exists():
            from tools.setup_demo import initialize
            initialize(args.root)
        store = StateStore(args.root)
        store.read()
        server = LocalServer(("127.0.0.1", args.port), args.root)
    except (CampaignError, OSError) as exc:
        print(json.dumps({"error": str(exc), "code": getattr(exc, "code", "server_error")}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(f"Tavolo aperto: http://127.0.0.1:{args.port} — Ctrl+C per chiudere", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
