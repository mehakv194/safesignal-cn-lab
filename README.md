# SecureSignal

SecureSignal is a campus cyber incident reporting and investigation app. Students
submit reports and optional evidence, see when the server stores their report,
and follow the investigation in a private conversation. Responders triage and
investigate cases after authenticator verification. Security reviewers review
application alerts without access to private case bodies.

## Local demo

From the repository root, install dependencies with
`python -m pip install -r requirements.txt`, then run
`python scripts/run_app.py --cyber-demo`. Open http://127.0.0.1:5000/.
The first start creates four synthetic accounts with random passwords in
`local/securesignal-demo/fixture.json` and keeps them for later runs. The
only supported demo interface is loopback; never upload real evidence there.

| Role | Synthetic email | Password field in fixture |
|---|---|---|
| Student | 0000000001@mail.jiit.ac.in | student |
| Second student | 0000000002@mail.jiit.ac.in | other-student |
| Cyber responder | 0000000003@mail.jiit.ac.in | responder |
| Security reviewer | 0000000004@mail.jiit.ac.in | reviewer |

Scan the authenticator QR when signing in as a responder or reviewer for the
first time; save the one-time recovery codes offline. See the
[setup, threat model, migration, and demonstration guide](docs/SECURESIGNAL.md).

The original classroom networking and NS2 materials were retained as historical
examples. The isolated networking preview still runs with
`python scripts/run_app.py --classroom-demo`; it does not share the cyber
demo database and its controls are not part of SecureSignal.
