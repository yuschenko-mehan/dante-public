import base64
import hashlib
import os
import socket
import struct
import threading
import urllib.parse

class WebSocket:
    def __init__(self, sock: socket.socket, leftover: bytes = b""):
        self.sock = sock
        self._buf = leftover  # bytes that arrived together with the handshake answer
        self._recv_lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._closed = False

    def _send_frame(self, opcode: int, data: bytes) -> None:
        """Every client frame is masked (RFC 6455, 5.3) — data, ping/pong and close alike."""
        with self._send_lock:
            header = bytearray([0x80 | opcode])
            length = len(data)
            if length < 126:
                header.append(0x80 | length)
            elif length < (1 << 16):
                header.append(0x80 | 126)
                header.extend(struct.pack('>H', length))
            else:
                header.append(0x80 | 127)
                header.extend(struct.pack('>Q', length))
            mask = os.urandom(4)
            header.extend(mask)
            self.sock.sendall(bytes(header) + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def send_text(self, text: str):
        self._send_frame(0x1, text.encode('utf-8'))

    def recv_text(self) -> str:
        fragments = []
        while True:
            b1, b2 = self._recv_exact(2)
            fin = bool(b1 & 0x80)
            opcode = b1 & 0x0F
            masked = bool(b2 & 0x80)
            length = b2 & 0x7F
            if length == 126:
                length = struct.unpack('>H', self._recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack('>Q', self._recv_exact(8))[0]
            if masked:
                mask = self._recv_exact(4)
            else:
                mask = None
            payload = self._recv_exact(length) if length else b''
            if masked:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            # handle control frames
            if opcode == 0x8:  # close
                self._closed = True
                raise ConnectionError("WebSocket closed")
            if opcode == 0x9:  # ping
                # respond with pong same payload
                self._send_pong(payload)
                continue
            if opcode == 0xA:  # pong
                continue
            # data frames
            if opcode == 0x1 or opcode == 0x0:  # text or continuation
                fragments.append(payload)
                if fin:
                    message = b''.join(fragments).decode('utf-8')
                    fragments.clear()
                    return message
                else:
                    continue
            # ignore other opcodes
    def _send_pong(self, payload: bytes):
        self._send_frame(0xA, payload)

    def close(self):
        if self._closed:
            return
        try:
            self._send_frame(0x8, b"")  # masked close frame
        except OSError:
            pass
        self.sock.close()
        self._closed = True

    def _recv_exact(self, n: int) -> bytes:
        buf, self._buf = self._buf[:n], self._buf[n:]
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("socket closed")
            buf += chunk
        return buf

def connect(url: str, timeout: float = 10) -> WebSocket:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'ws':
        raise ValueError("Only ws:// URLs are supported")
    host = parsed.hostname
    port = parsed.port or 80
    path = parsed.path or '/'
    if parsed.query:
        path += '?' + parsed.query
    sock = socket.create_connection((host, port), timeout)
    # handshake
    key = base64.b64encode(os.urandom(16)).decode()
    request = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    )
    sock.sendall(request.encode('utf-8'))
    # read response headers
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("Handshake failed")
        resp += chunk
    header, leftover = resp.split(b"\r\n\r\n", 1)
    lines = header.decode('latin-1').split("\r\n")
    status = lines[0]
    if not status.startswith("HTTP/1.1 101"):
        raise ConnectionError(f"Bad handshake status: {status}")
    hdr_dict = {}
    for line in lines[1:]:
        if ':' in line:
            k, v = line.split(':', 1)
            hdr_dict[k.strip().lower()] = v.strip()
    accept = hdr_dict.get('sec-websocket-accept')
    if not accept:
        raise ConnectionError("Missing Sec-WebSocket-Accept")
    expected = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
    if accept != expected:
        raise ConnectionError("Invalid Sec-WebSocket-Accept")
    return WebSocket(sock, leftover)
