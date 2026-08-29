# RajwadiTukda Backend

Django + Django REST Framework backend for RajwadiTukda — an online store for
premium chocolate infused with Rajasthani flavors. Postgres is hosted on Supabase;
product images are stored in Supabase Storage; transactional email is sent
via Resend. The frontend (React) talks to this backend only through the
documented REST API in [`docs/API.md`](docs/API.md).

## Why this structure

```
config/                # Django project: settings, root urls, wsgi/asgi
├── settings/
│   ├── base.py         # shared settings (DB, DRF, JWT, CORS, storage)
│   ├── development.py  # local overrides (DEBUG, console email fallback)
│   └── production.py   # security headers, whitenoise, Cloud Run's TLS proxy
apps/
├── core/               # cross-cutting code shared by every app
│   ├── response.py     # api_success()/api_error() envelope helpers
│   ├── exceptions.py   # turns every DRF error into the same envelope
│   ├── pagination.py   # standard paginated response shape
│   ├── permissions.py  # IsAdmin / IsAdminOrReadOnly
│   ├── models.py       # TimeStampedModel / UUIDPrimaryKeyModel bases
│   └── storage.py      # Supabase (S3-compatible) file storage backend
├── users/              # custom User model (role: customer/admin), JWT + email-OTP auth
├── products/           # Category, Product, ProductImage + catalog API
├── orders/             # Address, Cart, CartItem, Order, OrderItem + checkout
├── payments/           # Payment model + gateway-agnostic service interface (Razorpay live, manual UPI as fallback)
└── notifications/      # in-app Notification + email sending
```

Each app owns `models.py`, `serializers.py`, `services.py`, `views.py`,
`urls.py`, `permissions.py` (where needed), `admin.py`, and `tests.py`.
**Views never contain business logic** — they validate input via a
serializer, call a function in `services.py`, and return `api_success`/
`api_error`. This is what keeps adding a second product, a new payment
gateway, or a new notification channel a matter of adding code, not
rewriting existing code.

## Local setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # fill in your Supabase DB URL + storage keys

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

API is now available at `http://localhost:8000/api/`. Django admin at
`http://localhost:8000/admin/`.

## Running tests

```bash
python manage.py test
```

Tests run against a **local** Postgres, not the Supabase database in your
`.env` — `manage.py` switches to `config/settings/test.py` automatically for
the `test` command. The whole suite finishes in a few seconds; if it starts
taking minutes, something is pointing at a remote database again.

Postgres (not SQLite) because the checkout/stock code uses
`select_for_update()` for row locking. Start one with:

```bash
brew services start postgresql@17
```

Point somewhere else with `TEST_DATABASE_URL` if your local setup differs.

## Environment variables

See `.env.example` for the full list. Never commit `.env` — it's in
`.gitignore`. In particular:

- `DATABASE_URL` — Supabase Postgres connection string (Session Pooler URI recommended for serverless-style deploys).
- `SUPABASE_STORAGE_*` — Supabase Storage's S3-compatible credentials, used for product images.
- `RESEND_API_KEY` — from [resend.com/api-keys](https://resend.com/api-keys). If unset in development, email falls back to the console backend (prints to stdout instead of sending).
- `SECRET_KEY` — generate a fresh one for production, never reuse the dev default.
- `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` / `RAZORPAY_WEBHOOK_SECRET` — live in production; the manual UPI details (`PAYMENT_*`) only surface as a fallback if these are blank.

## Deployment

Runs on Google Cloud Run from the `Dockerfile` in this repo, auto-deployed
by a Cloud Build trigger on push to `main`. See
[`docs/gcp-deploy.md`](docs/gcp-deploy.md) for the full setup (this project
migrated off Render, whose free tier suspends idle services).

## What's deliberately not built yet

These were scoped out for now but the architecture doesn't need to change to add them later:

- **Redis caching** — plug in `django-redis` and cache `apps.products.services.visible_products_queryset`.
- **Celery** — `apps/notifications/services.py` functions are already plain, side-effect functions (including `send_email`, which calls Resend synchronously); wrap them with `@shared_task` and call `.delay()` instead of calling directly.
