Target: https://gitlab.com/aroffringa/aoflagger/-/issues
Status: ready to post
Reproduced on: run on AOFlagger 3.5.0 (Python module, snippet below); read in source at master 811f8e09261f04e97a4802a23635eee125fbf4b7 (`algorithms/sumthresholdmissing.cpp`, unchanged since v3.5.0 but for formatting)
Duplicates checked: AOFlagger issues/MRs ("sumthreshold", "missing"; nearest MR !159 "Make sure sumthreshold algorithm works with NaNs", !179 thresholding clean-up; none covers this)
Title: SumThresholdMissing::horizontal keeps a missing sample in the running sum for the rest of the row
---
In `SumThresholdMissing::horizontal` (`algorithms/sumthresholdmissing.cpp:13-68`, master 811f8e0)
the initial loop leaves `xRight` one past the last sample it counted, without skipping missing
samples:

```cpp
29      size_t xRight = xLeft, countAdded = 0, countTotal = 0;
30      while (countTotal + 1 < length && xRight != width) {
 ...
37        ++xRight;
38      }
40      while (xRight != width) {
41        // Add a sample at the right
42        if (!mask.Value(xRight, y)) {        // tests the mask only, not `missing`
43          sum += input.Value(xRight, y);
44          ++countAdded;
```

If that sample is missing, the main loop adds it. `xLeft` only ever visits non-missing samples, so
it is never subtracted: the value stays in `sum` and `countAdded` for the rest of the row. The later
`do { ++xRight; } while (missing...)` skips missing samples correctly, so only the first window of
each row and length is affected, but the error then persists along the row. This is the time
direction of `sumthreshold_masked`, which all shipped strategies use with the input flags as
`missing`.

Reproduction: noise rows with one large, missing sample per row. At x = 1 it lands on the bug
(length 2); at x = 10 it does not.

```python
import os, tempfile
import numpy as np
import aoflagger
lua = os.path.join(tempfile.mkdtemp(), "s.lua")
open(lua, "w").write("""function execute(input)
  local missing = input:copy()   -- the flags passed to run() mark the missing samples
  local data = input:copy()
  aoflagger.sumthreshold_masked(data, missing, 1.0, 1.0, true, false)
  input:set_mask(data)
end
""")
f = aoflagger.AOFlagger()
s = f.load_strategy_file(lua)
w, h = 64, 8
base = np.abs(np.random.default_rng(1).normal(0, 1, (h, w))).astype(np.float32)
for col in (1, 10):
    img = base.copy(); miss = np.zeros((h, w), bool)
    img[:, col] = 1e4; miss[:, col] = True
    iset = f.make_image_set(w, h, 1); iset.set_image_buffer(0, img)
    fm = f.make_flag_mask(w, h, False); fm.set_buffer(miss)
    out = np.array(s.run(iset, fm).get_buffer(), bool)
    print(f"missing hot column x={col}: flagged non-missing samples {int((out & ~miss).sum())} of {int((~miss).sum())}")
```

AOFlagger 3.5.0:

```
missing hot column x=1: flagged non-missing samples 504 of 504
missing hot column x=10: flagged non-missing samples 2 of 504
```

On MeerKAT data (14 time steps x 4,096 channels per baseline, input flags as `missing`), running
the same masked SumThreshold along x and, transposed, along y gives results that differ in 298,810
cells, from this and the zero tail described at the end. A model of the loop as written matches AOFlagger's x pass exactly
(0 differences on 40 synthetic 60 x 30 images, where the intended semantics differ in 655 cells).

Suggested fix, after the initial loop:

```diff
         ++xRight;
       }
+      while (xRight != width && missing.Value(xRight, y)) ++xRight;
 
       while (xRight != width) {
```

`VerticalReference` calls the same function on the transposed image, so it has the same defect;
the `compare_vertical_masked_*` tests do not hit it because `IntroduceGap` puts the missing block
in the middle of the image, not right after a row's first window.

Related, smaller: `VerticalStacked` (lines 98-125) compacts each column's valid samples to the top
of `cache.validImage` and leaves the rest of the column as zero-valued, unflagged samples, so
`VerticalLarge` also evaluates windows that run past the last valid sample, which `horizontal`
never does. On 40 synthetic 60-sample columns with 30 % missing this changed 4 cells. Limiting each
column's windows to its valid length (`cache.positions[x]`) would make the two directions agree.
