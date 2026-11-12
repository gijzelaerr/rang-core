Target: https://gitlab.com/aroffringa/aoflagger/-/issues
Status: ready to post
Reproduced on: run on AOFlagger 3.5.0 (Python module, snippet below); read in source at master 811f8e09261f04e97a4802a23635eee125fbf4b7 (`lua/functionswrapper.cpp:319`; v3.5.0 f4ee4cf `:320`)
Duplicates checked: AOFlagger issues/MRs ("sumthreshold_masked", "sumthreshold"; nearest MR !122 "Fix error in sumthreshold Lua documentation", !159 NaNs; none covers this)
Title: sumthreshold_masked reads its direction flags from Lua arguments 4 and 5 instead of 5 and 6
---
`Functions::sumthreshold_masked` (`lua/functionswrapper.cpp`, master 811f8e0):

```cpp
313  double hThresholdFactor = luaL_checknumber(L, 3), vThresholdFactor = luaL_checknumber(L, 4);
314  if (!lua_isboolean(L, 5) || !lua_isboolean(L, 6)) {
 ...
319    bool horizontal = lua_toboolean(L, 4), vertical = lua_toboolean(L, 5);
```

Argument 4 is the vertical threshold factor (a number, so always true), so the time direction
always runs and the frequency direction follows the `horizontal` argument. The shipped strategies
all pass `true, true` and are unaffected; any other combination is wrong.

```python
import os, tempfile
import numpy as np
import aoflagger
f = aoflagger.AOFlagger()
img = np.zeros((64, 32), np.float32)
img[10, 4:12] = 0.6     # a run along x (time)
img[30:38, 20] = 0.6    # a run along y (frequency)
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
        print(f"{fn}(..., {h}, {v}): x run flagged {bool(o[10, 4:12].all())}, y run flagged {bool(o[30:38, 20].all())}")
```

AOFlagger 3.5.0:

```
sumthreshold(..., true, false): x run flagged True, y run flagged False
sumthreshold(..., false, true): x run flagged False, y run flagged True
sumthreshold_masked(..., true, false): x run flagged True, y run flagged True
sumthreshold_masked(..., false, true): x run flagged True, y run flagged False
```

Fix:

```diff
-    bool horizontal = lua_toboolean(L, 4), vertical = lua_toboolean(L, 5);
+    bool horizontal = lua_toboolean(L, 5), vertical = lua_toboolean(L, 6);
```

(The error message on line 317 also names `sumthreshold()` rather than `sumthreshold_masked()`.)
