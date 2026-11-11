"""`python -m rang.check` from a checkout whose venv has no `rang-core` yet.

    .venv/bin/python tools/check.py [rang.check arguments]
    .venv\\Scripts\\python tools\\check.py [...]

`rang.check` imports only the standard library, so it runs from the source
tree; its `ext-build` step then installs the package. This replaces the
`maturin develop -q` that used to precede the check: that debug build was a
second full compile on a cold tree, and the release `ext-build` replaced its
extension straight away (research/check-speed.md).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))

from rang import check

if __name__ == "__main__":
    sys.exit(check.main())
