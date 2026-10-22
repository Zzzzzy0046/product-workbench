"""HTTP handler preserving the workbench's existing local API contract."""

from workbench.core.runtime import *
from workbench.api.routes import dispatch_get, dispatch_post
from workbench.api.serializers import attachment_header, encode_body


class Handler(BaseHTTPRequestHandler):
    server_version = "ProductWorkbench/0.9"

    def log_message(self, fmt, *args):
        pass

    @property
    def app(self):
        return self.server.app

    def respond(self, data, status=200, content_type="application/json; charset=utf-8", filename=None):
        body = encode_body(data, content_type)
        self.send_response(status)
        self.send_header("Content-Type",content_type)
        self.send_header("Content-Length",str(len(body)))
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Security-Policy","default-src 'self'; img-src 'self' blob: https://play-lh.googleusercontent.com https://lh3.googleusercontent.com https://*.mzstatic.com; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
        if filename:
            self.send_header("Content-Disposition", attachment_header(filename))
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        return self.headers.get("Host", "") in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}

    def discard_rejected_body(self):
        """Drain only a small bounded request before closing a rejected socket.

        Closing with unread POST bytes can reset the TCP connection on Windows
        before the client receives our 403. Never dispatch, log, or parse this
        data, and never wait indefinitely for an unauthenticated request.
        """
        self.close_connection = True
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            return
        if not 0 < length <= 16 * 1024:
            return
        previous_timeout = self.connection.gettimeout()
        try:
            self.connection.settimeout(0.5)
            self.rfile.read(length)
        except (OSError, TimeoutError):
            pass
        finally:
            self.connection.settimeout(previous_timeout)

    def do_GET(self):
        if not self.valid_host():
            return self.respond({"error":"无效 Host。"},403)
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            return dispatch_get(self, parsed, query)
        except ValueError as exc:
            return self.respond({"error":str(exc)},400)
        except Exception:
            return self.respond({"error":"读取失败，请检查服务配置。"},500)

    def do_POST(self):
        origin = self.headers.get("Origin")
        valid_origins = {f"http://127.0.0.1:{self.server.server_port}",f"http://localhost:{self.server.server_port}"}
        if not self.valid_host() or (origin and origin not in valid_origins) or not secrets.compare_digest(self.headers.get("X-Workbench-Token", ""),self.app.token):
            self.discard_rejected_body()
            return self.respond({"error":"请求校验失败，请刷新工作台。"},403)
        try:
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length", "0"))
            limit = MAX_PACKAGE * 2 if path == "/api/projects/import" else MAX_FILE * 2
            if length < 1 or length > limit:
                return self.respond({"error":"请求过大或为空。"},413)
            payload = json.loads(self.rfile.read(length))
            return dispatch_post(self, path, payload)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            return self.respond({"error":str(exc) if isinstance(exc,ValueError) else "请求字段无效。"},400)
        except Exception:
            return self.respond({"error":"操作失败，请检查文件与服务配置。"},500)
