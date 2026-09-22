# Regression tests

The tests run against Home Assistant 2026.9.3 on Python 3.14. They mock API
responses and use a temporary on-disk cache; no Pstryk account is needed.

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m pytest -q
```

Coverage includes scheduled sensor updates during repeated API outages, restart
from cache, expired and unreadable caches, midnight and Warsaw DST transitions,
timeouts crossing an hour boundary, API recovery, authentication errors, and
price conversion (including valid zero and negative prices).
