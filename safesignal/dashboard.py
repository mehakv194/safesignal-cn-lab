"""Dashboard aggregates calculated from actual incident records."""
from datetime import datetime, timedelta, timezone

from .models import CATEGORIES, INCIDENT_STATES


def summarize(rows):
    days = [(datetime.now(timezone.utc).date()-timedelta(days=i)).isoformat() for i in range(6,-1,-1)]
    daily = [sum(r['created_at'][:10] == day for r in rows) for day in days]
    states = {state:sum(r.get('incident_state','REPORTED') == state for r in rows) for state in INCIDENT_STATES}
    categories = {category:sum(r.get('category','SAFETY') == category for r in rows) for category in CATEGORIES}
    total = len(rows)
    peak = max(daily, default=0) or 1
    points = ' '.join(f'{35+i*65},{150-count/peak*110:.1f}' for i,count in enumerate(daily))
    return dict(total=total, active=total-states['RESOLVED'], resolved=states['RESOLVED'],
                critical=sum(r['severity']=='CRITICAL' and r.get('incident_state')!='RESOLVED' for r in rows),
                states=states,categories=categories,daily=daily,days=days,points=points,
                resolution_percent=round(states['RESOLVED']/total*100) if total else 0,
                week_total=sum(daily), peak=max(daily,default=0))
