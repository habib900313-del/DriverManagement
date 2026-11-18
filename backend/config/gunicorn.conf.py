"""Conservative Gunicorn settings for the 2-vCPU / 2-GB target VPS."""

bind = "127.0.0.1:8000"
workers = 2
worker_class = "sync"
timeout = 90
graceful_timeout = 30
keepalive = 2
max_requests = 500
max_requests_jitter = 50
accesslog = "-"
errorlog = "-"
capture_output = True
access_log_format = '%(h)s %(t)s "%(m)s %(U)s %(H)s" %(s)s %(L)s'
