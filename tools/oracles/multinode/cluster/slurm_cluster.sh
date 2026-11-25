#!/usr/bin/env bash
# A Slurm cluster in rootless podman containers on one host
# (research/multinode-2.md section 2): one controller `ctl` (also the login
# node: the parent `rang-core` runs there) and NODES compute nodes n1..nN,
# on a private podman network (no published port). Every container runs
# under nice 19 / ionice idle and bind-mounts the same host paths at the
# same paths: the shared directory SHARED (MS copies, spool, logs) read-write,
# MOUNTS read-only (the checkout with its .venv and uv's Python).
#
#   slurm_cluster.sh up SHARED NODES CPUS MEM_MB [MOUNT...]
#   slurm_cluster.sh down
#   slurm_cluster.sh kill NODE          # node loss: SIGKILL the container
#   slurm_cluster.sh exec CMD...        # run CMD on ctl
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
NET=rang-mn
IMAGE=localhost/rang-slurm:24.11
PREFIX=rangmn

cmd=${1:?usage}; shift
case "$cmd" in
up)
  SHARED=$1; NODES=$2; CPUS=$3; MEM=$4; shift 4
  mkdir -p "$SHARED/cluster"
  nice -n 19 podman build -q -t "$IMAGE" -f "$HERE/Containerfile.slurm" "$HERE" >/dev/null
  podman network exists "$NET" || podman network create "$NET" >/dev/null
  conf="$SHARED/cluster"
  sed -e "s/@NODES@/$NODES/" -e "s/@CPUS@/$CPUS/" -e "s/@MEM_MB@/$MEM/" \
    "$HERE/slurm.conf.in" > "$conf/slurm.conf"
  cp "$HERE/cgroup.conf" "$conf/cgroup.conf"
  [ -f "$conf/munge.key" ] || head -c 1024 /dev/urandom > "$conf/munge.key"
  chmod 600 "$conf/munge.key"
  vols=(-v "$SHARED:$SHARED")
  for m in "$@"; do vols+=(-v "$m:$m:ro"); done
  boot='install -o munge -g munge -m 400 /cluster/munge.key /etc/munge/munge.key
    cp /cluster/slurm.conf /cluster/cgroup.conf /etc/slurm/
    mkdir -p /run/munge && chown munge:munge /run/munge
    runuser -u munge -- munged
    exec "$@"'
  start() {  # name, daemon command...
    local name=$1; shift
    nice -n 19 ionice -c3 podman run -d --name "$PREFIX-$name" --hostname "$name" \
      --network "$NET" --cpus "$CPUS" --memory "${MEM}m" \
      -v "$conf:/cluster:ro" "${vols[@]}" -w "$SHARED" \
      "$IMAGE" bash -c "$boot" _ "$@" >/dev/null
  }
  start ctl slurmctld -D
  sleep 3
  for i in $(seq 1 "$NODES"); do start "n$i" slurmd -D -N "n$i"; done
  for _ in $(seq 60); do
    idle=$(podman exec "$PREFIX-ctl" sinfo -h -o '%T %D' 2>/dev/null | awk '$1=="idle"{s+=$2} END{print s+0}')
    [ "$idle" = "$NODES" ] && { podman exec "$PREFIX-ctl" sinfo; exit 0; }
    sleep 2
  done
  podman exec "$PREFIX-ctl" sinfo || true
  echo "cluster not idle after 120 s" >&2; exit 1 ;;
down)
  podman ps -a --format '{{.Names}}' | grep "^$PREFIX-" | xargs -r podman rm -f -t 2 >/dev/null
  podman network exists "$NET" && podman network rm "$NET" >/dev/null || true ;;
kill)
  podman kill -s KILL "$PREFIX-$1" >/dev/null ;;
exec)
  podman exec -w "$PWD" "$PREFIX-ctl" "$@" ;;
*) echo "unknown command $cmd" >&2; exit 2 ;;
esac
