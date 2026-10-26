#!/usr/bin/env bash

# Start cron if enabled (set ARG ENABLE_CRON=true in Dockerfile or via --build-arg)
if [ "$ENABLE_CRON" = "true" ]; then
    cron  # no & needed; cron daemonizes itself
fi

# Starts the ONE Xvfb (DISPLAY=:99, set in the base image); plus x11vnc + noVNC if ENABLE_VNC=true.
# Chrome runs headed on it. Exits 1 if Xvfb fails.
vnc-start || exit 1

if [ "$APP_ENV" = "development" ]; then
    # flask provides debug, hot reload
    # exec: replace bash so the server receives SIGTERM directly for graceful shutdown
    exec python main.py
else
    # WSGI - Flask
    # ONE worker: the process owns the single Chrome and its profile lock (a second worker = a second Chrome
    # on the same profile). Threads give concurrency; browser.py queues windows per site / MAX_WINDOWS.
    # Long timeout: some feeds fetch many pages with polite delays.
    exec gunicorn --workers 1 --threads 8 --timeout 600 --bind 0.0.0.0:5000 main:app
fi
