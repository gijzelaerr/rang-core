"""9.18: add FLAG_CATEGORY (WSClean opens it) to the ext4 copy, with the
source's column description, no cells written (as in the source MS).

    a5_fixcat.py SRC_MS DST_MS
"""

import sys

from casacore.tables import makecoldesc, table

src, dst = sys.argv[1:3]
s = table(src, ack=False)
desc = s.getcoldesc("FLAG_CATEGORY")
kw = s.getcolkeywords("FLAG_CATEGORY")
s.close()
d = table(dst, readonly=False, ack=False)
if "FLAG_CATEGORY" not in d.colnames():
    desc.pop("dataManagerGroup", None)
    d.addcols(makecoldesc("FLAG_CATEGORY", desc),
              {"TYPE": "StandardStMan", "NAME": "A5FlagCategory", "SPEC": {}})  # fmt: skip
    for k, v in kw.items():
        d.putcolkeyword("FLAG_CATEGORY", k, v)
print(sorted(d.colnames()))
d.close()
