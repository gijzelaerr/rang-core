#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# A Slurm cluster in rootless podman containers on one host
# (research/multinode-2.md section 1.2): one controller `ctl` (also the login
# node: the parent `rang-core` runs there) and NODES compute nodes n1..nN,
# on a private podman network (no published port). Every container runs
# under nice 19 / ionice idle and bind-mounts the same host paths at the
# same paths: the shared directory SHARED (MS copies, spool, logs) read-write,
# MOUNTS read-only (the checkout with its .venv and uv's Python).
#
#   slurm_cluster.sh up SHARED NODES CPUS MEM_MB [MOUNT...]
#   slurm_cluster.sh down
#   slurm_cluster.sh kill NODE          # node loss: SIGKILL the container
#   slurm_cluster.sh restart NODE       # bring it back; wait until all idle
#   slurm_cluster.sh wait               # wait until every node is idle
#   slurm_cluster.sh exec CMD...        # run CMD on ctl
#
# The controller (and login node) gets CTL_CPUS (default 4) and CTL_MEM_MB
# (default 16000): the parent stage runs there.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
NET=rang-mn
IMAGE=localhost/rang-slurm:24.11
PREFIX=rangmn
SUBNET=10.89.78

wait_idle() {  # every one of $1 nodes idle, within 300 s
  # A node that was killed comes back DOWN ("Not responding") or drained, or
  # with its lost job still completing: resume it once it answers again.
  local idle
  for _ in $(seq 150); do
    idle=$(podman exec "$PREFIX-ctl" sinfo -h -o '%T %D' 2>/dev/null | awk '$1=="idle"{s+=$2} END{print s+0}')
    [ "$idle" = "$1" ] && { podman exec "$PREFIX-ctl" sinfo; return 0; }
    for n in $(podman exec "$PREFIX-ctl" sinfo -h -N -o '%N %T' 2>/dev/null | awk '$2 ~ /^(down|drain|drng|fail)/ && $2 !~ /\*$/ {print $1}'); do
      podman exec "$PREFIX-ctl" scontrol update nodename="$n" state=resume >/dev/null 2>&1 || true
    done
    sleep 2
  done
  podman exec "$PREFIX-ctl" sinfo -N -l || true
  echo "cluster not idle after 300 s" >&2
  return 1
}

nodes() {
  local conf
  conf=$(podman inspect -f '{{range .Mounts}}{{if eq .Destination "/cluster"}}{{.Source}}{{end}}{{end}}' "$PREFIX-ctl")
  cat "$conf/nodes"
}

cmd=${1:?usage}; shift
case "$cmd" in
up)
  SHARED=$1; NODES=$2; CPUS=$3; MEM=$4; shift 4
  mkdir -p "$SHARED/cluster"
  nice -n 19 podman build -q -t "$IMAGE" -f "$HERE/Containerfile.slurm" "$HERE" >/dev/null
  # Fixed addresses: slurmctld caches a node's address, and a restarted
  # container would otherwise come back on a new one, "Not responding"
  # (the void SlNode rerun of 2026-11-26).
  # A fresh network every time: one left by an earlier run may lack the
  # subnet the fixed addresses need (podman exit 125, 2026-11-26).
  podman ps -a --format '{{.Names}}' | grep "^$PREFIX-" | xargs -r podman rm -f -t 2 >/dev/null || true
  if podman network exists "$NET"; then podman network rm "$NET" >/dev/null; fi
  podman network create --subnet "$SUBNET.0/24" "$NET" >/dev/null
  hosts=(--add-host "ctl:$SUBNET.10")
  for i in $(seq 1 "$NODES"); do hosts+=(--add-host "n$i:$SUBNET.$((10 + i))"); done
  conf="$SHARED/cluster"
  sed -e "s/@NODES@/$NODES/" -e "s/@CPUS@/$CPUS/" -e "s/@MEM_MB@/$MEM/" \
    "$HERE/slurm.conf.in" > "$conf/slurm.conf"
  cp "$HERE/cgroup.conf" "$conf/cgroup.conf"
  [ -f "$conf/munge.key" ] || head -c 1024 /dev/urandom > "$conf/munge.key"
  chmod 600 "$conf/munge.key"
  echo "$NODES" > "$conf/nodes"
  vols=(-v "$SHARED:$SHARED")
  for m in "$@"; do vols+=(-v "$m:$m:ro"); done
  boot='install -o munge -g munge -m 400 /cluster/munge.key /etc/munge/munge.key
    cp /cluster/slurm.conf /cluster/cgroup.conf /etc/slurm/
    mkdir -p /run/munge && chown munge:munge /run/munge
    runuser -u munge -- munged
    exec "$@"'
  start() {  # name, ip, cpus, memory MB, daemon command...
    local name=$1 ip=$2 cpus=$3 mem=$4
    shift 4
    nice -n 19 ionice -c3 podman run -d --name "$PREFIX-$name" --hostname "$name" \
      --network "$NET" --ip "$ip" "${hosts[@]}" --cpus "$cpus" --memory "${mem}m" \
      -v "$conf:/cluster:ro" "${vols[@]}" -w "$SHARED" \
      "$IMAGE" bash -c "$boot" _ "$@" >/dev/null
  }
  start ctl "$SUBNET.10" "${CTL_CPUS:-4}" "${CTL_MEM_MB:-16000}" slurmctld -D
  sleep 3
  for i in $(seq 1 "$NODES"); do
    start "n$i" "$SUBNET.$((10 + i))" "$CPUS" "$MEM" slurmd -D -N "n$i"
  done
  wait_idle "$NODES" ;;
down)
  podman ps -a --format '{{.Names}}' | grep "^$PREFIX-" | xargs -r podman rm -f -t 2 >/dev/null || true
  podman network exists "$NET" && podman network rm "$NET" >/dev/null || true ;;
kill)
  podman kill -s KILL "$PREFIX-$1" >/dev/null ;;
restart)
  podman start "$PREFIX-$1" >/dev/null
  wait_idle "$(nodes)" ;;
wait)
  wait_idle "$(nodes)" ;;
exec)
  podman exec -w "$PWD" "$PREFIX-ctl" "$@" ;;
*) echo "unknown command $cmd" >&2; exit 2 ;;
esac
