#!/bin/sh
source venv/bin/activate
exec gunicorn -b :5001 --chdir src --log-level=warning wsgi:app
