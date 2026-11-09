# cfg.sh: the runs of research/g5-multiscale.md, section 3 (sourced by run_g.sh and run_w.sh).
# run_args RUN sets: ms (the Measurement Set), c (options beyond BASE).
O=${G5_OUT:-/mnt/d/rang/outputs/g5-20261107-01}
BENCH=/mnt/d/rang/outputs/20261102-gemclean/bench/data
HELD=/mnt/d/rang/outputs/20261103-gemclean-heldout
G3=/mnt/d/rang/outputs/20261106-g3-spectral/data
M1DIR=/mnt/d/rang/outputs/g5-20261107-03/data
BASE=(-weight briggs 0.5 -niter 1000000 -gain 0.1 -nmiter 1000 -data-column DATA -field 0 -j 16)
SIM=(-size 2048 2048 -scale 1.5asec -abs-threshold 0.0001)
run_args() {
  case $1 in
    S2) ms=$BENCH/s2.ms; c=("${SIM[@]}" -mgain 0.8 -multiscale) ;;
    S2g) ms=$BENCH/s2.ms; c=("${SIM[@]}" -mgain 0.8 -multiscale -multiscale-shape gaussian) ;;
    H4) ms=$HELD/sim/data/h4.ms; c=("${SIM[@]}" -mgain 0.8 -multiscale) ;;
    H4l) ms=$HELD/sim/data/h4.ms; c=("${SIM[@]}" -mgain 0.8 -multiscale -multiscale-scales 0,5,15,45,135) ;;
    D2j) ms=$G3/D2.ms; c=(-size 2048 2048 -scale 1.5asec -abs-threshold 0.00015 -mgain 0.8 -multiscale
                         -channels-out 8 -join-channels -fit-spectral-pol 4) ;;
    P) ms=$HELD/real/cal2.ms; c=(-size 4096 4096 -scale 3asec -abs-threshold 0.003 -mgain 0.8 -multiscale) ;;
    M1) ms=$M1DIR/m1.ms; c=("${SIM[@]}" -mgain 0.8 -multiscale) ;;
    # Reported only.
    S2m) ms=$BENCH/s2.ms; c=("${SIM[@]}" -multiscale) ;;
    H4m) ms=$HELD/sim/data/h4.ms; c=("${SIM[@]}" -multiscale) ;;
    S2a) ms=$BENCH/s2.ms; c=(-size 2048 2048 -scale 1.5asec -auto-threshold 3 -mgain 0.8 -multiscale) ;;
    D2u) ms=$G3/D2.ms; c=(-size 2048 2048 -scale 1.5asec -abs-threshold 0.0003 -mgain 0.8 -multiscale
                         -channels-out 4) ;;
    *) echo "unknown run $1" >&2; return 2 ;;
  esac
}
