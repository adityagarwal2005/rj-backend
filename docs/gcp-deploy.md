# Deploying to Google Cloud Run

Replaces the Render free-tier deploy. Cloud Run runs the same Docker image
(see `Dockerfile`), scales to zero when idle (no forced sunset like Render's
free tier), and its free tier (2M requests/month, 360k GB-seconds compute)
comfortably covers a single-SKU store's traffic.

## One-time setup

You need a Google account and a credit card on file (GCP requires billing
enabled even to use the free tier - you won't be charged unless you exceed
it, but Google needs it linked). None of this can be done on your behalf;
it needs your own Google login.

1. **Install the gcloud CLI**: https://cloud.google.com/sdk/docs/install
2. **Log in**: `gcloud auth login`
3. **Create a project** (or use an existing one) at
   https://console.cloud.google.com/projectcreate - note the Project ID
   it gives you (not the display name).
4. **Enable billing** for that project at
   https://console.cloud.google.com/billing - link a billing account.
5. **Point the CLI at your project and enable the APIs it needs**:

```bash
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com
```

## Deploy

Run this from the `rj-backend` directory. `gcloud run deploy --source .`
detects the `Dockerfile`, builds it via Cloud Build, pushes it to Artifact
Registry, and deploys - one command, no separate build/push steps needed.

```bash
gcloud run deploy rajwaditukda-backend \
  --source . \
  --region asia-south1 \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 3 \
  --memory 512Mi \
  --set-env-vars "$(cat <<'EOF' | tr '\n' ',' | sed 's/,$//'
DJANGO_SETTINGS_MODULE=config.settings.production
SECRET_KEY=REPLACE_ME_generate_a_new_one
ALLOWED_HOSTS=rajwaditukda-backend-REPLACE_ME.a.run.app
CORS_ALLOWED_ORIGINS=https://rajwaditukda.in
CSRF_TRUSTED_ORIGINS=https://rajwaditukda.in
DATABASE_URL=REPLACE_ME_same_supabase_url_from_render
SUPABASE_STORAGE_ENDPOINT_URL=REPLACE_ME
SUPABASE_STORAGE_REGION=REPLACE_ME
SUPABASE_STORAGE_BUCKET_NAME=REPLACE_ME
SUPABASE_STORAGE_ACCESS_KEY_ID=REPLACE_ME
SUPABASE_STORAGE_SECRET_ACCESS_KEY=REPLACE_ME
RESEND_API_KEY=REPLACE_ME
DEFAULT_FROM_EMAIL=REPLACE_ME
PAYMENT_UPI_ID=REPLACE_ME
PAYMENT_BANK_ACCOUNT_NAME=REPLACE_ME
PAYMENT_BANK_ACCOUNT_NUMBER=REPLACE_ME
PAYMENT_BANK_IFSC=REPLACE_ME
PAYMENT_BANK_NAME=REPLACE_ME
PAYMENT_WHATSAPP_NUMBER=REPLACE_ME
RAZORPAY_KEY_ID=REPLACE_ME
RAZORPAY_KEY_SECRET=REPLACE_ME
RAZORPAY_WEBHOOK_SECRET=REPLACE_ME
CRON_SECRET=REPLACE_ME
ACCESS_TOKEN_LIFETIME_MINUTES=60
REFRESH_TOKEN_LIFETIME_DAYS=7
EOF
)"
```

All the `REPLACE_ME` values are exactly what's already sitting in your
Render dashboard's Environment tab - copy them over, same values, nothing
to regenerate except `ALLOWED_HOSTS` (see below).

**This is a two-step dance the first time**: the very first deploy needs
*some* value in `ALLOWED_HOSTS`, but you don't know the real `*.run.app`
URL until after that first deploy finishes and prints it. Deploy once with
a placeholder, copy the URL it gives you, then re-run the same command
with the real URL substituted in - updating env vars is instant (no
rebuild).

## Getting your admin login (same trick as Render)

Cloud Run has no interactive shell either, but the `bootstrap_admin`
management command (already in this repo) still works the same way: add
`ADMIN_EMAIL=you@example.com,ADMIN_PASSWORD=your-password` to the
`--set-env-vars` list above (or `gcloud run services update ... --update-env-vars`
to add it without a full redeploy), which reruns it on the next container
start. Remove the var afterward if you don't want the password sitting in
Cloud Run's env var list.

## Custom domain (api.rajwaditukda.in)

```bash
gcloud run domain-mappings create --service rajwaditukda-backend --domain api.rajwaditukda.in --region asia-south1
```

This prints a DNS record (CNAME or A/AAAA) to add at your domain registrar
(GoDaddy) - same as the CNAME you already set up for Render, just pointed
at Cloud Run instead. Once it's live, also add `api.rajwaditukda.in` to
the `ALLOWED_HOSTS` env var alongside the `*.run.app` URL.

## Frontend

Update the frontend's `VITE_API_BASE_URL` (in Vercel's project env vars)
to the new backend URL, then redeploy the frontend on Vercel. No code
changes needed on the frontend side - it's already fully env-driven.

## Redeploying after future code changes

Same one-liner, since it always rebuilds from the current source:

```bash
gcloud run deploy rajwaditukda-backend --source . --region asia-south1
```

(Env vars persist across redeploys unless you change them - no need to
repeat the whole `--set-env-vars` list every time.)

## Cold starts

`--min-instances 0` means Cloud Run kills the container after a few
minutes of no traffic and cold-starts a new one on the next request
(a few seconds of extra latency) - this is what keeps it free. That's
different from Render's free tier, which now suspends the service
entirely until you manually intervene; Cloud Run just cold-starts, no
suspension, no action needed from you. If cold starts ever become
annoying, `--min-instances 1` keeps one instance warm permanently, but
that runs 24/7 and is very likely to incur a small charge instead of
staying fully free.
