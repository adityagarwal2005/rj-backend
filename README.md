# RajwadiTukda Backend

Django + Django REST Framework backend for RajwadiTukda — an online store for
premium chocolate infused with Rajasthani flavors. Postgres is hosted on Supabase;
product images are stored in Supabase Storage; transactional email is sent
via Resend. The frontend (React) talks to this backend only through the
documented REST API in [`docs/API.md`](docs/API.md).

## Why this structure

```
backend/
├── config/                # Django project: settings, root urls, wsgi/asgi
│   └── settings/
│       ├── base.py        # shared settings (DB, DRF, JWT, CORS, storage)
│       ├── development.py # local overrides (DEBUG, console email fallback)
│       └── production.py  # security headers, whitenoise
├── apps/
│   ├── core/               # cross-cutting code shared by every app
│   │   ├── response.py     # api_success()/api_error() envelope helpers
│   │   ├── exceptions.py   # turns every DRF error into the same envelope
│   │   ├── pagination.py   # standard paginated response shape
│   │   ├── permissions.py  # IsAdmin / IsAdminOrReadOnly / IsOwnerOrAdmin
│   │   ├── models.py       # TimeStampedModel / UUIDPrimaryKeyModel bases
│   │   └── storage.py      # Supabase (S3-compatible) file storage backend
│   ├── users/              # custom User model (role: customer/admin), JWT auth
│   ├── products/           # Category, Product, ProductImage + catalog API
│   ├── orders/              # Address, Cart, CartItem, Order, OrderItem + checkout
│   ├── payments/            # Payment model + gateway-agnostic service interface
│   └── notifications/       # in-app Notification + email sending
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
cd backend
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

## Environment variables

See `.env.example` for the full list. Never commit `.env` — it's in
`.gitignore`. In particular:

- `DATABASE_URL` — Supabase Postgres connection string (Session Pooler URI recommended for serverless-style deploys).
- `SUPABASE_STORAGE_*` — Supabase Storage's S3-compatible credentials, used for product images.
- `RESEND_API_KEY` — from [resend.com/api-keys](https://resend.com/api-keys). If unset in development, email falls back to the console backend (prints to stdout instead of sending).
- `SECRET_KEY` — generate a fresh one for production, never reuse the dev default.

## What's deliberately not built yet

These were scoped out for now but the architecture doesn't need to change to add them later:

- **Redis caching** — plug in `django-redis` and cache `apps.products.services.visible_products_queryset`.
- **Celery** — `apps/notifications/services.py` functions are already plain, side-effect functions (including `send_email`, which calls Resend synchronously); wrap them with `@shared_task` and call `.delay()` instead of calling directly.
- **Razorpay** — `apps/payments/services.py` has a `RazorpayGateway` class with the two methods (`create_payment_intent`, `verify_payment`) stubbed out; fill them in with the Razorpay SDK.
- **Docker / CI/CD** — `config/settings/production.py` already assumes a reverse proxy (Nginx) terminating TLS and `gunicorn` serving the app; add a `Dockerfile` + `docker-compose.yml` when ready to containerize.
