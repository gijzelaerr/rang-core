Target: https://gitlab.com/aroffringa/wsclean/-/issues
Status: ready to post
Reproduced on: run on WSClean 3.7 (`-pol IQ -join-polarizations -niter 1`, two-source simulation); read in source at WSClean master 486d0f5f2277818bd8082b5e7eb8b3f762b14bc3 with Radler 703c1bd79aa97a27e9a69076ebf4f95f18f02bec (its pin; Radler master 109057d has the same code)
Duplicates checked: WSClean issues/MRs ("join-polarizations", "sum of squares"; "linear sum" (0 hits) and "peak finding" (nearest #103 "-squared-channel-joining finding low signal clean components", closed 2022: the explicit squared flag, not the default rule) rerun 2026-11-12; nearest #169 "Multiscale and squared-channel-joining", #197 "-fit-rm" question; neither covers this); Radler MRs ("join", "polarization", "squared", "GetLinearIntegrated"; nearest !152 "Fix squared channel issue", !53 "Spectral fitting with joined polarizations")
Title: -join-polarizations: help and docs say peaks are found in the sum of squares; the default clean finds them in the linear sum
---
`wsclean --help` (master `main/commandline.cpp:467-470`, v3.7 `:457`):

> -join-polarizations
>    Perform deconvolution by searching for peaks in the sum of squares of the polarizations, ...

and `doc/source/rm_synthesis.rst:89-91` says `-pol QU -join-polarizations -channels-out 100`
finds peaks in Q^2 + U^2.

The default (fast sub-minor) Högbom path does not. Without `-squared-channel-joining`,
`ImageSet::GetLinearIntegrated` (Radler `cpp/image_set.h:150-166`, `image_set.cc:422-460`)
returns `f * sum_ch w_ch * sum_p r_p` (f = polarization normalisation), and that is what is
searched in:

- `SubMinorModel::GetMaxComponent` and `SubMinorLoop::findPeakPositions`
  (`cpp/algorithms/subminor_loop.cc:49`, `:179`);
- the first peak of every major iteration in `GenericClean::ExecuteMajorIteration`
  (`cpp/algorithms/generic_clean.cc:70`).

Only the `-no-fast-subminor` loop switches to `GetSquareIntegrated` after its first component
(`generic_clean.cc:197`), so that path mixes both rules. The comment at `image_set.h:150-160`
says the square form "should be used for peak finding" and the linear one is meant for
multiscale.

Reproduction (WSClean 3.7): two point sources, A with I = 1, Q = -0.8 and B with I = 0.6,
Q = +0.5. Sum of squares: A 1.64, B 0.61. Linear sum: A 0.2, B 1.1.
`-pol IQ -join-polarizations -niter 1` puts the first component on B, in the default loop and
with `-no-fast-subminor`.

This matters most for `-pol QU -join-polarizations` (the documented RM case): a component with
Q ~ -U has a small Q + U and is found late or not at all, which is what the docs say the
option avoids.

Either the help text and `rm_synthesis.rst` should say the linear sum (and that
`-join-channels -squared-channel-joining` switches to squares), or the default path should call
`GetSquareIntegrated` for joined polarizations, as the `-no-fast-subminor` loop already does
after its first pick.
