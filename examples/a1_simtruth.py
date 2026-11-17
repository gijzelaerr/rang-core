"""Task A1: write the simulated truth as a Measurement Set (research/a1-simtruth.md).

    python examples/a1_simtruth.py generate {small,full,...} OUTDIR [--workers N]
    python examples/a1_simtruth.py size {small,full,...}

The generator is `rang.simtruth_ms` since task V3b (research/v3-intro-track.md),
so `python -m rang.simtruth_ms` does the same from any install; this script
stays for the commands, tools and notes that name it.
"""

from rang.simtruth_ms import *
from rang.simtruth_ms import main

if __name__ == "__main__":
    main()
