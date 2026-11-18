#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# `docker` on nash (research/wsclean38-rebaseline.md, amendment 1): rootless podman, with
# "--user UID:GID" replaced by --userns=keep-id so the container can write bind mounts.
args=()
while [ $# -gt 0 ]; do
  if [ "$1" = --user ]; then args+=(--userns=keep-id); shift 2; continue; fi
  args+=("$1"); shift
done
exec podman "${args[@]}"
