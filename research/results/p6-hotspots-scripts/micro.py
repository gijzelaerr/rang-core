import time
import numpy as np
from rangtoy import core_signal
rng = np.random.default_rng(0)
n = 70000
pool = rng.normal(size=(500, 2, 2)) + 1j * rng.normal(size=(500, 2, 2))
m = pool[np.repeat(np.arange(n // 20), 20) % 500]
for name, f in (("cond", np.linalg.cond), ("_cond", core_signal._cond), ("inv", np.linalg.inv), ("_inv", core_signal._inv)):
    best = min((lambda t: (f(m), time.perf_counter() - t)[1])(time.perf_counter()) for _ in range(3))
    print(name, f"{best*1e3:.1f} ms")
