"""T-I of research/e2a-3b-diag.md: `rang-core` (the frozen wheel) with every
chain term's `max_iterations` set to N instead of `chain_terms`' 50; with
the optional STOP and FRACTION (post hoc T-S, section 6) also every term's
`stop_criterion` and `stop_fraction`.

    python d1_rang_iter.py N run CONFIG MS
    python d1_rang_iter.py N:STOP:FRACTION run CONFIG MS
"""

import sys

from rang import core_cli, core_pipeline

PARTS = sys.argv[1].split(":")
N = int(PARTS[0])
STOP = float(PARTS[1]) if len(PARTS) > 1 else None
FRACTION = float(PARTS[2]) if len(PARTS) > 2 else None
_chain_terms = core_pipeline.chain_terms


def chain_terms(*args, **kwargs):
    terms = _chain_terms(*args, **kwargs)
    for t in terms:
        if "max_iterations" in t:
            t["max_iterations"] = N
            if STOP is not None:
                t["stop_criterion"] = STOP
            if FRACTION is not None:
                t["stop_fraction"] = FRACTION
    return terms


core_pipeline.chain_terms = chain_terms
sys.exit(core_cli.main(sys.argv[2:]))
