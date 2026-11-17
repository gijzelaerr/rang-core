Target: https://github.com/CARTAvis/carta-python/issues
Status: ready to post
Reproduced on: carta-python dev c33914d with stub browser/backend objects (no CARTA backend), Python 3.13.16, 2026-11-12; the shutdown traceback was seen on v1.2.0 with CARTA 6.0.0 and headless Chrome (2026-10-31)
Duplicates checked: search/issues repo:CARTAvis/carta-python "__del__", "close", "sys.meta_path", "shutdown": none; open PRs #168, #185, #186, #189 touch session.py but not close()/__del__

Title: Session.close() is repeated by __del__, so an explicitly closed headless session errors at interpreter exit
---
`Session.close()` closes `self._browser` and stops `self._backend` but keeps the references, and `Session.__del__` calls `close()` again. After an explicit `session.close()` the browser driver's `quit()` and the backend's `stop()` therefore run a second time when the object is collected. For a headless session that is usually at interpreter shutdown, and it prints

```
ImportError: sys.meta_path is None, Python is likely shutting down
```

(seen with v1.2.0, CARTA 6.0.0, headless Chrome, `Session.start_and_create(...)` followed by `session.close()`).

Minimal check without a backend (dev c33914d):

```python
import gc
from carta.session import Session

class B:
    n = 0
    def close(self): B.n += 1
class K:
    n = 0
    def stop(self): K.n += 1

s = Session(1, protocol=None, browser=B(), backend=K())
s.close()
print(B.n, K.n)   # 1 1
del s; gc.collect()
print(B.n, K.n)   # 2 2
```

Code: `carta/session.py` on dev (c33914d), `__del__` at lines 74-76 and `close` at lines 1050-1062.

Suggested fix: clear the references in `close()` so it is idempotent:

```python
if self._browser is not None:
    self._browser.close()
    self._browser = None
if self._backend is not None:
    self._backend.stop()
    self._backend = None
```
