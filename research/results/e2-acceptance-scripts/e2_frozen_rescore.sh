#!/bin/sh
# Post-hoc check of e1b_score's m000 reproduction (research/e2-acceptance.md 2.3):
# the frozen e1_score.py --only composite,crosshand,k on E1's -03 now; E1's
# result.json is restored from the copy afterwards.
R=/d/rang/outputs/e1-20261109-03; O=/d/rang/outputs/e2-20261110-02-scorer
cmp -s $R/result.json $O/e1-03-result.frozen-copy.json || exit 3
.venv/Scripts/python.exe research/results/e1-chain-scripts/e1_score.py chain 'D:\rang\outputs\e1-20261109-03' --only k,composite,crosshand
rc=$?
cp $R/result.json $O/m32-frozen-rescore.json
cp $O/e1-03-result.frozen-copy.json $R/result.json
exit $rc
