cd /dev/shm/u5cc; export UV_CACHE_DIR=/dev/shm/u5cc/cache
export PATH=$HOME/.local/bin:$PATH
for v in 3.8.35 3.8.36 3.8.37 3.8.38 3.8.39 3.8.40; do
  rm -rf b; uv venv -q -p 3.12 b; VIRTUAL_ENV=b uv pip install -q --index-url https://pypi.org/simple casacure==$v numpy
  rm -rf w/b-*; echo "$v: $(b/bin/python -I -c "
from casacure import tables as T
t=T.table('w/b-x', T.maketabdesc([T.makearrcoldesc('FLAG', False, shape=[4,2])]), nrow=1, ack=False)
print('option', t.getcoldesc('FLAG').get('option')); t.close()" 2>&1 | tail -1)"
done; rm -rf b
