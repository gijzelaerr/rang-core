Target: Richard Armstrong (SARAO), channel for the owner to choose. Status: draft, not sent (owner decides the channel and sends or approves).
Public fork: github.com/richarms/Obit (issues disabled). Its master = bill-cotton/Obit master dc26694. Branch `fix/mfbeam-stokes-multigpu` carries
commit ab77437c2c0bc85dcc14f36602d4ba82233cd5f8 (2026-10-20, "Fix residual Stokes selection dimensions"), the same two-line fix as ours.
The fix is not on bill-cotton/Obit master (dc26694, 2026-10-09, latest; lines 1088 and 1115 unchanged, re-read 2026-11-12). No PR from
richarms to bill-cotton/Obit exists; bill-cotton/Obit has issues enabled but no issue or PR was ever filed there.
Reproduced on: bill-cotton/Obit master dc26694, built and run by V5 (`rang-obit:dc26694`, crash; `rang-obit:dc26694-p1`, patched, passes).

Title: Obit MFImage CLEAN crash: dim[5] in MFMakeResiduals (your ab77437c)

---

Hi Richard,

MFImage at bill-cotton/Obit master dc26694 crashes at the first residual of every CLEAN (Niter > 0): SIGSEGV, rc 139, 14.8 s
into the run, right after "SkyModel with 30 components". Niter 0 runs are fine.

- File: `ObitSystem/Obit/src/ObitDConCleanVisMF.c`, `MFMakeResiduals`, lines 1088 and 1115:
  `dim[0] = 4; dim[1] = dim[2] = dim[3] = dim[5];`
- `dim` is `gint32 dim[MAXINFOELEMDIM] = {4,1,1,1,1}` and `MAXINFOELEMDIM` is 5 (`ObitInfoElem.h:46`), so `dim[5]` is read
  one past the end and the element count of the "Stokes" `ObitInfoListAlwaysPut` is stack garbage.
- Under gdb the run aborts in `g_malloc0`, asked for 18446744071959779253 bytes from that call.
- Reproduce: any MFImage run with Niter > 0 (ours: MeerKAT L-band simulation, 2048², Robust 0.5, Ubuntu 24.04, GCC 13,
  -O3 -march=native). Whether it segfaults or runs on depends on the stack contents, so it may not show on every build.

Patch:

```diff
--- a/ObitSystem/Obit/src/ObitDConCleanVisMF.c
+++ b/ObitSystem/Obit/src/ObitDConCleanVisMF.c
@@ -1088 +1088 @@
-  dim[0] = 4; dim[1] = dim[2] = dim[3] = dim[5];
+  dim[0] = 4; dim[1] = dim[2] = dim[3] = dim[4] = 1;
@@ -1115 +1115 @@
-    dim[0] = 4; dim[1] = dim[2] = dim[3] = dim[5];
+    dim[0] = 4; dim[1] = dim[2] = dim[3] = dim[4] = 1;
```

With it the same run completes: rc 0, 236,158 iterations, fluxes within 2e-4 of the truth.

I see your ab77437c on `fix/mfbeam-stokes-multigpu` is the same change, so this confirms it independently. Is it on its way
to Bill's master, or should we send it to him directly?

Gijs
