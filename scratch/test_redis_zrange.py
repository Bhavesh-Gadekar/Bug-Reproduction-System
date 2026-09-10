import asyncio
import time
import subprocess

subprocess.run(["docker", "stop", "-t", "1", "bug_reproduction_redis"], check=True)

test_script = """
import asyncio, time
from arq.connections import create_pool, RedisSettings
from app.core.config import get_worker_settings

async def test():
    s = get_worker_settings()
    rs = RedisSettings.from_dsn(s.REDIS_URL)
    rs.conn_retries = 0
    t0 = time.time()
    try:
        pool = await create_pool(rs)
        await pool.zrangebyscore("reproduction_tasks", 0, 1000)
    except Exception as e:
        print(f"FAILED in {time.time()-t0:.2f}s with {type(e).__name__}: {e}")

asyncio.run(test())
"""

res = subprocess.run(["docker", "exec", "bug_reproduction_worker", "python", "-c", test_script], capture_output=True, text=True)
print("STDOUT:", res.stdout)
print("STDERR:", res.stderr)

subprocess.run(["docker", "start", "bug_reproduction_redis"], check=True)
