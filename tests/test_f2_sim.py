"""F2's simulation design (research/f2-flagger.md, section 4): window, seeds, RFI."""

import numpy as np
from rang import f2flag_sim as fs
from rang import simtruth as st


def test_window_is_lunos():
    d = fs.design("f2sim-v")
    assert d.nchan == 2048
    assert abs(d.chan_width - 208984.375) < 1e-6
    assert abs(d.freq[0] - (856e6 + 1024.5 * 208984.375)) < 1e-3
    assert abs(d.sigma - 420 / np.sqrt(2 * 208984.375 * 8)) < 1e-12


def test_seeds_are_registered_and_unique():
    used = []
    for name, s in st.SEEDS.items():
        if not name.startswith(("f2sim", "f3sim")):
            used += [s[k] for k in ("jones", "sky", "rfi", "noise")]
    for name in fs.OBSERVATIONS:
        s = fs.seeds(name)
        assert not set(s.values()) & set(used)


def test_drifting_only_in_test_observations():
    for name, role in fs.ROLE.items():
        d = fs.design(name)
        _, scans, _, _ = fs.schedule(d, fs.OBSERVATIONS[name]["start"])
        g1, l1, dr1 = fs.extra_events(d, scans, role == "test")
        g2, l2, _ = fs.extra_events(d, scans, role == "test")
        assert (len(dr1) > 0) == (role == "test")
        assert [e["chans"] for e in g1] == [e["chans"] for e in g2]
        assert l1 == l2
