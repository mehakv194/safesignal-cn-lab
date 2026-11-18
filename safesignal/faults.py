"""Opt-in app-layer faults only; never modifies OS networking."""
import json
import os
from pathlib import Path

PRESETS = ('normal', 'delay', 'ack_lost', 'disconnect')


class Faults:
    def __init__(self, path, enabled=False):
        self.path, self.enabled = Path(path), enabled

    def preset(self):
        if not self.enabled:
            return 'normal'
        try:
            value = json.loads(self.path.read_text())['preset']
            return value if value in PRESETS else 'normal'
        except FileNotFoundError:
            return 'normal'

    def set(self, preset):
        if not self.enabled or preset not in PRESETS:
            raise ValueError('Faults disabled or invalid preset')
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'preset': preset}))
        os.replace(temporary, self.path)
