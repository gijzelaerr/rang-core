Target: https://github.com/CARTAvis/carta-python/issues
Status: ready to post
Reproduced on: carta-python dev c33914d (installed from the checkout) and v1.2.0 (989af8e, same code), selenium 4.52.0, Python 3.13.16, 2026-11-12; no CARTA backend or browser needed
Duplicates checked: search/issues repo:CARTAvis/carta-python "executable_path" (#189, #174, #168, #70, #25: all about the CARTA backend executable), "selenium" (#144/#147 find_element_by_*, #159, #168), "chromedriver", "driver_path": none; open PRs #168, #169, #184-#189 do not change browser.py's driver handling

Title: Chrome(driver_path=...) fails on Selenium >= 4.10: executable_path is no longer accepted
---
`carta.browser.Chrome(driver_path=...)` passes `executable_path=driver_path` to `selenium.webdriver.Chrome`. Selenium removed that argument in 4.10.0; the current signature (4.52.0) is `Chrome(options=None, service=None, keep_alive=True)`. So any use of `driver_path` raises before a browser starts:

```python
import carta.browser
carta.browser.Chrome(driver_path="/usr/bin/chromedriver")
```

```
TypeError: WebDriver.__init__() got an unexpected keyword argument 'executable_path'
```

Code: `carta/browser.py` lines 184-185 on dev (c33914d):

```python
if driver_path:
    kwargs["executable_path"] = driver_path
```

Suggested fix:

```python
from selenium.webdriver.chrome.service import Service
...
if driver_path:
    kwargs["service"] = Service(executable_path=driver_path)
```

(and a minimum `selenium>=4.10` in the `browser` extra).
