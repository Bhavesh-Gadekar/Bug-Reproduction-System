import re

raw_trace = """Traceback (most recent call last):
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
TypeError: unsupported operand type(s) for +: 'int' and 'str'
"""

sandbox_stderr = """Traceback (most recent call last):
  File "/repos/8ee97f4d-3bf0-4eda-81f9-c7f619e125b2/.deps/dateutil/parser/_parser.py", line 649, in parse
    ret = self._build_naive(res, default)
  File "/repos/8ee97f4d-3bf0-4eda-81f9-c7f619e125b2/.deps/dateutil/parser/_parser.py", line 1232, in _build_naive
    if cday > monthrange(cyear, cmonth)[1]:
  File "/usr/local/lib/python3.11/calendar.py", line 126, in monthrange
    raise IllegalMonthError(month)
calendar.IllegalMonthError: bad month number 0; must be 1-12

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "<string>", line 12, in <module>
  File "<string>", line 6, in main
  File "/repos/8ee97f4d-3bf0-4eda-81f9-c7f619e125b2/.deps/dateutil/parser/_parser.py", line 1368, in parse
    return DEFAULTPARSER.parse(timestr, **kwargs)
  File "/repos/8ee97f4d-3bf0-4eda-81f9-c7f619e125b2/.deps/dateutil/parser/_parser.py", line 651, in parse
    six.raise_from(ParserError(str(e) + ": %s", timestr), e)
  File "<string>", line 3, in raise_from
dateutil.parser._parser.ParserError: bad month number 0; must be 1-12: 0-100
"""

def extract_signature_details(raw_stack_trace: str, title: str = "", description: str = ""):
    exceptions: list[str] = []
    for line in raw_stack_trace.splitlines():
        m = re.match(r"^[\w.]*?(\w+(?:Error|Exception|Warning|Failure))\s*:", line.strip())
        if m:
            exceptions.append(m.group(1))
    
    primary_error = exceptions[-1] if exceptions else None
    if not primary_error:
        title_matches = re.findall(r"\b([A-Z]\w*(?:Error|Exception|Warning|Failure))\b", f"{title} {description}")
        if title_matches:
            primary_error = title_matches[0]
            
    all_keywords = set(exceptions)
    if primary_error:
        all_keywords.add(primary_error)
        
    return primary_error, all_keywords

primary, all_kw = extract_signature_details(raw_trace, "Dateutil Issue 981: parser raises TypeError in wrapper logic")
print("Primary error:", primary)
print("All keywords:", all_kw)

def check_match(primary_error, all_keywords, output):
    if primary_error:
        # The primary exception must be present as an exception in the output
        pattern = r"\b" + re.escape(primary_error) + r"\s*:"
        if re.search(pattern, output) or f"{primary_error}:" in output:
            return "matched"
        return "no_match"
    else:
        # Fallback to any keyword
        if any(kw in output for kw in all_keywords):
            return "matched"
        return "no_match"

print("Match verdict with sandbox stderr:", check_match(primary, all_kw, sandbox_stderr))
