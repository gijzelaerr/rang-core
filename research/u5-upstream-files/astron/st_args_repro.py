# sumthreshold vs sumthreshold_masked direction arguments (AOFlagger Lua API).
import os
import tempfile

import aoflagger
import numpy as np

f = aoflagger.AOFlagger()
img = np.zeros((64, 32), np.float32)
img[10, 4:12] = 0.6  # a run along x (time)
img[30:38, 20] = 0.6  # a run along y (frequency)
tmp = tempfile.mkdtemp()
for fn, extra in (("sumthreshold", ""), ("sumthreshold_masked", "missing, ")):
    for h, v in (("true", "false"), ("false", "true")):
        lua = os.path.join(tmp, f"{fn}_{h}_{v}.lua")
        with open(lua, "w") as fh:
            fh.write(f"""function execute(input)
  local missing = input:copy()
  local data = input:copy()
  aoflagger.{fn}(data, {extra}1.0/6.0, 1.0/6.0, {h}, {v})
  input:set_mask(data)
end
""")
        s = f.load_strategy_file(lua)
        iset = f.make_image_set(32, 64, 1)
        iset.set_image_buffer(0, img)
        o = np.array(s.run(iset).get_buffer())
        print(
            f"{fn}(..., {h}, {v}): x run flagged {bool(o[10, 4:12].all())}, y run flagged {bool(o[30:38, 20].all())}"
        )
