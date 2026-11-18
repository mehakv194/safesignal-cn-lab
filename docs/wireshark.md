# Wireshark / TLS inspection — NOT RUN here

Wireshark is unavailable on PATH in this environment. Install from the official
vendor on your own authorized lab device; on Windows select Npcap loopback
support. Capture only synthetic traffic you are authorized to inspect.

1. Start SafeSignal. Select the loopback adapter carrying 127.0.0.1 traffic.
2. Set capture filter `tcp port 9443` before starting capture.
3. Submit one synthetic alert and acknowledge it. Stop capture immediately.
4. Display filter `tcp.port == 9443`. Inspect TCP connection establishment,
   TLS handshake and encrypted application-data records. TLS session resumption
   can change handshake details. No readable alert description should appear in
   protected records without deliberately configured session-key logging.
5. Inspect `tcp.analysis.retransmission` only if actual transport retransmissions
   occurred. An app-layer lost receipt is a closed stream after server commit;
   the sender opens another TLS connection. It is not a dropped TCP segment.
6. Record OS, adapter, Wireshark version, capture time, filters and synthetic
   test steps in your report. Do not commit captures or session keys.

Visible ports/timing/packet lengths remain metadata; ciphertext alone does not
prove server persistence, role correctness, production security or human action.
Use SQLite audit and integration checks for those application facts.
Optional lab commands: `ping 127.0.0.1`, `netstat -ano` (Windows),
`ss -ltn` (Linux). Never capture unrelated system traffic automatically.

Reference: [Wireshark User's Guide](https://www.wireshark.org/docs/wsug_html_chunked/).
