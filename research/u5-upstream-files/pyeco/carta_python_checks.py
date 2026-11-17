"""carta-python checks that need no CARTA backend or browser."""

import inspect
import sys

import carta
import carta.browser
import carta.session
import selenium
from carta.session import Session
from selenium import webdriver

print(
    "python",
    sys.version.split()[0],
    "selenium",
    selenium.__version__,
    "carta from",
    carta.__file__,
)

# 1. Chrome(driver_path=...) -> selenium.webdriver.Chrome(executable_path=...)
print("webdriver.Chrome signature:", inspect.signature(webdriver.Chrome.__init__))
try:
    carta.browser.Chrome(driver_path="/nonexistent/chromedriver")
except TypeError as e:
    print("Chrome(driver_path=...) raised TypeError:", e)


# 2. Session.__del__ repeats close() after an explicit close()
class FakeBrowser:
    calls = 0

    def close(self):
        FakeBrowser.calls += 1


class FakeBackend:
    calls = 0

    def stop(self):
        FakeBackend.calls += 1


s = Session(1, protocol=None, browser=FakeBrowser(), backend=FakeBackend())
s.close()
print(
    "after close(): browser.close calls",
    FakeBrowser.calls,
    "backend.stop calls",
    FakeBackend.calls,
)
del s
import gc

gc.collect()
print(
    "after del + gc.collect(): browser.close calls",
    FakeBrowser.calls,
    "backend.stop calls",
    FakeBackend.calls,
)
