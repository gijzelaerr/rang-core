#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# An OpenPBS cluster in rootless podman containers on one host
# (research/multinode-2.md section 1.2): a server `pbs` (pbs_server,
# pbs_sched, pbs_comm and the PostgreSQL datastore; also the login node, where
# the parent runs) and NODES execution hosts m1..mN (pbs_mom), on a private
# podman network with fixed addresses (PBS wants forward and reverse lookups
# to agree; no published port). Mounts as slurm_cluster.sh: SHARED read-write,
# MOUNTS read-only, at the same paths; every container at nice 19 / ionice idle.
#
#   pbs_cluster.sh up SHARED NODES CPUS MEM_MB [MOUNT...]
#   pbs_cluster.sh down
#   pbs_cluster.sh kill NODE       # node loss: SIGKILL the container
#   pbs_cluster.sh restart NODE    # bring a killed node back
#   pbs_cluster.sh exec CMD...     # run CMD on the server (login node)
#
# The server (and login node) gets CTL_CPUS (default 4) and CTL_MEM_MB
# (default 16000).
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
NET=rang-pbs
SUBNET=10.89.77
IMAGE=localhost/rang-pbs:master
PREFIX=rangpbs

hosts() {  # --add-host for the server and every node
  local n=$1 out=(--add-host "pbs:$SUBNET.10")
  for i in $(seq 1 "$n"); do out+=(--add-host "m$i:$SUBNET.$((10 + i))"); done
  echo "${out[@]}"
}

start() {  # name ip server|mom SHARED NODES CPUS MEM MOUNTS...
  local name=$1 ip=$2 role=$3 shared=$4 nodes=$5 cpus=$6 mem=$7; shift 7
  local vols=(-v "$shared:$shared")
  for m in "$@"; do vols+=(-v "$m:$m:ro"); done
  local conf
  if [ "$role" = server ]; then
    conf='PBS_START_SERVER=1\nPBS_START_SCHED=1\nPBS_START_COMM=1\nPBS_START_MOM=0'
  else
    conf='PBS_START_SERVER=0\nPBS_START_SCHED=0\nPBS_START_COMM=0\nPBS_START_MOM=1'
  fi
  local boot="printf 'PBS_SERVER=pbs\nPBS_EXEC=/opt/pbs\nPBS_HOME=/var/spool/pbs\nPBS_CORE_LIMIT=unlimited\nPBS_SCP=/usr/bin/scp\n$conf\n' > /etc/pbs.conf
    if [ $role = mom ]; then
      mkdir -p /var/spool/pbs/mom_priv
      printf '\$clienthost pbs\n\$usecp *:/ /\n' > /var/spool/pbs/mom_priv/config
    fi
    /opt/pbs/libexec/pbs_init.d start
    exec sleep infinity"
  # shellcheck disable=SC2046
  nice -n 19 ionice -c3 podman run -d --name "$PREFIX-$name" --hostname "$name" \
    --network "$NET" --ip "$ip" $(hosts "$nodes") --cpus "$cpus" --memory "${mem}m" \
    "${vols[@]}" -w "$shared" "$IMAGE" bash -c "$boot" >/dev/null
}

wait_free() {  # every one of $1 nodes free, within 300 s
  local free
  for _ in $(seq 150); do
    free=$(podman exec "$PREFIX-pbs" /opt/pbs/bin/pbsnodes -a 2>/dev/null | grep -c "state = free" || true)
    [ "$free" = "$1" ] && { podman exec "$PREFIX-pbs" /opt/pbs/bin/pbsnodes -aSj; return 0; }
    sleep 2
  done
  podman exec "$PREFIX-pbs" /opt/pbs/bin/pbsnodes -a || true
  echo "nodes not free after 300 s" >&2
  return 1
}

cmd=${1:?usage}; shift
case "$cmd" in
up)
  SHARED=$1; NODES=$2; CPUS=$3; MEM=$4; shift 4
  nice -n 19 podman build -q -t "$IMAGE" -f "$HERE/Containerfile.pbs" "$HERE" >/dev/null
  # A fresh network every time (as slurm_cluster.sh).
  podman ps -a --format '{{.Names}}' | grep "^$PREFIX-" | xargs -r podman rm -f -t 2 >/dev/null || true
  if podman network exists "$NET"; then podman network rm "$NET" >/dev/null; fi
  podman network create --subnet "$SUBNET.0/24" "$NET" >/dev/null
  start pbs "$SUBNET.10" server "$SHARED" "$NODES" "${CTL_CPUS:-4}" "${CTL_MEM_MB:-16000}" "$@"
  for i in $(seq 1 "$NODES"); do
    start "m$i" "$SUBNET.$((10 + i))" mom "$SHARED" "$NODES" "$CPUS" "$MEM" "$@"
  done
  q() {  # qmgr, retried: the server may still be starting on a loaded host
    for _ in $(seq 30); do
      podman exec "$PREFIX-pbs" /opt/pbs/bin/qmgr -c "$1" 2>/dev/null && return 0
      sleep 2
    done
    podman exec "$PREFIX-pbs" /opt/pbs/bin/qmgr -c "$1"
  }
  for _ in $(seq 150); do
    podman exec "$PREFIX-pbs" /opt/pbs/bin/qstat -B >/dev/null 2>&1 && break
    sleep 2
  done
  q "set server acl_roots = root"
  q "set server flatuid = true"
  q "set server job_history_enable = true"
  for i in $(seq 1 "$NODES"); do
    podman exec "$PREFIX-pbs" /opt/pbs/bin/qmgr -c "create node m$i" 2>/dev/null || true
    # What the container may use, not what the host has.
    q "set node m$i resources_available.ncpus = $CPUS"
    q "set node m$i resources_available.mem = ${MEM}mb"
  done
  echo "$NODES" > "$SHARED/cluster-pbs.nodes"
  wait_free "$NODES" ;;
down)
  podman ps -a --format '{{.Names}}' | grep "^$PREFIX-" | xargs -r podman rm -f -t 2 >/dev/null || true
  podman network exists "$NET" && podman network rm "$NET" >/dev/null || true ;;
kill)
  podman kill -s KILL "$PREFIX-$1" >/dev/null ;;
restart)
  podman start "$PREFIX-$1" >/dev/null
  wait_free "$(cat "$(podman inspect -f '{{.Config.WorkingDir}}' "$PREFIX-pbs")/cluster-pbs.nodes")" ;;
wait)
  wait_free "$(cat "$(podman inspect -f '{{.Config.WorkingDir}}' "$PREFIX-pbs")/cluster-pbs.nodes")" ;;
exec)
  podman exec -w "$PWD" "$PREFIX-pbs" "$@" ;;
*) echo "unknown command $cmd" >&2; exit 2 ;;
esac
