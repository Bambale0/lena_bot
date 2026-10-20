import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError

import pytest

from api import public_files


def test_reference_download_does_not_follow_redirect(monkeypatch):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(302)
            self.send_header("Location", "/private-target")
            self.end_headers()

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # Only the loopback fixture bypasses DNS/IP validation; redirect handling is real.
    monkeypatch.setattr(public_files, "_reject_private_url_targets", lambda _url: None)
    try:
        with pytest.raises(HTTPError) as error:
            public_files._download_public_url(
                f"http://127.0.0.1:{server.server_port}/reference", follow_redirects=False,
            )
        assert error.value.code == 302
        assert requests == ["/reference"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_reference_download_rejects_private_target_before_opening():
    with pytest.raises(ValueError, match="non-public"):
        public_files._download_public_url("http://127.0.0.1/reference", follow_redirects=False)
