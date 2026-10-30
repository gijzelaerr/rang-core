"""Temporary compatibility re-export for task C1's branch (big plan task P11).

The frozen `rangtoy.flagging` moved to `history/python/flagging.py`; its
definitions that live code uses are verbatim in `rangtoy.core_policy`
(research/p11-extract.md). C1's `core_campaign_closure.py` was written against
`from .flagging import fixed_support_tv, gain_tv, polar_gauge`; the coordinator
switches that line to `.core_policy` at C1's merge and deletes this file. No
other code may import it (tests/test_p11_extract.py).
"""

from .core_policy import fixed_support_tv, gain_tv, polar_gauge

__all__ = ["fixed_support_tv", "gain_tv", "polar_gauge"]
