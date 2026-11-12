set -e
cd /mnt/c/Users/gijsm/Github/rang/.claude/worktrees/eloquent-lovelace-8bb556/tools/oracles/obit
/usr/bin/time -f "%e s wall, %M kB maxrss (docker client) build-full" docker build --progress=plain -t rang-obit:dc26694 . 2>&1 | tail -120
docker run --rm rang-obit:dc26694 sh -c 'cat /obit-commit.txt; wc -l /obit-tasks.txt; grep -c warning /obit-make.log; ls -la /src/Obit/ObitSystem/Obit/bin/MFImage; tail -3 /obit-py.log'
