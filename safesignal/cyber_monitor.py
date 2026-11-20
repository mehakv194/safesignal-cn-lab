"""Sliding-window application security rules over pseudonymous signals."""
import hmac
import json

RULES = {
    'LOGIN_ACCOUNT': (5,60,300), 'LOGIN_SOURCE': (4,120,300), 'CASE_ACCESS': (4,60,300),
    'RESPONDER_ACTION': (4,60,300), 'EVIDENCE_DOWNLOAD': (15,60,300),
}
NEXT = {'OPEN':('ACKNOWLEDGED','FALSE_POSITIVE'), 'ACKNOWLEDGED':('INVESTIGATING','FALSE_POSITIVE'),
        'INVESTIGATING':('RESOLVED','FALSE_POSITIVE')}


class Monitor:
    def __init__(self, identity, rules=None):
        self.identity = identity
        self.rules = RULES | (rules or {})
        if set(self.rules)!=set(RULES) or any(len(v)!=3 or any(type(n)!=int or n<1 for n in v)
                                               or v[0]>1000 or v[1]>86400 for v in self.rules.values()):
            raise ValueError('Invalid security rule configuration.')
        with identity.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS security_signals(
                    id INTEGER PRIMARY KEY, rule TEXT NOT NULL, subject TEXT NOT NULL,
                    account TEXT NOT NULL, actor TEXT NOT NULL, target TEXT NOT NULL, stamp REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS signal_stamp ON security_signals(stamp);
                CREATE INDEX IF NOT EXISTS signal_scope ON security_signals(rule,subject,stamp);
                CREATE TABLE IF NOT EXISTS security_alerts(
                    id INTEGER PRIMARY KEY, rule TEXT NOT NULL, subject TEXT NOT NULL,
                    first REAL NOT NULL,last REAL NOT NULL,window INTEGER NOT NULL,
                    observations INTEGER NOT NULL,threshold INTEGER NOT NULL,sample TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'OPEN');
                CREATE INDEX IF NOT EXISTS alert_scope ON security_alerts(rule,subject,last);
                CREATE TABLE IF NOT EXISTS security_review(
                    id INTEGER PRIMARY KEY,alert_id INTEGER NOT NULL,actor TEXT NOT NULL,
                    status TEXT NOT NULL, reason TEXT NOT NULL,stamp REAL NOT NULL);
                INSERT OR IGNORE INTO schema_migrations VALUES(8);
            """)

    def private(self, value):
        return hmac.digest(self.identity.key, ('monitor:'+value).encode(),'sha256').hex()[:32]

    def event(self, rule, subject, account='', actor='', target=''):
        threshold, window, cooldown = self.rules[rule]
        subject, account = self.private(subject), self.private(account) if account else ''
        now = self.identity.clock()
        with self.identity.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO security_signals(rule,subject,account,actor,target,stamp) VALUES(?,?,?,?,?,?)',
                       (rule,subject,account,actor,target,now))
            db.execute('DELETE FROM security_signals WHERE stamp<? OR id<=(SELECT max(id)-20000 FROM security_signals)',
                       (now-max(v[1] for v in self.rules.values()),))
            rows = db.execute("""SELECT account,actor,target,stamp FROM security_signals
                WHERE rule=? AND subject=? AND stamp>? ORDER BY stamp DESC,id DESC LIMIT 1000""",
                (rule,subject,now-window)).fetchall()
            count = len({r['account'] for r in rows if r['account']}) if rule=='LOGIN_SOURCE' else len(rows)
            if count<threshold:
                return
            old=db.execute('SELECT id,status FROM security_alerts WHERE rule=? AND subject=? AND last>? ORDER BY id DESC LIMIT 1',
                           (rule,subject,now-cooldown)).fetchone()
            sample=json.dumps([dict(r) for r in rows[:10]])
            if not old:
                db.execute("""INSERT INTO security_alerts(rule,subject,first,last,window,observations,threshold,sample)
                              VALUES(?,?,?,?,?,?,?,?)""",(rule,subject,rows[-1]['stamp'],now,window,count,threshold,sample))
            elif old['status'] not in ('RESOLVED','FALSE_POSITIVE'):
                db.execute('UPDATE security_alerts SET last=?,observations=?,sample=? WHERE id=?',(now,count,sample,old['id']))

    def login(self, account, source):
        if account:
            self.event('LOGIN_ACCOUNT',account,account)
            self.event('LOGIN_SOURCE',source,account)

    def review(self, aid, actor, state, reason):
        with self.identity.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT status FROM security_alerts WHERE id=?',(aid,)).fetchone()
            if not row or state not in NEXT.get(row['status'],()):
                raise ValueError('Invalid alert transition.')
            db.execute('UPDATE security_alerts SET status=? WHERE id=?',(state,aid))
            db.execute('INSERT INTO security_review(alert_id,actor,status,reason,stamp) VALUES(?,?,?,?,?)',
                       (aid,actor,state,reason,self.identity.clock()))
