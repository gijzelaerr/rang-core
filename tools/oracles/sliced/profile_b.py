"""Where a channel-chunked B solve spends its time (research/sliced-read.md).

    python profile_b.py MS OUT.txt [CHUNK_ROWS]

On a read-only MS (field 0, `combine: scan`, K and G pre-applied, the
unit model), B with `data.chunk_rows` CHUNK_ROWS (default 7: one channel per
chunk) under cProfile. The cumulative times of the reader, the pre-apply and
the kernel are printed; run it with the code before and after the change.
"""

import cProfile
import io
import pstats
import sys
import time

from rang import cal_bandpass, cal_delay, cal_fluxscale, cal_gain, core_chunks


def main(ms, out, chunk_rows=7):
    nrow, nchan = cal_fluxscale._field_rows(ms, 0, 0)
    model = cal_fluxscale.smodel_view(nrow, nchan, (1.0, 0.0, 0.0, 0.0))
    common = {"field_id": 0, "refant": 0, "weight_column": "WEIGHT", "model": model}
    k = cal_delay.gaincal(ms, solint="inf", **common)[0]
    g = cal_gain.gaincal(ms, solint="int", gaintable=[k], minblperant=2, **common)[0]
    budget = core_chunks.ChainBudget(chunk_bytes=8 << 30, chunk_rows=int(chunk_rows))
    prof = cProfile.Profile()
    start = time.perf_counter()
    prof.enable()
    b = cal_bandpass.bandpass(
        ms, combine="scan", minblperant=2, gaintable=[k, g], budget=budget, **common
    )
    prof.disable()
    wall = time.perf_counter() - start
    text = io.StringIO()
    stats = pstats.Stats(prof, stream=text).sort_stats("cumulative")
    stats.print_stats(40)
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"wall {wall:.2f} s, B iterations {b[1].iterations}\n")
        f.write(text.getvalue())
    print(f"wall {wall:.2f} s")


if __name__ == "__main__":
    main(*sys.argv[1:])
