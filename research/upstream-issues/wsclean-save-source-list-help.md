Target: https://gitlab.com/aroffringa/wsclean/-/issues
Status: ready to post (low priority; documentation only)
Reproduced on: run on WSClean 3.7 (`-channels-out 16 -join-channels -save-source-list`, no `-fit-spectral-pol`: refused at start-up); help text and docs read at master 486d0f5f2277818bd8082b5e7eb8b3f762b14bc3
Duplicates checked: WSClean issues/MRs ("save-source-list", "fitting method"; nearest MR !665 "Produce immediate error when source list is asked with incorrect fitting", which added the start-up check but no help text; issues #98, #100 are about the list's contents)
Title: -save-source-list help and component_list.rst do not state its restrictions
---
`main/settings.cpp:378-395` (master 486d0f5) refuses `-save-source-list`

- unless exactly one polarization is imaged and it is I, XX, YY, LL or RR;
- when `-channels-out > 1` with `-join-channels` and no spectral fitting
  (`-fit-spectral-pol` / `-fit-spectral-log-pol`): "Saving a source list with multiple channels
  requires specifying a fitting method";
- with `-niter 0`.

The help text (`main/commandline.cpp:529-531`) and `doc/source/component_list.rst` mention none of
these. Since !665 the error comes at start-up, so this only costs a failed launch, but the help
could say, e.g.:

```
-save-source-list
   Saves the found clean components as a BBS/DP3 text sky model. Requires cleaning (-niter > 0) and a
   single Stokes I (or XX, YY, LL, RR) image; with -join-channels and -channels-out > 1 it also
   requires -fit-spectral-pol or -fit-spectral-log-pol. This parameter enables Gaussian shapes during
   multi-scale cleaning (-multiscale-shape gaussian).
```
