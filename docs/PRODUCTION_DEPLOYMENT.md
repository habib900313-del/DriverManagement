# Production preparation (Ubuntu 24.04)

This is a deployment template, not a completed or tested VPS deployment. The
development settings and `scripts/start-backend.sh` /
`scripts/start-frontend.sh` remain available for local use.

## Runtime layout

- Nginx serves the built `frontend/dist` SPA and Django's collected static
  files, terminates HTTPS, and proxies `/api/` and `/admin/`.
- Gunicorn runs Django with two synchronous workers, bound only to
  `127.0.0.1:8000`.
- PostgreSQL remains the production database. Uploaded media stays in
  `storage/media` and is delivered only through authenticated Django endpoints;
  do not expose that directory as a public Nginx alias.
- Production processes must set `DJANGO_SETTINGS_MODULE` to
  `config.production_settings`. Production settings deliberately do not load
  the repository's `.env`, `.env.postgres`, or `config/local_settings.py`.

## Prepare the environment

Use a Python 3.12 virtual environment on Ubuntu 24.04, install
`backend/requirements.txt`, and place production variables in a protected file
outside the repository. Start from `.env.example`, replace every placeholder,
and restrict the file to the service account and root (typically mode `0600`).
Generate `DJANGO_SECRET_KEY` on the VPS; never commit the resulting value.

The production settings fail closed unless a strong key, explicit host list,
HTTPS CSRF origins, and PostgreSQL configuration are supplied. Database
password authentication may use `DB_PASSWORD`; a separately secured
PostgreSQL authentication method is also possible.

## Build and static files

Build the React application on a build machine or CI runner and deploy the
resulting `frontend/dist` directory to the path used by the Nginx example. Node
is a build-time requirement, not a production request-serving process. Install
Python dependencies on the VPS, then load the protected environment file and
run:

```bash
python backend/manage.py check --deploy --settings=config.production_settings
python backend/manage.py collectstatic --noinput --settings=config.production_settings
```

These commands are instructions only; they were not run as part of this
preparation task. No database migration is included here.

## Start Django

With the required environment variables supplied by systemd or the shell:

```bash
bash scripts/start-production.sh
```

The script selects the production settings module and starts the Gunicorn
configuration in `backend/config/gunicorn.conf.py`. The default worker count is
intentionally fixed at two for the 2-vCPU / 2-GB target; measure memory and
response times before changing it. Keep Gunicorn bound to loopback and ensure
Nginx overwrites `X-Forwarded-Proto`; production settings trust that header for
HTTPS redirects and secure-cookie handling.

## Nginx and remaining deployment work

Copy `deploy/nginx/driver-management.conf.example` into the VPS Nginx
configuration, replace the domain, certificate, and deployment paths, then
validate it with Nginx's configuration test before reload. The
`client_max_body_size` value is aligned with Django's 50-MB request limit.
Nginx must not serve `/media/` directly.

Still required before real deployment: provision the VPS and PostgreSQL 18,
create a least-privilege database role, set up HTTPS certificates and a
systemd-managed service, deploy the frontend build, collect static files,
plan any pending migrations with a backup/rollback strategy, back up media
alongside the database, and run production smoke/load tests. No VPS, database,
or deployment command was used for this preparation.
