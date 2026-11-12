Target: https://github.com/casacore/casacore/issues
Status: ready to post
Reproduced on: python-casacore 3.8.1 wheel from PyPI (bundles casacore 3.8.1), Linux x86_64 (WSL2, glibc), 2026-11-12; code read at casacore master 9afc669 (unchanged in these places; v3.8.2 has no python-casacore wheel)
Duplicates checked: casacore issues/PRs for "uninitialised", "uninitialized", "valgrind", "MALLOC_PERTURB", "MultiFile", "writeHeader", "StManArrayFile", "putRes", "padding", "garbage", "heap"; nearest: PR #1089 (closed unmerged 2022: zero FilebufIO and MemoryIO buffers; declined as an innocent valgrind warning, suppressions in build-tools/casacore_memcheck.supp), #767 (closed 2018; StandardStMan record-column file growth on identical rewrite, a size issue, not uninitialised bytes)
Title: Table files contain uninitialised heap memory (array-file gaps, reserved arrays, MultiFile header blocks); one case is read back as cell values
---
PR #1089 proposed zeroing the `FilebufIO` and `MemoryIO` buffers and was closed because the valgrind report was considered innocent. Four places where the uninitialised bytes end up in table files suggest otherwise (cases 1-3 come from the `FilebufIO`/`MemoryIO` buffers #1089 touched; case 4 is a separate `malloc` buffer): one is read back as cell values, and the others put process heap contents (file names, AipsIO records, about 4 MiB per MultiFile header write) into files that are routinely shared. Each case below was run twice plainly and twice under `MALLOC_PERTURB_=85` / `170` with python-casacore 3.8.1 (casacore 3.8.1); the perturbed runs differ from the plain ones exactly in the bytes listed.

**1. Values read back from reserved, never-written arrays (IncrementalStMan, FixedShape indirect column).**

```python
import numpy as np, casacore.tables as pt
cd = pt.makearrcoldesc("A", 0.0, shape=[64], options=4)          # FixedShape, indirect
dm = {"*1": {"TYPE": "IncrementalStMan", "NAME": "ISM", "SPEC": {}, "COLUMNS": ["A"]}}
t = pt.table("t", pt.maketabdesc([cd, pt.makescacoldesc("S", 0)]), dminfo=dm, nrow=3)
t.putcol("A", np.ones((3, 64)))
t.removerows([0, 1, 2])       # manager recreated
t.addrows(5)
t.putcol("S", np.arange(5, dtype=np.int32))
t.close()
print(pt.table("t").getcell("A", 0)[:4])    # fresh process
```

Plain run: `[1. 1. 1. 1.]` (values of the removed rows). `MALLOC_PERTURB_=85`: `-3.72066208e-103` (0xAA bytes); `=170`: `1.19453053e+103` (0x55). `table.f0i` differs in 511 of 540 bytes. `ISMIndColumn::addRow` (tables/DataMan/ISMIndColumn.cc:88-96) reserves the row-0 array through `StManArrayFile::putRes` (tables/DataMan/StArrayFile.cc:309-331), which writes the shape and one byte at the end of the reserved space. The bytes between come from the `FilebufIO` buffer (`new char[bufSize]`, casa/IO/FilebufIO.cc:86), which is never cleared.

**2. Alignment gaps between arrays in `table.fNi` (StandardStMan indirect columns).**

```python
d = pt.maketabdesc([pt.makearrcoldesc("I", 0, ndim=1)])
t = pt.table("t", d, nrow=8)
for r in range(8):
    t.putcell("I", r, np.arange(3, dtype=np.int32))   # 20-byte record, 4-byte gap
t.close()
```

`table.f0i` (204 bytes) differs in 28 bytes: the 4-byte gap after each record (offsets 36-39, 60-63, ...) holds `aaaaaaaa` under `MALLOC_PERTURB_=85`, zeros in a fresh process without it. With variable-shape Complex [3, 5] cells, 12 bytes differ. (In an earlier run on 3.8.1, `addcols` of a model column to a copy of a real MS gave 323 differing gap bytes; the first gap held `77640000` in a plain run.) `putRes` aligns `leng_p` to 8 bytes (StArrayFile.cc:310) without writing the gap, so it gets whatever the `FilebufIO` buffer held.

**3. MultiFile block 0 past the header (`MultiFile::writeHeader`).**

With `table.storage.option: multifile` in an aipsrc file (`CASARCFILES`), a 30-row table with an Int and a Double array column gives `table.mf` (12,582,912 bytes) in which 4,194,079 bytes differ under `MALLOC_PERTURB_`: all of block 0 from the end of the 225-byte header to the end of the 4 MiB block. `writeHeader` builds the header in `MemoryIO(itsBlockSize, itsBlockSize)` (casa/IO/MultiFile.cc:166, allocation `new unsigned char[itsAlloc]` at casa/IO/MemoryIO.cc:45) and writes the whole block with `itsIO->pwrite(itsBlockSize, 0, buf)` (MultiFile.cc:237), so every header write puts about 4 MiB of heap into the file. With a 4096-byte block (`table.storage.blocksize: 4096`) and 40 columns, two plain runs already differ in 220 bytes of the block-0 tail.

**4. MultiFile continuation block (`MultiFile::writeRemainder`).**

With `table.storage.blocksize: 4096` and 100 `addcols` (header 7,879 bytes, so it needs a continuation block), block 202 differs in bytes 3791-4095 under `MALLOC_PERTURB_`. In one plain run those bytes held strings such as `table.f83`, `table.f83i`, `table.f84i`, left over from earlier header buffers. `writeRemainder` copies at most `contBlkSize` bytes into `mfbuf` (MultiFile.cc:283-289) and writes the full block. The buffer comes from `malloc(bufSize)` (casa/IO/MultiFileBase.cc:400), which #1089 did not touch.

Suggested fix. None of these needs a full clear on every buffer allocation, which was the performance concern in #1089:
- `writeHeader`: `memset` from `mio->length()` to `itsBlockSize` before the `pwrite`. This runs once per header write.
- `writeRemainder`: zero the tail of `iobuf` for the last chunk (`todo < contBlkSize`).
- `putRes`: write zeros over the alignment gap and the reserved array instead of one byte at the end. Alternatively, zero-fill in `FilebufIO` when it reads past the end of the file, so that the fill is not left to whatever was in the buffer.

MultiFile reproduction for cases 3 and 4 (`CASARCFILES=mf.rc`; `mf.rc` contains `table.storage.option: multifile` and, for case 4, `table.storage.blocksize: 4096`):

```python
t = pt.table("t", pt.maketabdesc([pt.makescacoldesc("I", 0)]), nrow=5)
for i in range(100):
    t.addcols(pt.maketabdesc([pt.makearrcoldesc("A%03d" % i, 0.0, ndim=1)]),
              dminfo={"TYPE": "StandardStMan", "NAME": "SSM%03d_with_a_long_name_to_grow_header" % i, "SPEC": {}})
t.close()
```

Compare `t/table.mf` from a plain run with one under `MALLOC_PERTURB_=85` using `cmp -l`. The header size is the big-endian Int64 at bytes 32-39 and the block size the one at bytes 40-47.
