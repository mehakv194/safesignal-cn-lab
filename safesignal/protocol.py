"""Bounded JSON messages over a connected socket."""
import json
import struct

MAX_FRAME = 16 * 1024


def recv_exact(sock, size):
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise EOFError('Connection closed before complete frame')
        data.extend(chunk)
    return bytes(data)


def receive(sock):
    size, = struct.unpack('!I', recv_exact(sock, 4))
    if not 0 < size <= MAX_FRAME:
        raise ValueError('Invalid frame size')
    obj = json.loads(recv_exact(sock, size))
    if not isinstance(obj, dict):
        raise ValueError('Object required')
    return obj


def send(sock, obj):
    data = json.dumps(obj, allow_nan=False, ensure_ascii=False).encode('utf-8')
    if not 0 < len(data) <= MAX_FRAME:
        raise ValueError('Invalid frame size')
    sock.sendall(struct.pack('!I', len(data)) + data)
