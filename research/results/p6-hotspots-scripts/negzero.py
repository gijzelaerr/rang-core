import numpy as np
from rangtoy import core_trend
for n in (1, 3, 7, 8, 9, 16, 130):
    a = np.full(n, -0.0)
    m = np.mean(a)
    got = core_trend.segment_means(a, np.array([0, n]))[0]
    print(n, repr(m), np.signbit(m), repr(got), np.signbit(got))
b = np.array([-0.0, 1.0, -1.0]); print("mixed", repr(np.mean(b)), repr(core_trend.segment_means(b, np.array([0,3]))[0]))
print(repr(np.maximum(np.array([-0.0]), 0)))
