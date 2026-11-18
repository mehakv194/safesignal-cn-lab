from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4

SEVERITIES = ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')


def now():
    return datetime.now(timezone.utc).isoformat()


def validate_alert(p):
    fields = {'alert_id', 'severity', 'description', 'location', 'created_at'}
    if not isinstance(p, dict) or set(p) != fields:
        raise ValueError('Invalid alert fields')
    if any(not isinstance(v, str) for v in p.values()):
        raise ValueError('String fields required')
    if str(UUID(p['alert_id'])) != p['alert_id']:
        raise ValueError('Canonical UUID required')
    if p['severity'] not in SEVERITIES:
        raise ValueError('Invalid severity')
    if not 10 <= len(p['description'].strip()) <= 300 or len(p['location']) > 120:
        raise ValueError('Invalid description or location length')
    created = datetime.fromisoformat(p['created_at'])
    if created.tzinfo is None or created.utcoffset() != timedelta(0):
        raise ValueError('UTC timestamp required')
    if created > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError('Timestamp in future')
    return p


def new_alert(severity, description, location=''):
    return validate_alert(dict(alert_id=str(uuid4()), severity=severity,
                               description=description, location=location, created_at=now()))
