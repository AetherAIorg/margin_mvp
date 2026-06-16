from rq import Worker

from app.queue import redis_conn


def main():
    worker = Worker(["parse"], connection=redis_conn)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
