# cfg.sh: the configurations of research/g3-spectral.md (sourced by run_g.sh and run_w.sh).
O=/mnt/d/rang/outputs/20261106-g3-spectral
BASE=(-size 2048 2048 -scale 1.5asec -weight briggs 0.5 -niter 1000000 -gain 0.1 -nmiter 1000 -data-column DATA -field 0 -j 16)
cfg_args() {
  case $1 in
    C0) c=(-abs-threshold 0.00015) ;;
    C1) c=(-channels-out 8 -join-channels -fit-spectral-pol 4 -abs-threshold 0.00015) ;;
    C2) c=(-channels-out 8 -join-channels -abs-threshold 0.00015) ;;
    C3) c=(-channels-out 4 -abs-threshold 0.0003) ;;
    C4) c=(-channel-range 2 14 -channels-out 3 -niter 0) ;;
    A1) c=(-average-channels 2 -niter 0) ;;
    A4) c=(-average-channels 2 -channels-out 4 -niter 0) ;;
    P1) c=(-niter 0) ;;
    P4) c=(-channels-out 4 -niter 0) ;;
    *) echo "unknown configuration $1" >&2; return 2 ;;
  esac
}
