import random
import threading


def backoff(attempt):
    return min(30.0, 0.5 * 2 ** min(max(attempt - 1, 0), 6)) * random.uniform(0.8, 1.0)


class Worker:
    """One worker per outbox; independent of browser lifetime."""
    def __init__(self, outbox, call, identity=None):
        self.outbox, self.call = outbox, call
        self.stop = threading.Event()
        self.identity = identity
        self.outbox.recover()

    def tick(self):
        if self.identity:
            self.identity.reconcile(self.outbox)
        for row in self.outbox.rows():
            if self.stop.is_set():
                return
            aid, state = row['alert_id'], row['status']
            if self.identity and not row['owner_user_id']:
                continue  # Legacy shared records remain restricted; never assign a student.
            if row['incident_state'] == 'RESOLVED':
                continue
            if state == 'QUEUED' and not self.outbox.claim(aid):
                continue
            if state not in ('QUEUED', 'SERVER_RECEIVED','RESPONDER_ACKNOWLEDGED'):
                continue
            try:
                reply = self.call('SUBMIT_ALERT', row['alert']) if state == 'QUEUED' else self.call('GET_STATUS', {'alert_id': aid})
                if reply['status'] == 'OK':
                    self.outbox.confirmed(aid, reply)
                elif state == 'QUEUED':
                    self.outbox.failed(aid, backoff(row['attempt_count'] + 1), reply['code'])
            except (OSError, EOFError, ValueError):
                if state == 'QUEUED':
                    self.outbox.failed(aid, backoff(row['attempt_count'] + 1), 'CONNECTION_FAILED')

    def run(self):
        while not self.stop.is_set():
            self.tick()
            self.stop.wait(1)
