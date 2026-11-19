# Phase 2 — Mobile-first product shell

Date: 19 November 2026. Branch: codex/v2-identity-mobile.
Phase 1 commit: c6b99c5. Phase 2 implementation commit: 7229354.
Status: PASS for local implementation and responsive browser acceptance, not public release approval.

## User-visible changes and files

- templates/base.html now chooses shell_v2.html for identity-enabled mode and preserves shell_legacy.html for isolated original lab compatibility. report_dialog.html shares the real existing reporting form.
- templates/student_home.html puts report creation and private cases first, with actual backend reachability and receipt/progress states. It does not invent SafeWalk functionality.
- templates/walks_pending.html and web.py provide an honest My Walks destination marked not yet available; no walk timer/session is created in Phase 2.
- templates/shell_v2.html provides Home/My Walks/Incidents/Profile phone navigation, desktop sidebar, role-specific Lab access, persistent simulation warning, free-host limitation, live action feedback, semantic main and skip link.
- static/mobile.css provides 44px+ interactive targets, 16px inputs, phone card-style incident lists, responsive desk forms, safe-area navigation spacing, bounded dialogs, focus styles, contrast corrections and reduced-motion handling. Existing styles.css retained.
- templates/identity.html adds password confirmation, show/hide password, readable account forms, profile/password change and explicit logout. app.js reports sending/offline truthfully, retains existing safe five-second polling and real chart export.
- templates/welcome.html / hosted.py describe individual accounts in v2 rather than claiming a shared sender queue. Existing legacy landing remains compatible.
- Owner queries/indexes were tightened in web.py and both stores so student outbox reads are scoped in SQL. Original worker still processes the queue independently.
- tests/test_mobile_shell.py adds functional Home/navigation/profile/form/security checks; tests/test_identity.py checks the v2 landing text and password confirmation.
- .env.example and V2_LOCAL_GUIDE.md describe mail configuration, local review, provisioning and rollback without credentials.

## Actual automated tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=C:/Users/mehak/.codex/visualizations/2026/11/18/01a1eef0-be7d-75d1-b1ed-8f0bbffef830/v2-phases12-releasecheck
```

**44 passed in 32.01s**, exit 0. No skips/failures. Earlier Phase 2 integration runs: 42 passed in 28.05s and 44 passed in 30.71s. Final run includes the owner-index/query and landing updates.

`git diff --check` passed (line-ending conversion notices only). No new Linux run or production smoke result claimed here.

## Browser acceptance evidence

Used isolated local/v2-preview with synthetic test accounts and captured local email. Existing user databases and production were not used.

- Home, login and responder incident queue checked at 320, 360, 390, 430, 768, 1024 and 1440 CSS pixels. Screenshots: evidence/phase2-home-*.png, phase2-login-*.png, phase2-queue-*.png.
- Read-only DOM measurements stored in evidence/phase2-responsive-checks.json: no page horizontal overflow; final Home/login/queue checks show no visible interactive links/buttons under 44×44px; login input font sizes 16px. Hidden dialogs and skip-link offscreen positioning are excluded as appropriate.
- Initial review found narrow Sign in/Next/Clear links, short incident title links and inherited dark text on green panels; corrected CSS and recaptured affected login/queue widths. These are resolved observations, not accepted defects.
- Keyboard Tab from enrollment email focused password with a visible solid outline. Show/hide password toggled the input type. Account forms use native labels/autocomplete and status/error semantics. Reduced-motion styles inspected.
- Real UI journey: individual student report → server receipt → Medical Team acknowledgment → start → resolve → student Home shows RESOLVED. The distinct delivery field remained RESPONDER_ACKNOWLEDGED, as intended. Proof: evidence/phase2-resolved-phone.png and phase2-student-final.png.
- Local browser account session already established; UI reporting was on synthetic data only. Automated tests cover fresh signup/verification, wrong role, owner-ID guessing, CSRF and revocation.

This is responsive desktop-browser testing, not a real iOS/Android keyboard or screen-reader certification. No chat composer exists until Phase 4, so that keyboard gate is pending with chat. Automated global WCAG certification and low-end-device performance are not claimed; Phase 6 keeps broader system QA. The shell's relevant controls, navigation and form layout passed the recorded checks.

## Acceptance status

- PASS: usable student Home with actions before charts; bottom navigation and desktop navigation; real private incident list, profile and onboarding.
- PASS: responder report/assignment/start/resolve retained and browser exercised; Evidence/Network Lab remain available under correct roles.
- PASS: responsive widths, input sizing, measured target sizes, no page overflow, focus/password behavior, security headers/CSRF tests.
- PASS: original networking suite preserved; no fake receipt or offline-delivery success.
- PASS: migration remains additive; existing backups/restore tested in Phase 1; this phase has no destructive data changes.
- Pending: actual SMTP/inbox delivery, real-device keyboard/screen-reader review and staging/release gate. Shared proxy-IP rate limits need staging review; the app intentionally does not trust arbitrary forwarded client IP headers.
- Pending by scope: SafeWalk (3), Incident Room/closure feedback (4), local Trust Lab (5), integrated hardening (6), release approval (7). No paid service or native app added.

## Rollback and deployment

Keep feature code on this branch; restore the previous accepted implementation commit only with matching data compatibility checks. Legacy templates are a local-lab fallback, not public shared-auth fallback. Stop all writers and restore both pre-v2 database backups into an isolated directory before any operational switch; never delete new records or reassign legacy ownership to simplify rollback. Hosted backups are ephemeral too.

Phase 0 docs published to main at 2202136; no runtime redeployment was necessary for documentation. Phase 1 and 2 are NOT merged into main or deployed. A public deployment requires a separate explicit approval and release checks. User approval to begin Phase 3: PENDING.
