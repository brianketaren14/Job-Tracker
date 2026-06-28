# gunicorn.conf.py
# Production Gunicorn configuration

import os
import multiprocessing

bind          = f"0.0.0.0:{os.getenv('PORT', '5000')}"
workers       = 1                          # Keep at 1 — APScheduler must run in a single process
worker_class  = "sync"
timeout       = 120
keepalive     = 5
preload_app   = True                       # Load app before forking (ensures scheduler starts once)

# Logging
accesslog     = "-"                        # stdout
errorlog      = "-"
loglevel      = "info"
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(D)sµs'

# Lifecycle hooks — start scheduler after worker fork
def on_starting(server):
    pass

def post_fork(server, worker):
    from scheduler import start_scheduler
    start_scheduler()

def worker_exit(server, worker):
    from scheduler import stop_scheduler
    stop_scheduler()
