import requests
import json

payload = {
    "title": "Dateutil Issue 981: parser raises TypeError in wrapper logic when parsing '0-100'",
    "description": "parser raises TypeError in wrapper logic when parsing '0-100' because IllegalMonthError takes an integer instead of string and concatenates with ': %s'.",
    "raw_stack_trace": """Traceback (most recent call last):
  File "dateutil/parser/_parser.py", line 655, in parse
    ret = self._build_naive(res, default)
  File "dateutil/parser/_parser.py", line 1238, in _build_naive
    if cday > monthrange(cyear, cmonth)[1]:
  File "calendar.py", line 124, in monthrange
    raise IllegalMonthError(month)
calendar.IllegalMonthError: bad month number 0; must be 1-12

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "dateutil/parser/_parser.py", line 1374, in parse
    return DEFAULTPARSER.parse(timestr, **kwargs)
  File "dateutil/parser/_parser.py", line 657, in parse
    six.raise_from(ParserError(e.args[0] + ": %s", timestr), e)
TypeError: unsupported operand type(s) for +: 'int' and 'str'""",
    "repo": {
        "git_url": "https://github.com/dateutil/dateutil",
        "branch": "master",
        "language": "python",
        "framework": "pytest",
        "build_system": "pip"
    },
    "max_hypotheses": 1
}

r = requests.post("http://127.0.0.1:8000/api/bug-reports", json=payload)
print(f"HTTP {r.status_code}")
data = r.json()
print(json.dumps(data, indent=2))
print("RUN_ID=" + data["run_id"])
