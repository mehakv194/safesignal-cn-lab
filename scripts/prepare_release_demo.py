"""Prepare a private Render secret file after verifying each account owner."""
import argparse
import base64
from getpass import getpass
import json
import os
from pathlib import Path
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from argon2 import PasswordHasher
from safesignal.identity import Identity, email_address

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('emails',nargs=2)
args=parser.parse_args()
emails=[email_address(email) for email in args.emails]
if len(set(emails))!=2 or set(emails) & {'0000000001@mail.jiit.ac.in','0000000002@mail.jiit.ac.in'}:
    parser.error('Use two distinct approved JIIT addresses; old shared demo accounts are not eligible.')
hasher=PasswordHasher()
records={}
for email in emails:
    first=getpass(f'New unique password for {email}: ')
    Identity.password(first)
    if first!=getpass('Confirm password: '):
        raise SystemExit('Passwords did not match. No release secrets were written.')
    records[email]=hasher.hash(first)
path=Path('local/release-secrets.env')
path.parent.mkdir(exist_ok=True)
fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w',encoding='utf-8') as file:
    file.write('SECURESIGNAL_MFA_KEY='+base64.b64encode(secrets.token_bytes(32)).decode()+'\n')
    file.write('SECURESIGNAL_RELEASE_DEMO_ACCOUNTS='+json.dumps(records,separators=(',',':'))+'\n')
print(f'Private settings written to {path}. Add the two values to Render Environment. Do not share the file.')
