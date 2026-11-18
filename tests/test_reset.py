from pathlib import Path
import runpy


def test_reset_preserves_databases_and_credentials(tmp_path):
    reset = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/reset_demo.py'))
    for name in ('server.sqlite', 'outbox.sqlite', 'config.json'):
        (tmp_path / name).write_text('synthetic fixture')
    archive = reset['archive_databases'](tmp_path)
    assert (archive / 'server.sqlite').read_text() == 'synthetic fixture'
    assert (archive / 'outbox.sqlite').read_text() == 'synthetic fixture'
    assert (tmp_path / 'config.json').read_text() == 'synthetic fixture'
    assert reset['archive_databases'](tmp_path) is None
