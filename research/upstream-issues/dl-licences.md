# Licence requests to four upstream projects (drafts, not posted)

Status, 2026-11-20: **drafts for the owner; nothing posted, nobody contacted.** Source of the list:
[dl0-profile.md](../dl0-profile.md) section 5. Checked 2026-11-20 with the GitHub API (`gh api repos/...`,
`gh issue list --state all --search "licence OR license"`): no licence issue exists, open or closed,
on any of the four, so each needs a new issue. Maintainers are the top committers by GitHub's
contributor count; in the drafts no one is @-mentioned (the owner decides whether to tag anyone).

What we would find compatible, for a project that is GPL-3.0-or-later
([LICENSE](../../LICENSE)): code under GPL-3.0(-or-later) or a permissive licence (MIT, BSD-3-Clause,
Apache-2.0); weights and data under CC BY 4.0 or CC0.

| Project | Repository | Licence now | Maintainers (commits) | Existing issue |
| --- | --- | --- | --- | --- |
| R2D2-RI | <https://github.com/basp-group/R2D2-RI> | none on `main` (GitHub: none); README badge says GPL-3.0; GPL-3.0 text on branches `r2d2-python-v1.0` and `gh-pages` | Taylor-Chu (35), amiraghabiglou (24), arwina (13) | none |
| AIRI astro-trained denoiser shelf | <https://github.com/basp-group/AIRI> (code GPL-3.0); weights: Heriot-Watt portal, DOI [10.17861/aa1f43ee-2950-4fce-9140-5ace995893b0](https://doi.org/10.17861/aa1f43ee-2950-4fce-9140-5ace995893b0) | code GPL-3.0; MRI-trained shelf CC BY; astro-trained (OAID) files have no licence field | ChaoTang0330 (120), arwina (32) | none |
| rcGAN (RI-GAN) | <https://github.com/astro-informatics/rcGAN> (fork of <https://github.com/matt-bendel/rcGAN>) | none on either; weights CC BY 4.0 on Zenodo 16529320 | JessWhitney (192), tobias-liaudat (77), MatthijsMars (21); upstream matt-bendel | none (on either) |
| astroNNomy | <https://github.com/LOFAR-VLBI/astroNNomy> | none; weights on a SURF share, licence unstated | LVeefkind (32), robogast (3) | none |

For rcGAN the issue goes to the astro-informatics fork (the RI-GAN code); it also asks whether the
upstream's terms allow a licence, because the fork carries matt-bendel's code.

## 1. basp-group/R2D2-RI

**Title:** Add a LICENSE file to `main` (the README badge says GPL-3.0)

> Hello, and thank you for releasing R2D2 and its trained series.
>
> We work on rang-core (<https://github.com/gijzelaerr/rang-core>), an open-source
> GPL-3.0-or-later package for calibration and imaging of MeerKAT data. We are evaluating learned
> deconvolution and would like to use R2D2-RI as a comparator, and possibly to train a series on
> MeerKAT uv coverages with your training code.
>
> The README's badge says GPL-3.0 and links to `LICENSE`, but `main` has no LICENSE file, and GitHub
> reports no licence for the repository. The GPL-3.0 text is present on the `r2d2-python-v1.0` and
> `gh-pages` branches. Could you add the licence file to `main`? GPL-3.0, or GPL-3.0-or-later, would
> suit us; any OSI licence compatible with GPL-3.0 would too. The released weights are already CC BY
> on the Heriot-Watt portal, which is fine for us.
>
> Thank you.

## 2. basp-group/AIRI (the astro-trained denoiser shelf)

**Title:** Licence of the astro-trained (OAID) denoiser shelf

> Hello, and thank you for AIRI and for publishing the denoiser shelves.
>
> We work on rang-core (<https://github.com/gijzelaerr/rang-core>), an open-source
> GPL-3.0-or-later package for calibration and imaging of MeerKAT data. Your MeerKAT results with
> AIRI make it the learned imager we would most like to compare against on our data.
>
> On the Heriot-Watt dataset record (DOI 10.17861/aa1f43ee-2950-4fce-9140-5ace995893b0), the
> MRI-trained shelf and its uncertainty set carry CC BY, but the astro-trained (OAID) files show no
> licence. Could you state a licence for them, CC BY 4.0 like the MRI shelf, or CC0? That would let
> us use and redistribute them in comparisons with attribution. The AIRI code itself is GPL-3.0,
> which suits us.
>
> Thank you.

## 3. astro-informatics/rcGAN

**Title:** Licence for the rcGAN / RI-GAN code

> Hello, and thank you for RI-GAN and for publishing the trained models on Zenodo (16529320, CC BY
> 4.0).
>
> We work on rang-core (<https://github.com/gijzelaerr/rang-core>), an open-source
> GPL-3.0-or-later package for calibration and imaging of MeerKAT data. RI-GAN, trained on MeerKAT
> uv coverages with the PSF in the network, is a natural baseline for a quick-look imaging stage
> we are scoping, and we would like to run and compare against it.
>
> The repository has no licence file, and neither has its upstream (matt-bendel/rcGAN), so we cannot
> reuse the code. Could you add one? GPL-3.0(-or-later), MIT, BSD-3-Clause or Apache-2.0 would all
> work for us. If the upstream's terms need settling first, we would be grateful to know.
>
> Thank you.

## 4. LOFAR-VLBI/astroNNomy

**Title:** Licence for the code and the trained classifier weights

> Hello, and thank you for releasing the selfcal image classifier (de Jong et al. 2025,
> arXiv:2508.12115) and its code.
>
> We work on rang-core (<https://github.com/gijzelaerr/rang-core>), an open-source
> GPL-3.0-or-later package for calibration and imaging of MeerKAT data. Your "continue or stop"
> classifier is the closest published work to a stage we are scoping: deciding from the image
> when self-calibration can stop. We would like to reuse the approach and compare against your
> weights.
>
> The repository has no licence file, and the weights that `lofar_facet_selfcal` downloads from the
> SURF share do not state one. Could you add a licence for the code (GPL-3.0(-or-later), MIT,
> BSD-3-Clause or Apache-2.0 would all suit us) and state one for the weights (CC BY 4.0 or CC0)?
>
> Thank you.
