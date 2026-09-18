import json, os, re, http.server, socketserver, urllib.parse, socket, urllib.request

PORT = 8000
BACKEND_PORT = 8001


class ReuseAddrServer(socketserver.TCPServer):
    allow_reuse_address = True
    def server_bind(self):
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        super().server_bind()

class RewriteHandler(http.server.SimpleHTTPRequestHandler):
    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass

    def __init__(self, *args, **kwargs):
        with open("vercel.json") as f:
            config = json.load(f)
        self.rewrites = []
        for route in config.get("routes", []):
            src = route.get("src", "")
            dest = route.get("dest", "")
            if dest and not src.startswith("/api/"):
                self.rewrites.append((re.compile(src), dest))
        super().__init__(*args, directory=".", **kwargs)

    def translate_path(self, path):
        path = self._apply_rewrites(path)
        return super().translate_path(path)

    def _apply_rewrites(self, path):
        path = urllib.parse.urlparse(path).path
        for pattern, dest in self.rewrites:
            m = pattern.fullmatch(path)
            if m:
                result = dest
                for idx, g in enumerate(m.groups(), 1):
                    result = result.replace(f"${idx}", g)
                print(f"  rewrite: {path} -> {result}")
                return result
        return path

    def do_POST(self):
        if self.path.startswith("/api/"):
            self._proxy_api()
        else:
            super().do_POST()

    def do_PUT(self):
        if self.path.startswith("/api/"):
            self._proxy_api()
        else:
            self.send_response(405)
            self.end_headers()

    def do_DELETE(self):
        if self.path.startswith("/api/"):
            self._proxy_api()
        else:
            self.send_response(405)
            self.end_headers()

    def do_OPTIONS(self):
        if self.path.startswith("/api/"):
            self._proxy_api()
        else:
            self.send_response(200)
            self.send_header("Allow", "GET, POST, PUT, DELETE, OPTIONS")
            self.end_headers()

    def do_GET(self):
        if self.path.startswith("/api/"):
            self._proxy_api()
        else:
            super().do_GET()


    def _proxy_api(self):
        backend_url = f"http://localhost:{BACKEND_PORT}{self.path}"
        body = None
        if self.command in ("POST", "PUT", "PATCH"):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length > 0 else None

        req = urllib.request.Request(
            backend_url,
            data=body,
            method=self.command,
            headers={k: v for k, v in self.headers.items()
                     if k.lower() not in ("host", "connection", "transfer-encoding")},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() not in ("transfer-encoding", "content-encoding"):
                        self.send_header(k, v)
                self.end_headers()
                self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            for k, v in e.headers.items():
                if k.lower() not in ("transfer-encoding", "content-encoding"):
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(e.read())
        except urllib.error.URLError:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Backend not running"}).encode())



if __name__ == "__main__":
    with ReuseAddrServer(("", PORT), RewriteHandler) as httpd:
        print(f"Server: http://localhost:{PORT}")
        print(f"Backend: run 'uvicorn backend.main:app --port {BACKEND_PORT}' in another terminal")
        print(f"API proxy: /api/* -> http://localhost:{BACKEND_PORT}/api/*")
        httpd.serve_forever()
