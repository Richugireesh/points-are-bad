# Gunicorn configuration for Points Are Bad
#
# Run with:
#   gunicorn -c gunicorn.conf.py web.server:app
#
# IMPORTANT — workers must stay at 1.
# The app uses a threading.Lock for read-modify-write safety on the JSON data
# file.  That lock lives in process memory.  Multiple workers each get their
# own copy of the lock, making it ineffective — concurrent writes will corrupt
# the data file.  Keep workers=1 unless you migrate to a proper database.
#
# threads > 1 is safe: all threads share the same lock instance.

import os

# Bind
bind = f"0.0.0.0:{os.environ.get('PORT', '5001')}"

# Single worker — required for threading.Lock correctness (see note above)
workers = 1
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

# Load the application before forking workers.  With workers=1 this is a minor
# startup optimisation; it also ensures any module-level initialisation (e.g.
# the flask-limiter Limiter object) runs once in the master process.
preload_app = True

# Trust X-Forwarded-For from any upstream proxy so that flask-limiter sees the
# real client IP rather than the proxy's address.  Restrict to a specific CIDR
# if your proxy has a fixed IP (e.g. "10.0.0.0/8").
forwarded_allow_ips = "*"
