"""Official Angel One publisher-login callback for the desktop application."""
from __future__ import annotations

from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from secrets import token_urlsafe
from threading import Thread
from urllib.parse import parse_qs, urlencode, urlparse


DEFAULT_CALLBACK = "http://127.0.0.1:8765/angel-one/callback"


class AngelOnePublisherLogin:
    LOGIN_URL = "https://smartapi.angelone.in/publisher-login"

    def __init__(self, api_key: str, callback_url: str = DEFAULT_CALLBACK, timeout_seconds: int = 300):
        self.api_key = str(api_key or "").strip()
        self.callback_url = str(callback_url or DEFAULT_CALLBACK).strip()
        self.timeout_seconds = max(30, min(600, int(timeout_seconds)))
        self.state = token_urlsafe(24)
        self._server = None

    def authorization_url(self) -> str:
        if not self.api_key:
            raise ValueError("Angel One API Key is required for official login.")
        parsed = urlparse(self.callback_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise ValueError("Desktop callback must use local http://127.0.0.1 or localhost.")
        return f"{self.LOGIN_URL}?{urlencode({'api_key': self.api_key, 'redirect_url': self.callback_url, 'state': self.state})}"

    def start(self, on_success, on_error) -> str:
        """Start one bounded local callback and return the official login URL."""
        login_url = self.authorization_url()
        parsed = urlparse(self.callback_url)
        expected_path = parsed.path or "/"
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format, *_args):
                return

            def do_GET(self):
                request = urlparse(self.path)
                if request.path != expected_path:
                    self.send_error(404)
                    return
                values = {key: items[0] for key, items in parse_qs(request.query).items() if items}
                auth_token = values.get("auth_token") or values.get("jwtToken") or values.get("jwt_token")
                feed_token = values.get("feed_token") or values.get("feedToken")
                returned_state = values.get("state")
                error = values.get("error") or values.get("message")
                if returned_state != owner.state:
                    owner._respond(self, False, "Security state did not match. Please restart broker login.")
                    on_error("Angel One callback security state did not match.")
                elif error or not auth_token or not feed_token:
                    message = error or "Angel One did not return both auth_token and feed_token."
                    owner._respond(self, False, message)
                    on_error(message)
                else:
                    owner._respond(self, True, "Angel One authorization received. You can return to TPS.")
                    on_success({
                        "auth_token": auth_token, "feed_token": feed_token,
                        "client_code": values.get("client_code") or values.get("clientcode") or values.get("user_id") or "",
                    })

        try:
            self._server = ThreadingHTTPServer((parsed.hostname, parsed.port or 80), Handler)
        except OSError as error:
            raise RuntimeError(f"TPS local broker callback could not start: {error}") from error
        self._server.timeout = self.timeout_seconds

        def wait_once():
            try:
                self._server.handle_request()
            except Exception as error:
                on_error(f"Angel One callback failed: {error}")
            finally:
                self._server.server_close()
                self._server = None

        Thread(target=wait_once, name="tps-angel-publisher-callback", daemon=True).start()
        return login_url

    @staticmethod
    def _respond(handler, success: bool, message: str):
        title = "Authorization complete" if success else "Authorization failed"
        colour = "#3ddc97" if success else "#ff6b6b"
        body = (
            "<!doctype html><html><head><meta charset='utf-8'><title>TPS Broker Login</title></head>"
            "<body style='font-family:Segoe UI;background:#120d33;color:#fff;padding:48px'>"
            f"<h1 style='color:{colour}'>{escape(title)}</h1><p>{escape(message)}</p>"
            "<p>This page never displays or stores your broker PIN, password or TOTP.</p></body></html>"
        ).encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
