import sys
import asyncio
import os

sys.path.insert(0, os.path.abspath("."))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

os.environ["SANDBOX_URL"] = "http://127.0.0.1:8001"
from app.main import ReproductionWorker

async def test_worker():
    w = ReproductionWorker()
    await w.start_dependencies()
    print("Dependencies started! Running graph with real Gemini...")
    payload = {
        "bug_report_id": "00000000-0000-0000-0000-000000000001",
        "run_id": "00000000-0000-0000-0000-000000000001",
        "title": "ValueError in parse()",
        "raw_stack_trace": "Traceback (most recent call last):\n  File \"test.py\", line 5, in <module>\nValueError: invalid date format",
        "repo": {
            "git_url": "https://github.com/dateutil/dateutil",
            "branch": "master",
            "language": "python",
            "framework": "pytest",
            "build_system": "pip"
        },
        "max_hypotheses": 1
    }
    try:
        res = await w.process_task(payload)
        print("Graph finished with result keys:", list(res.keys()))
        print("Final verdict:", res.get("final_verdict"))
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        await w.shutdown()

if __name__ == "__main__":
    asyncio.run(test_worker())
