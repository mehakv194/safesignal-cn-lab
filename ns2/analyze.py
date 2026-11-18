"""Parse legacy 12-column wired trace-all format (not NAM/wireless traces)."""
import argparse
import csv
from pathlib import Path
import statistics


def analyze(lines, duration=9.5):
    if duration <= 0:
        raise ValueError('Positive observation duration required')
    sent, received, dropped = {}, {}, set()
    for number, line in enumerate(lines, 1):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        fields = line.split()
        if len(fields) != 12 or fields[0] not in ('+', '-', 'r', 'd'):
            raise ValueError(f'Unsupported trace format at line {number}')
        event, stamp, src, dst, kind, size, flags, fid, source, destination, seq, pid = fields
        stamp, size = float(stamp), int(size)
        if kind != 'tcp' or fid != '1':
            continue
        if event == '+' and src == '0':
            sent.setdefault(pid, stamp)
        if event == 'r' and dst == '3':
            received.setdefault(pid, (stamp, size))
        if event == 'd':
            dropped.add(pid)
    delays = [stamp - sent[pid] for pid, (stamp, size) in received.items() if pid in sent and stamp >= sent[pid]]
    return dict(source_packet_ids=len(sent), sink_packet_ids=len(received),
                dropped_packet_ids=len(dropped),
                packet_drop_percent=len(dropped) / len(sent) * 100 if sent else None,
                sink_throughput_bps=sum(size * 8 for stamp, size in received.values()) / duration,
                mean_identifiable_packet_delay_seconds=statistics.mean(delays) if delays else None,
                delay_sample_count=len(delays), observation_seconds=duration)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('trace', type=Path)
    parser.add_argument('--duration', type=float, default=9.5)
    args = parser.parse_args()
    with args.trace.open() as file:
        result = analyze(file, args.duration)
    writer = csv.DictWriter(__import__('sys').stdout, fieldnames=list(result))
    writer.writeheader()
    writer.writerow(result)
