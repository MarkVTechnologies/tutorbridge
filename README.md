# TutorBridge

A managed, trust-first home-tutoring marketplace for Nigerian families and teachers (see `TutorBridge_PRD.docx`, v1.0).

```
client/   React 19 + Vite + TypeScript + Tailwind — compiled to static files (no Node.js on the server)
server/   Django 5.2 LTS + Django REST Framework — MySQL in production, SQLite locally
```

The PRD specifies server-rendered Django templates; to keep client and server in separate folders, the
UI is a React app that talks to a Django JSON API on the **same origin** (session cookies + CSRF,
exactly as server-rendered pages would). It is built locally and served by Django/WhiteNoise or
Apache, so cPanel still only needs Python.

## Run locally

```bash
# Server (Python 3.12+)
cd server
python -m venv .venv && .venv/Scripts/activate      # Windows; use .venv/bin/activate on macOS/Linux
pip install -r requirements-dev.txt
cp .env.example .env                               # DEBUG on, fake payment gateway, console SMS/email
python manage.py migrate
python manage.py createcachetable
python manage.py seed_demo                         # reference data + demo accounts (DEBUG only)
python manage.py runserver 127.0.0.1:8000

# Client (Node 20+)
cd client
npm install
npm run dev                                        # http://localhost:5173, proxies /api to :8000

# Background jobs (emails/SMS appear in the server console)
python manage.py cron minute
```

Demo accounts (password `DemoPass!2026`): `parent@`, `tobi@`, `ngozi@`, `aisha@`, and staff
`admin@`, `vetting@`, `ops@`, `finance@`, `finance2@`, `safety@` — all `@tutorbridge.test`.
Staff must set up an authenticator app at first sign-in.

With `PAYMENT_GATEWAY=fake`, checkout redirects to a local test page that simulates the gateway
and sends a signed webhook to the server — the same path real Paystack payments take.

### Tests

```bash
cd server && python manage.py test tests           # 220+ tests: ledger, payments, bookings, policies, permissions
python -m coverage run manage.py test tests && python -m coverage report   # ~92% on payments/bookings/accounts/trust
cd client && npm run typecheck
```

The suite passes on both SQLite and MariaDB 10.11 (strict mode, utf8mb4). To run it against MySQL/MariaDB,
point the `DB_*` variables at a server where the app user may create `test_<DB_NAME>`:

```bash
DB_ENGINE=mysql DB_HOST=127.0.0.1 DB_PORT=3306 DB_NAME=tutorbridge DB_USER=tutorbridge DB_PASSWORD=... python manage.py test tests
```

**Dates and time zones.** The app does not need MySQL's time-zone tables (often missing on cPanel).
Never use Django's `__date` / `Trunc*` lookups — they call `CONVERT_TZ()`, which returns NULL without those
tables and silently matches nothing. Use `core.dates.day_start()` / `day_range()` to filter by Lagos days.

## What's built (PRD Must requirements)

| Area | Highlights |
|---|---|
| Accounts (AUTH) | Parent/tutor signup, email link + SMS OTP verification, email-or-phone login, 30-min single-use reset, 5-strike/15-min lockout, mandatory TOTP 2FA for staff (optional for others), role + granular permission RBAC, 8h staff idle timeout |
| Tutor vetting (TUT) | 12-step save-and-resume onboarding, subjects × levels matrix, areas + travel distance, availability grid, rate bands, private uploads (type-sniffed, images re-encoded, outside web root), NIN+selfie via KYC adapter with manual-review fallback, bank name-match, timed subject tests from a question bank, interview slots, referee/guarantor secure-link forms, safeguarding course + e-signed agreement, vetting dashboard with per-check decisions, status history with reasons, annual re-verification |
| Requests & matching (REQ) | Children, lesson requests, hard filters + weighted scoring (admin-tunable), new-tutor boost, ops review/edit/invite/publish shortlist, status tracking, 24h SLA alerts |
| Booking (BKG) | Trial or packages, recurring weekly slots, double-booking + travel-buffer guard, 12h accept or auto-offer to next shortlisted tutor, policy-driven cancel/reschedule, tutor replacement carrying package balance |
| Lessons (LSN) | Per-lesson check-in/out codes visible only to the parent, mobile lesson page, optional GPS stamp, required lesson note, auto-confirm after 48h, late/no-show detection, monthly progress-report PDF |
| Payments (PAY) | Paystack (primary) / Flutterwave (switchable) hosted checkout; credit only on HMAC-verified webhook + server-side verify; raw webhooks stored and processed idempotently; append-only double-entry ledger in kobo; per-lesson escrow states; wallet; tiered commission; receipts PDF; daily reconciliation |
| Payouts (OUT) | Earnings dashboard, weekly batch above threshold, maker-checker approval with fresh TOTP, transfers + webhook settlement, failed-transfer return and retry, 48h hold + OTP on bank change, monthly statement PDF |
| Messaging (MSG) | Booking-gated threads, contact masking (numbers, emails, links, handles, spelled-out digits), repeat-attempt flagging, staff view of originals, email/SMS/in-app notifications with editable templates and preferences |
| Trust (REV/SAF) | Reviews only after confirmed lessons, private tutor→parent ratings, moderation; disputes freezing payout with refund/partial/reject; urgent safety button alerting safety officers; suspend/ban with booking reassignment; strikes; reliability score and Verified/Gold/Elite tiers |
| Admin (ADM) | KPI dashboard, settings for every fee/policy, rate bands, subjects/areas, user search + activity history, immutable audit log, CSV exports, FAQ and blog editor |
| Phase 2 | Package auto-renewal with saved cards (BKG-06), promo codes and referral credits (PAY-10), private calendar feed (BKG-05), Sentry + daily health email + staff health panel |
| Phase 3 (pilot) | Address autocomplete (Nominatim, or Google with `GOOGLE_MAPS_API_KEY`) with real-distance matching and check-in distance flags; interview confirmations + 24h/1h reminders (TUT-10); online lesson links limited to Meet/Zoom/Teams/Whereby with a Join button 15 min before (LSN-07); **Pilot reports** at `/staff/reports` — PRD §20 scorecard vs targets, weekly trends, parent cohort retention, fill rate by area, CSV (ADM-07) |
| Website (WEB) | Home, how it works, safety, pricing, FAQ, contact, blog, legal drafts, tutor search + profiles, subject × area SEO pages, PWA manifest + service worker |

## Not done yet / needs a decision

- **KYC provider** — adapter is in `server/vetting/kyc.py`; the default `manual` provider routes every NIN check to the vetting team until Prembly/Dojah/VerifyMe/Smile ID is chosen (PRD decision #5).
- **Escrow structure** — the ledger holds funds per the PRD; confirm with a fintech lawyer whether gateway split/sub-accounts or a licensed escrow partner is required (decision #8).
- **Not yet built**: Google sign-in, WhatsApp notifications, ClamAV scanning, withholding tax, NPS surveys (the one PRD §20 metric the reports can't compute yet). Legal pages are drafts.
- Termii sender ID registration, SPF/DKIM/DMARC, and gateway live keys.

## Deploy on cPanel (PRD §17)

1. **Build the client locally**: `cd client && npm ci && npm run build` → `client/dist/` (commit it on the release branch or upload it).
2. **cPanel → Setup Python App**: Python 3.12, app root outside `public_html` (e.g. `~/tutorbridge/server`), startup file `passenger_wsgi.py`, entry point `application`.
3. **Database**: in cPanel → MySQL Databases create the database (utf8mb4) and a user with privileges on that
   database only. Time-zone tables are not required.
4. **Environment variables** (Python app screen): everything in `server/.env.example` with production values — `DJANGO_DEBUG=0`, a long `DJANGO_SECRET_KEY`, `DB_ENGINE=mysql` + credentials, `FIELD_ENCRYPTION_KEYS`, `PAYMENT_GATEWAY=paystack`, gateway keys, `SMS_PROVIDER=termii`, SMTP, `SITE_URL=https://yourdomain`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `PRIVATE_MEDIA_ROOT` (outside `public_html`), `CLIENT_DIST_DIR`.
5. **Over SSH**: activate the virtualenv, `pip install -r requirements.txt`, back up the DB, then
   `python manage.py migrate && python manage.py createcachetable && python manage.py seed_reference && python manage.py collectstatic --noinput`, then `touch tmp/restart.txt`.
6. **First admin**: `python manage.py shell -c "from accounts.models import User; User.objects.create_superuser('you@domain', '+234…', 'strong-password', first_name='…', last_name='…')"` — sign in and set up 2FA.
7. **Webhooks**: Paystack → `https://yourdomain/api/payments/webhooks/paystack/`; Flutterwave → `/api/payments/webhooks/flutterwave/` (set the secret hash).
8. **Cron jobs** (cPanel → Cron Jobs; use the virtualenv's python):
   ```
   * * * * *    cd ~/tutorbridge/server && ~/virtualenv/tutorbridge/server/3.12/bin/python manage.py cron minute
   */5 * * * *  … manage.py cron five      # offers, reminders, late/no-show, SLA
   0 * * * *    … manage.py cron hourly    # auto-confirm lessons, release escrow
   0 2 * * *    … manage.py cron daily     # reconciliation, ratings/reliability, retention
   0 18 * * 4   … manage.py cron weekly    # prepare payout batch for Friday approval
   0 3 1 * *    … manage.py cron monthly   # re-verification and review reminders
   ```
9. **Monitoring**: point UptimeRobot at `/api/health/` — it returns 503 if the job queue hasn't run in 10 minutes. Set `SENTRY_DSN` for error tracking (no personal data is sent). Super admins get a daily health email after the 02:00 run, and the staff dashboard shows the same checks live.
