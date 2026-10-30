"""Process peak memory and CPU time on every platform (task P7,
research/p7-architecture.md; X1 found `import resource` breaking Windows).

On POSIX these read `resource.getrusage`, imported lazily, so the values are
the ones the drivers recorded before. `ru_maxrss` is KiB on Linux but bytes
on macOS; `peak_rss_bytes` returns bytes on both. On Windows the peak
working set comes from `K32GetProcessMemoryInfo` and CPU time from
`os.times`.
"""

import os
import sys


def _rusage():
    import resource

    return resource.getrusage(resource.RUSAGE_SELF)


def _windows_peak_working_set():
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.K32GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(Counters),
        wintypes.DWORD,
    ]
    kernel32.K32GetProcessMemoryInfo.restype = wintypes.BOOL
    counters = Counters()
    counters.cb = ctypes.sizeof(Counters)
    if not kernel32.K32GetProcessMemoryInfo(
        kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    ):
        raise OSError("K32GetProcessMemoryInfo failed")
    return int(counters.PeakWorkingSetSize)


def peak_rss_bytes():
    """The process's peak resident set (Windows: peak working set), bytes."""
    if sys.platform == "win32":
        return _windows_peak_working_set()
    maxrss = _rusage().ru_maxrss
    return int(maxrss) if sys.platform == "darwin" else int(maxrss) * 1024


def peak_rss_mb():
    """`peak_rss_bytes() / 2**20`; on Linux bit-equal to `ru_maxrss / 1024`."""
    return peak_rss_bytes() / 2**20


def cpu_seconds():
    """User plus system CPU seconds of this process."""
    if sys.platform == "win32":
        times = os.times()
        return times.user + times.system
    usage = _rusage()
    return usage.ru_utime + usage.ru_stime
