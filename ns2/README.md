# Independent NS2 wired experiment — NOT RUN on this Windows host

The Python application does not run inside NS2. These scripts simulate a separate
four-node wired TCP/Reno + FTP topology. No NS2 results are bundled or invented.
Use an authorized Linux/WSL lab with NS2 installed (`ns`, not ns-3).
For Debian/Ubuntu lab environments, install through the distribution package
manager (`sudo apt update`, `sudo apt install ns2`), subject to local availability.

From repository root:

```sh
ns ns2/baseline.tcl
ns ns2/impaired.tcl
python ns2/analyze.py artifacts/ns2/baseline.tr > artifacts/ns2/baseline.csv
python ns2/analyze.py artifacts/ns2/impaired.tr > artifacts/ns2/impaired.csv
```

Baseline bottleneck: 2Mb/s, 10ms, queue 50. Impaired: 0.5Mb/s, 80ms,
queue 3. Both have 10Mb/s, 5ms access links. Impairment changes bandwidth,
delay and queue capacity; it does not prescribe an exact loss percentage.
FTP runs at t=0.5..8.5, trace ends t=10. Denominator 9.5 seconds includes
drain time. Inspect actual trace before interpreting results.

Parser expects **legacy wired trace-all, 12 fields**: event, time, hop source,
hop destination, packet type, bytes, flags, flow ID, source address.port,
destination address.port, sequence, packet ID. Selects TCP flow ID 1; excludes
reverse ACKs. Counts source enqueue IDs, sink receive IDs and unique dropped IDs.
Sink throughput includes TCP packet bytes, not application goodput. Drop ratio
is packet IDs dropped / IDs emitted; TCP retransmissions are separate packets,
so this is not application alert failure. In-flight packets at cutoff need not
be drops. Delay only pairs identifiable source and sink packet IDs; empty
samples are N/A (empty CSV cells). Rejects other trace formats.

Format and API references: [NS2 trace format](https://www.isi.edu/websites/nsnam/ns/doc/node289.html),
[NS2 queue/link commands](https://www.isi.edu/websites/nsnam/ns/doc/node63.html).
Parser fixtures are synthetic unit-test text, not measured simulation evidence.
