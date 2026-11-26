#!/bin/bash
set -euo pipefail
cd ~/Build/tmp/20261124-selfcal-mem-34
./run.sh base
./run.sh pipeline M0 4096
