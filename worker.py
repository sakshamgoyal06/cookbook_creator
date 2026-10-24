"""Background worker: `python worker.py`. Runs pipeline jobs from Redis (REDIS_URL).

Run it as a separate Railway service from the same repo, with this as its start command.
It does not run migrations; the web service does that before it starts.
"""
import logging

from redis import Redis
from rq import Worker

import config

if __name__ == "__main__":
    if not config.REDIS_URL:
        raise SystemExit("REDIS_URL is not set; uploads are processed inline, so no worker is needed.")
    logging.basicConfig(level=logging.INFO)
    Worker([config.PIPELINE_QUEUE], connection=Redis.from_url(config.REDIS_URL)).work(with_scheduler=True)
