# Licence requests to four upstream projects

Status, 2026-11-20: **three posted on the owner's word, one settled by owner decision.** Posted with the
paragraphs joined and no other change: [basp-group/AIRI#3](https://github.com/basp-group/AIRI/issues/3),
[astro-informatics/rcGAN#6](https://github.com/astro-informatics/rcGAN/issues/6),
[LOFAR-VLBI/astroNNomy#1](https://github.com/LOFAR-VLBI/astroNNomy/issues/1). **R2D2-RI: not posted**;
owner decision, 2026-11-20, verbatim: "for r2d2-RI we can assume it is GPL, it says it in the readme!" So
R2D2-RI is taken as GPL-3.0 by its README badge, and no issue is opened; its draft below is kept as
written. The drafts were revised the same day for two owner corrections, verbatim: "rang-core is part of
the ra-ng package. we are working on ra-ng. also we want to be MIT, but use GPL where required." Source of
the list: [dl0-profile.md](../dl0-profile.md) section 5. Checked 2026-11-20 with the GitHub API (`gh api
repos/...`, `gh issue list --state all --search "licence OR license"`): no licence issue existed, open or
closed, on any of the four. Maintainers are the top committers by GitHub's contributor count; the issues
@-mention no one.

Licence stance in the drafts: ra-ng aims to be MIT-licensed and uses GPL only where a dependency requires
it ([mit-relicense-audit.md](../mit-relicense-audit.md)); the repository's LICENSE is still
GPL-3.0-or-later today, so the drafts do not claim MIT. The ask: code under a permissive licence (MIT,
BSD-3-Clause, Apache-2.0), GPL-3.0 still workable; weights under CC BY 4.0 or CC0.

| Project | Repository | Licence now | Maintainers (commits) | Issue (2026-11-20) |
| --- | --- | --- | --- | --- |
| R2D2-RI | <https://github.com/basp-group/R2D2-RI> | none on `main` (GitHub: none); README badge says GPL-3.0; GPL-3.0 text on branches `r2d2-python-v1.0` and `gh-pages` | Taylor-Chu (35), amiraghabiglou (24), arwina (13) | not opened: GPL-3.0 by the README badge (owner decision) |
| AIRI astro-trained denoiser shelf | <https://github.com/basp-group/AIRI> (code GPL-3.0); weights: Heriot-Watt portal, DOI [10.17861/aa1f43ee-2950-4fce-9140-5ace995893b0](https://doi.org/10.17861/aa1f43ee-2950-4fce-9140-5ace995893b0) | code GPL-3.0; MRI-trained shelf CC BY; astro-trained (OAID) files have no licence field | ChaoTang0330 (120), arwina (32) | [#3](https://github.com/basp-group/AIRI/issues/3), posted |
| rcGAN (RI-GAN) | <https://github.com/astro-informatics/rcGAN> (fork of <https://github.com/matt-bendel/rcGAN>) | none on either; weights CC BY 4.0 on Zenodo 16529320 | JessWhitney (192), tobias-liaudat (77), MatthijsMars (21); upstream matt-bendel | [#6](https://github.com/astro-informatics/rcGAN/issues/6), posted (on the fork) |
| astroNNomy | <https://github.com/LOFAR-VLBI/astroNNomy> | none; weights on a SURF share, licence unstated | LVeefkind (32), robogast (3) | [#1](https://github.com/LOFAR-VLBI/astroNNomy/issues/1), posted |

For rcGAN the issue goes to the astro-informatics fork (the RI-GAN code); it also asks whether the
upstream's terms allow a licence, because the fork carries matt-bendel's code.

## 1. basp-group/R2D2-RI (not posted: owner decision)

**Title:** Add a LICENSE file to `main` (the README badge says GPL-3.0)

> Hello, and thank you for releasing R2D2 and its trained series.
>
> We work on ra-ng, an open-source project for radio astronomy (MeerKAT calibration and imaging);
> rang-core (<https://github.com/gijzelaerr/rang-core>) is its first package. We would like to use
> R2D2-RI as a comparator for learned deconvolution, and possibly train a series on MeerKAT uv
> coverages with your training code.
>
> The README's badge says GPL-3.0 and links to `LICENSE`, but `main` has no LICENSE file and GitHub
> reports no licence (the GPL-3.0 text is on the `r2d2-python-v1.0` and `gh-pages` branches). Could you
> add it to `main`? GPL-3.0 works for us; ra-ng aims to be MIT-licensed, so a permissive licence (MIT,
> BSD-3-Clause, Apache-2.0) would make reuse easier, if you are open to it. The CC BY weights are fine.
>
> Thank you.

## 2. basp-group/AIRI (the astro-trained denoiser shelf): posted as #3

**Title:** Licence of the astro-trained (OAID) denoiser shelf

> Hello, and thank you for AIRI and for publishing the denoiser shelves.
>
> We work on ra-ng, an open-source project for radio astronomy (MeerKAT calibration and imaging);
> rang-core (<https://github.com/gijzelaerr/rang-core>) is its first package. Your MeerKAT results make
> AIRI the learned imager we would most like to compare against on our data.
>
> On the Heriot-Watt record (DOI 10.17861/aa1f43ee-2950-4fce-9140-5ace995893b0) the MRI-trained shelf
> carries CC BY, but the astro-trained (OAID) files show no licence. Could you state one for them,
> CC BY 4.0 like the MRI shelf, or CC0?
>
> Thank you.

## 3. astro-informatics/rcGAN: posted as #6

**Title:** Licence for the rcGAN / RI-GAN code

> Hello, and thank you for RI-GAN and the trained models on Zenodo (16529320, CC BY 4.0).
>
> We work on ra-ng, an open-source project for radio astronomy (MeerKAT calibration and imaging);
> rang-core (<https://github.com/gijzelaerr/rang-core>) is its first package. RI-GAN, trained on
> MeerKAT uv coverages with the PSF in the network, is a natural baseline for a quick-look imaging
> stage we are scoping.
>
> The repository has no licence file, and neither has its upstream (matt-bendel/rcGAN), so we cannot
> reuse the code. Could you add one? ra-ng aims to be MIT-licensed, so MIT, BSD-3-Clause or Apache-2.0
> would suit us best; GPL-3.0 would still work. If the upstream's terms need settling first, we would be
> glad to know.
>
> Thank you.

## 4. LOFAR-VLBI/astroNNomy: posted as #1

**Title:** Licence for the code and the trained classifier weights

> Hello, and thank you for the selfcal image classifier (de Jong et al. 2025, arXiv:2508.12115) and
> its code.
>
> We work on ra-ng, an open-source project for radio astronomy (MeerKAT calibration and imaging);
> rang-core (<https://github.com/gijzelaerr/rang-core>) is its first package. Your "continue or stop"
> classifier is the closest published work to a stage we are scoping: deciding from the image when
> self-calibration can stop.
>
> The repository has no licence file, and the weights that `lofar_facet_selfcal` downloads from the
> SURF share do not state one. Could you add a code licence (MIT, BSD-3-Clause or Apache-2.0 would suit
> us best, as ra-ng aims to be MIT-licensed; GPL-3.0 would still work) and state one for the weights
> (CC BY 4.0 or CC0)?
>
> Thank you.
