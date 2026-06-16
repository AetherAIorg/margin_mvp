from redis import Redis
from rq import Queue

from app.config import settings

redis_conn = Redis.from_url(settings.redis_url)
parse_queue = Queue("parse", connection=redis_conn)


def enqueue_parse(job_id: str, artifact_id: str) -> str:
    from app.jobs import run_parse_job

    job = parse_queue.enqueue(run_parse_job, job_id, artifact_id, job_timeout=600)
    return job.id
