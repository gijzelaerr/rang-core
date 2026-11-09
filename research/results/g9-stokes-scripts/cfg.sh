# cfg.sh: the configurations of research/g9-stokes.md (sourced by run_g.sh and run_w.sh).
BASE=(-size 2048 2048 -scale 1.5asec -weight briggs 0.5 -niter 1000000 -gain 0.1 -nmiter 1000 -data-column DATA -field 0 -j 16)
# data_of SKY: the MS of a sky (D1 is G3's, read in place).
data_of() {
  case $1 in
    D1) echo /mnt/d/rang/outputs/20261106-g3-spectral/data/D1.ms ;;
    P1) echo /mnt/d/rang/outputs/g9-20261107-02/data/P1.ms ;;
    H1p) echo /mnt/d/rang/outputs/g9-20261107-03/data/H1p.ms ;;
    *) echo "unknown sky $1" >&2; return 2 ;;
  esac
}
cfg_args() {
  case $1 in
    Q0) c=(-pol I -abs-threshold 0.00015) ;;
    Q1) c=(-pol IQUV -abs-threshold 0.00015) ;;
    Q2) c=(-pol IQUV -join-polarizations -abs-threshold 0.00015) ;;
    Q3) c=(-pol IQUV -join-polarizations -channels-out 8 -join-channels -abs-threshold 0.00015) ;;
    Q4) c=(-pol xx,yy -niter 0) ;;
    Q5) c=(-pol IQUV -channels-out 4 -niter 0) ;;
    Q6) c=(-pol QU -join-polarizations -channels-out 4 -join-channels -abs-threshold 0.00015) ;;
    *) echo "unknown configuration $1" >&2; return 2 ;;
  esac
}
