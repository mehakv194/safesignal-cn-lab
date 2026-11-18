import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('ns2_analyze', Path(__file__).resolve().parents[1] / 'ns2/analyze.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_synthetic_trace_fixture():
    # Handwritten parser fixture; not a recorded NS2 experiment.
    lines = ['+ 0.5 0 1 tcp 1000 ------- 1 0.0 3.0 0 10',
             'r 0.6 2 3 tcp 1000 ------- 1 0.0 3.0 0 10',
             '+ 0.7 0 1 tcp 1000 ------- 1 0.0 3.0 1 11',
             'd 0.8 1 2 tcp 1000 ------- 1 0.0 3.0 1 11',
             'r 0.9 1 0 ack 40 ------- 1 3.0 0.0 0 12']
    result = module.analyze(lines, 1)
    assert result['packet_drop_percent'] == 50
    assert result['sink_throughput_bps'] == 8000
    assert result['mean_identifiable_packet_delay_seconds'] == pytest.approx(.1)
    assert module.analyze([])['packet_drop_percent'] is None
    with pytest.raises(ValueError):
        module.analyze(['bad trace'])
