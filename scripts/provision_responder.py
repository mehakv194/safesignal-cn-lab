"""Restricted local maintainer operation, never an HTTP endpoint."""
import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from safesignal.identity import Identity
from safesignal.models import RESPONSE_TEAMS

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('email')
    parser.add_argument('--team',required=True,choices=RESPONSE_TEAMS)
    parser.add_argument('--legacy-demo',action='store_true')
    args=parser.parse_args()
    identity=Identity(Path(os.environ['SAFESIGNAL_DATA_DIR'])/'server.sqlite',os.environ['SAFESIGNAL_SESSION_SECRET'])
    identity.provision(args.email,args.team,args.legacy_demo)
    print('Verified demo account provisioned; previous sessions revoked.')
