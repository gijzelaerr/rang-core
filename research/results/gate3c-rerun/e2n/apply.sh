#!/bin/bash
s=$(date +%s)
~/Build/tmp/20261123-gate3c-rerun/e2n-venv/bin/python -m rang.core_cli apply ~/Worktrees/rang/gate3c-rerun/research/results/e2n-scripts/e2n.yaml /home/gijs/rang-data/outputs/gate3c-rerun-20261123/e2n.ms --run-dir /home/gijs/rang-data/outputs/gate3c-rerun-20261123/n/rang-run --force
echo "apply rc=$? $(( $(date +%s)-s ))s"
