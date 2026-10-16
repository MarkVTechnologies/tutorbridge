#!/bin/sh
# Railway (public demo) entrypoint: migrate, seed demo data, run the scheduler and the web server.
set -e
python manage.py migrate --noinput
python manage.py createcachetable
python manage.py collectstatic --noinput
python manage.py seed_demo
python manage.py run_scheduler &
exec gunicorn config.wsgi --bind "0.0.0.0:${PORT:-8000}" --workers 2 --timeout 60 --access-logfile -
