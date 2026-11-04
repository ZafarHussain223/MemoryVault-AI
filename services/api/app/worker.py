from redis import Redis
from rq import Worker,Queue
from .config import REDIS_URL
if __name__=='__main__':
    connection=Redis.from_url(REDIS_URL)
    Worker([Queue('ingestion',connection=connection)],connection=connection).work()
