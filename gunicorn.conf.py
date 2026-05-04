# Gunicorn configuration for Points Are Bad
#
# Run with:
#   gunicorn -c gunicorn.conf.py web.server:app
#
# SQLite with WAL journal mode safely handles concurrent reads and writes
# from multiple workers/threads.  No application-level lock is needed.

import os

# Bind
bind = f"0.0.0.0:{os.environ.get('PORT', '5001')}"

# Concurrency — SQLite WAL handles it across workers
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))
threads = 4

# Graceful shutdown timeout (seconds)
timeout = 30
graceful_timeout = 10
keepalive = 5

# Logging — output to stdout/stderr so container runtimes capture it
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(D)sµs'

# Process naming
proc_name = "points-are-bad"

# Load the application before forking workers.
preload_app = True

# Trust X-Forwarded-For from any upstream proxy so that flask-limiter sees the
# real client IP rather than the proxy's address.
forwarded_allow_ips = "*"
