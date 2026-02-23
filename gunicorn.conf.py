"""
Gunicorn Configuration for Production

Reference: https://docs.gunicorn.org/en/stable/settings.html
"""

import os
import multiprocessing

# =============================================================================
# SERVER SOCKET
# =============================================================================

# Bind to PORT from environment (Render, etc.) or default 8000
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"

# Number of pending connections
backlog = 2048

# =============================================================================
# WORKER PROCESSES
# =============================================================================

# Worker class - sync is simple and reliable for most apps
worker_class = "sync"

# Number of workers
# For free tier (limited CPU), use 2-4
workers = int(os.getenv("WEB_CONCURRENCY", 2))

# Threads per worker (for sync workers, typically 1)
threads = 1

# Max requests per worker before restart (prevents memory leaks)
max_requests = 1000
max_requests_jitter = 50

# Worker timeout in seconds
timeout = 30

# Graceful timeout for worker shutdown
graceful_timeout = 30

# Keep-alive timeout
keepalive = 2

# =============================================================================
# SECURITY
# =============================================================================

# Limit request line size
limit_request_line = 4094

# Limit request fields
limit_request_fields = 100

# Limit request field size
limit_request_field_size = 8190

# =============================================================================
# LOGGING
# =============================================================================

# Access log format
accesslog = "-"  # stdout
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Error log
errorlog = "-"  # stderr
loglevel = os.getenv("LOG_LEVEL", "info")

# Capture output
capture_output = True

# =============================================================================
# PROCESS NAMING
# =============================================================================

proc_name = "carebox"

# =============================================================================
# SERVER MECHANICS
# =============================================================================

# Daemonize the Gunicorn process (False for container deployment)
daemon = False

# PID file path
pidfile = None

# User/group for worker processes
user = None
group = None

# Umask for file mode creation
umask = 0

# Working directory
chdir = os.path.dirname(os.path.abspath(__file__))

# Temporary directory for worker heartbeat files
tmp_upload_dir = None

# =============================================================================
# HOOKS
# =============================================================================

def on_starting(server):
    """Called just before the master process is initialized."""
    pass

def on_reload(server):
    """Called before workers reload."""
    pass

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info(f"Worker spawned (pid: {worker.pid})")

def worker_exit(server, worker):
    """Called just after a worker has been exited."""
    pass
