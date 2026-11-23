H=/mnt/c/Users/gijsm/Github/rang/.claude/worktrees/v8a-listobs-1c691e
S=$HOME/Build/tmp/20261121-dl4b-step1
export DL4B_WSCLEAN='docker run --rm --user {uid} -v /mnt/d:/mnt/d -v /home/gijsm/Build/tmp:/home/gijsm/Build/tmp -w {cwd} rang-wsclean-native:3.7 wsclean'
mkdir -p /mnt/d/rang/dl4b-step1/onnx
$HOME/Build/tmp/20261120-dl4b-torch/bin/python $H/examples/dl4b_train1.py export /mnt/d/rang/dl4b-step1/smoke/ckpt.pt /mnt/d/rang/dl4b-step1/onnx/smoke99.onnx
cd $H && ~/Github/rang/.venv/bin/python examples/dl4b_step1.py parm $S/skies $S --names V3 --onnx smoke99=/mnt/d/rang/dl4b-step1/onnx/smoke99.onnx --taus 5 --kmax 2
