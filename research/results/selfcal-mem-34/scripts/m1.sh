#!/bin/bash
set -euo pipefail
cd ~/Build/tmp/20261124-selfcal-mem-34
./build-arm.sh
./run-arm.sh base
./run-arm.sh pipeline M1 4096
