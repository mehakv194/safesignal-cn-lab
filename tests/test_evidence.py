import csv
from pathlib import Path

from safesignal.faults import Faults
from safesignal.metrics import export, summarize
from test_transport import lab


def test_fault_guard_and_delay(lab, tmp_path):
    from safesignal.models import new_alert
    import time
    disabled = Faults(tmp_path / 'off.json')
    assert disabled.preset() == 'normal'
    import pytest
    with pytest.raises(ValueError):
        disabled.set('disconnect')
    faults = Faults(tmp_path / 'on.json', True)
    lab[0].faults = faults
    faults.set('delay')
    started = time.monotonic()
    assert lab[2]('SUBMIT_ALERT', new_alert('LOW', 'TEST ONLY: delayed application response'))['status'] == 'OK'
    assert time.monotonic() - started >= 1.5


def test_real_experiment_and_export(tmp_path, monkeypatch):
    import importlib.util
    from safesignal.tls import create_certificate
    spec = importlib.util.spec_from_file_location('experiments', Path(__file__).resolve().parents[1] / 'scripts/run_experiments.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.chdir(tmp_path)
    create_certificate('certs')
    result = module.run(Path('artifacts/test-run'), count=3)
    assert result['policies']['single_attempt']['received'] == 2
    assert result['policies']['single_attempt']['pending_confirmation'] == 2
    assert result['policies']['retry_dedup']['received'] == 3
    assert result['policies']['retry_dedup']['duplicate_suppressions'] == 1
    with Path('artifacts/test-run/results.csv').open() as f:
        assert len(list(csv.DictReader(f))) == 6
    assert summarize([])['p95_confirmation_seconds'] is None
