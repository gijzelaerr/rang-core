# Debian 13 (trixie) with Slurm 24.11 and munge from the Debian archive.
# Slurm 24.05 and later accept CgroupPlugin=disabled, which a rootless
# container needs (Ubuntu 24.04's 23.11 does not: research/multinode-2.md 0.2).
# glibc 2.41 here, newer than nash's 2.39, so the host-built _core and uv's
# Python run unchanged from read-only mounts.
FROM docker.io/library/debian:trixie
RUN apt-get update -qq \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq slurm-wlm munge procps iproute2 >/dev/null \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /var/spool/slurmctld /var/spool/slurmd /var/log/slurm
