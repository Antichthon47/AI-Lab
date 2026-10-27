"""Restricted Unix-socket Ollama broker and private-namespace HTTP relay.

Importing this module makes no network requests. Tests supply a fake upstream.
"""
import argparse
import http.client
import http.server
import json
import socket
import socketserver
import subprocess
import sys
import threading
import time

MAX_BODY = 2 * 1024 * 1024
MAX_RESPONSE = 32 * 1024 * 1024
MODELS = frozenset(("pi-qwen35-9b-16k", "pi-qwen35-9b-32k", "qwen3:8b-32k"))
FIELDS = frozenset(("model", "messages", "input", "instructions", "tools", "tool_choice",
                    "parallel_tool_calls", "stream", "stream_options", "temperature", "top_p",
                    "max_tokens", "max_completion_tokens", "max_output_tokens", "reasoning", "reasoning_effort",
                    "think", "seed", "stop", "presence_penalty", "frequency_penalty"))


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def text_content(content):
    if content is None or isinstance(content, str):
        return
    if not isinstance(content, list):
        raise ValueError("text-only content required")
    for part in content:
        if (not isinstance(part, dict) or part.get("type") not in ("text", "input_text", "output_text", "summary_text")
                or set(part) - {"type", "text", "annotations"} or not isinstance(part.get("text"), str)):
            raise ValueError("images, files, URLs and nontext content blocks forbidden")


def local_schema(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref" and (not isinstance(child, str) or not child.startswith("#/")):
                raise ValueError("remote schema references forbidden")
            local_schema(child)
    elif isinstance(value, list):
        for child in value:
            local_schema(child)


def authorize(method, path, body):
    if method == "GET" and path in ("/healthz", "/v1/models", "/api/tags", "/api/version"):
        if body:
            raise ValueError("GET bodies forbidden")
        return
    if method != "POST" or path not in ("/v1/chat/completions", "/v1/responses"):
        raise ValueError("route forbidden")
    value = json.loads(body, object_pairs_hook=no_duplicates)
    if not isinstance(value, dict) or value.get("model") not in MODELS:
        raise ValueError("model forbidden")
    if value.keys() - FIELDS:
        raise ValueError("unsupported request fields")
    if "reasoning_effort" in value and value["reasoning_effort"] != "none":
        raise ValueError("only reasoning_effort=none is permitted")
    # Inference endpoints can otherwise become server-side fetch proxies through
    # image/file URLs or built-in web/MCP tools. This benchmark is text only.
    if "instructions" in value and not isinstance(value["instructions"], str):
        raise ValueError("text instructions required")
    for tool in value.get("tools", []):
        if (not isinstance(tool, dict) or tool.get("type") != "function"
                or set(tool) - {"type", "function", "name", "description", "parameters", "strict"}):
            raise ValueError("only client-executed function tools allowed")
        local_schema(tool)
    if "messages" in value:
        if not isinstance(value["messages"], list):
            raise ValueError("message list required")
        for message in value["messages"]:
            if not isinstance(message, dict) or set(message) - {"role", "content", "name", "tool_call_id", "tool_calls", "reasoning", "reasoning_content"}:
                raise ValueError("unsupported message fields")
            if message.get("role") not in ("system", "developer", "user", "assistant", "tool"):
                raise ValueError("unsupported message role")
            text_content(message.get("content"))
            for call in message.get("tool_calls", []):
                if not isinstance(call, dict) or call.get("type") != "function":
                    raise ValueError("only function tool-call replay allowed")
    if "input" in value:
        if isinstance(value["input"], str):
            pass
        elif isinstance(value["input"], list):
            for item in value["input"]:
                if not isinstance(item, dict):
                    raise ValueError("unsupported input")
                kind = item.get("type", "message")
                if kind == "message":
                    if set(item) - {"type", "role", "content", "id", "status"}:
                        raise ValueError("unsupported message fields")
                    text_content(item.get("content"))
                elif kind == "function_call_output":
                    if set(item) - {"type", "id", "call_id", "output", "status"}:
                        raise ValueError("unsupported call-output fields")
                    text_content(item.get("output"))
                elif kind == "function_call":
                    if set(item) - {"type", "id", "call_id", "name", "arguments", "status"}:
                        raise ValueError("unsupported function-call fields")
                    if not isinstance(item.get("arguments"), str):
                        raise ValueError("string function arguments required")
                elif kind == "reasoning":
                    if set(item) - {"type", "id", "summary", "status", "encrypted_content"}:
                        raise ValueError("unsupported reasoning fields")
                    text_content(item.get("summary"))
                else:
                    raise ValueError("nontext input type forbidden")
        else:
            raise ValueError("unsupported input")
    for field in ("max_tokens", "max_completion_tokens", "max_output_tokens"):
        if field in value and (type(value[field]) is not int or not 1 <= value[field] <= 2048):
            raise ValueError("output budget must be 1..2048")
    if not any(field in value for field in ("max_tokens", "max_completion_tokens", "max_output_tokens")):
        value["max_output_tokens" if path == "/v1/responses" else "max_tokens"] = 2048
    return value


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", timeout=10)
        self.path = str(path)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)

    def getresponse(self):
        # Keep the existing 10-second connect/request-write timeout. Only the
        # response header/stream reads on the Unix relay get a longer idle wait.
        if self.sock is not None:
            self.sock.settimeout(120)
        return super().getresponse()


class StreamMetadata:
    """Observe terminal markers without retaining or logging response content."""
    def __init__(self):
        self.pending = b""
        self.finish_reason_seen = False
        self.done_seen = False

    def observe(self, chunk):
        self.pending += chunk
        while b"\n" in self.pending:
            line, self.pending = self.pending.split(b"\n", 1)
            if not line.startswith(b"data:"):
                continue
            data = line[5:].strip()
            if data == b"[DONE]":
                self.done_seen = True
                continue
            try:
                event = json.loads(data)
                if isinstance(event, dict):
                    self.finish_reason_seen |= any(isinstance(c, dict) and bool(c.get("finish_reason"))
                                                   for c in event.get("choices", []))
            except (ValueError, TypeError):
                pass
        if len(self.pending) > 65536:
            self.pending = b""  # Bounded diagnostic buffer; forwarding is untouched.


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *_):
        pass  # Do not leak prompts/credentials into a shared host log.

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def body(self):
        if self.headers.get_all("Transfer-Encoding") or self.headers.get_all("Expect"):
            raise ValueError("chunked/Expect requests forbidden")
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) > 1:
            raise ValueError("ambiguous content length")
        length = int(lengths[0]) if lengths else 0
        if not 0 <= length <= MAX_BODY:
            raise ValueError("request too large")
        data = self.rfile.read(length)
        if len(data) != length:
            raise ValueError("incomplete body")
        return data

    def do_GET(self):
        self.forward()

    def do_POST(self):
        self.forward()

    def do_CONNECT(self):
        self.send_error(403, "CONNECT forbidden")

    def do_PUT(self):
        self.send_error(403, "method forbidden")

    do_DELETE = do_PUT
    do_PATCH = do_PUT

    def forward(self):
        try:
            body = self.body()
            value = authorize(self.command, self.path, body)
            if self.command == "POST":
                body = json.dumps(value).encode()
        except (ValueError, TypeError, UnicodeError):
            self.send_error(403, "request forbidden")
            return
        # Discovery stays local: no management APIs or upstream discovery calls.
        if self.command == "GET" and not self.server.relay:
            if self.path == "/healthz":
                value = {"ok": True}
            elif self.path == "/api/version":
                value = {"version": "0.40.11", "broker": True}
            elif self.path == "/api/tags":
                value = {"models": [{"name": m, "model": m} for m in sorted(MODELS)]}
            else:
                value = {"object": "list", "data": [{"id": m, "object": "model", "owned_by": "local"} for m in sorted(MODELS)]}
            encoded = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return
        connection = self.server.upstream()
        started = time.monotonic()
        count = 0
        status = None
        reason = "connection_closed"
        stage = "request"
        metadata = StreamMetadata()

        def log(event):
            print(json.dumps({"event": event, "layer": "relay" if self.server.relay else "broker",
                              "elapsed_seconds": round(time.monotonic()-started, 3),
                              "bytes_read": count, "status": status, "stage": stage,
                              "reason": reason, "finish_reason_seen": metadata.finish_reason_seen,
                              "done_seen": metadata.done_seen}), file=sys.stderr, flush=True)

        try:
            # Never forward Host, Authorization, proxy headers, cookies or URLs
            # supplied by the client. There is exactly one pinned upstream.
            connection.request(self.command, self.path, body=body,
                               headers={"Content-Type": "application/json"})
            stage = "response_headers"
            response = connection.getresponse()
            status = response.status
            if 300 <= response.status < 400:
                self.send_error(502, "upstream redirects forbidden")
                return
            self.send_response(response.status)
            self.send_header("Content-Type", response.getheader("Content-Type", "application/json"))
            self.end_headers()
            while True:
                stage = "read"
                chunk = response.read1(8192)
                if not chunk:
                    reason = "upstream_eof"
                    log("stream_complete")
                    break
                count += len(chunk)
                if "text/event-stream" in response.getheader("Content-Type", ""):
                    metadata.observe(chunk)
                if count > MAX_RESPONSE or time.monotonic() - started > 600:
                    reason = "existing_size_or_total_time_limit"
                    break
                stage = "write"
                self.wfile.write(chunk)
                self.wfile.flush()
        except TimeoutError:
            reason = "idle_timeout"
            log("read_timeout" if stage in ("read", "response_headers") else "connection_timeout")
            self.close_connection = True
        except (OSError, http.client.HTTPException) as error:
            reason = type(error).__name__
            self.close_connection = True
        finally:
            connection.close()
            log("connection_closed")


class BoundedThreads(socketserver.ThreadingMixIn):
    daemon_threads = True
    block_on_close = False

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()


class UnixServer(BoundedThreads, socketserver.UnixStreamServer):
    daemon_threads = True
    block_on_close = False
    relay = False


class RelayServer(BoundedThreads, http.server.HTTPServer):
    daemon_threads = True
    relay = True


class Broker:
    def __init__(self, directory, upstream=None):
        self.path = directory / "ollama.sock"
        self.server = UnixServer(str(self.path), Handler)
        self.server.slots = threading.BoundedSemaphore(8)
        self.path.chmod(0o600)
        self.server.upstream = upstream or (lambda: http.client.HTTPConnection("127.0.0.1", 11434, timeout=120))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.path.unlink(missing_ok=True)


def relay_main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("missing command")
    server = RelayServer(("127.0.0.1", 11435), Handler)
    server.slots = threading.BoundedSemaphore(8)
    server.upstream = lambda: UnixConnection(args.socket)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        return subprocess.call(command)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    raise SystemExit(relay_main())
