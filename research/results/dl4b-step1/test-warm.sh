H=/mnt/c/Users/gijsm/Github/rang/.claude/worktrees/v8a-listobs-1c691e
PY=$HOME/Build/tmp/20261120-dl4b-torch/bin/python
S=$HOME/Build/tmp/20261121-dl4b-step1
rm -rf /mnt/d/rang/dl4b-step1/test-warm
$PY $H/examples/dl4b_train1.py train $S/skies /mnt/d/rang/dl4b-step1/test-warm --seed 1 --hours 0.4 --steps-total 12000 --steps-max 700 --first-val 600 --batch 8 2>&1 | grep -E "step|abort"
$PY -c "import torch;c=torch.load('/mnt/d/rang/dl4b-step1/test-warm/ckpt.pt',weights_only=False);print([round(r,3) for s,r in c['state']['ratio']])"
