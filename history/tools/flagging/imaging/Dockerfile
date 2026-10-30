# Build only after root checks the new trend overlay identity; preserve the old
# response image. This adds Debian WSClean, never reinstalls the solver/venvs.
FROM rang-flagging-next:local
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1

COPY <<EOF /opt/rang/imaging-snapshot.list
deb [arch=amd64 check-valid-until=no signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://snapshot.debian.org/archive/debian/20250901T000000Z/ trixie main
EOF

RUN python - <<'PY'
import hashlib, json, os, re, subprocess
from pathlib import Path

limit = 256 * 1024**2
snapshot = 'https://snapshot.debian.org/archive/debian/20250901T000000Z/'
def run(args):
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout
def packages():
    return dict(line.split('\t', 1) for line in run(['dpkg-query','-W','-f=${binary:Package}\t${Version}\n']).splitlines())
before = packages()
apt = ['apt-get','-o','Dir::Etc::sourcelist=/opt/rang/imaging-snapshot.list','-o','Dir::Etc::sourceparts=-','-o','Acquire::Retries=0']
run(apt + ['update'])  # Signed metadata mandatory; no trusted/unauthenticated flag.
args = ['--no-install-recommends','--no-remove','install','wsclean=3.6-1']
simulation = run(apt + ['--simulate'] + args)
new = []
for line in simulation.splitlines():
    if line.startswith(('Remv ', 'Conf ')) and line.startswith('Remv '):
        raise RuntimeError('package removal forbidden')
    if line.startswith('Inst '):
        match = re.match(r'Inst (\S+)(?: \[([^]]+)\])? \((\S+)', line)
        if not match:
            raise RuntimeError('unparsed package simulation')
        name, old, version = match.groups()
        if old is not None or name in before or name + ':amd64' in before:
            raise RuntimeError('preexisting package change forbidden: ' + name)
        record = run(['apt-cache','-o','Dir::Etc::sourcelist=/opt/rang/imaging-snapshot.list','-o','Dir::Etc::sourceparts=-','show',name+'='+version])
        fields = dict(line.split(': ',1) for line in record.split('\n\n')[0].splitlines() if ': ' in line and not line.startswith(' '))
        new.append({'name':name,'version':version,'size':int(fields['Size']),'filename':fields['Filename'],'sha256':fields['SHA256'],'url':snapshot+fields['Filename']})
if not new or sum(x['size'] for x in new) > limit:
    raise RuntimeError('advertised new-deb budget exceeds256MiB or empty plan')
Path('/opt/rang/imaging-download-plan.json').write_text(json.dumps({'snapshot':snapshot,'packages':new},indent=2)+'\n')
run(apt + ['--download-only','-y'] + args)
archive = Path('/var/cache/apt/archives')
debs = list(archive.glob('*.deb'))
actual = []
for item in new:
    found = []
    for path in debs:
        name, version = run(['dpkg-deb','-f',str(path),'Package','Version']).splitlines()
        name = name.removeprefix('Package: ')
        version = version.removeprefix('Version: ')
        if (name,version) == (item['name'],item['version']):
            found.append(path)
    if len(found) != 1:
        raise RuntimeError('missing/ambiguous downloaded package')
    path = found[0]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if path.stat().st_size != item['size'] or digest != item['sha256']:
        raise RuntimeError('signed-package size/hash mismatch')
    actual.append({**item,'downloaded_file':path.name,'actual_sha256':digest})
if sum(x.stat().st_size for x in debs) > limit or len(debs) != len(actual):
    raise RuntimeError('unexpected archives or actual256MiB cap breach')
run(apt + ['--no-download','-y'] + args)
after = packages()
if any(after.get(key) != value for key,value in before.items()):
    raise RuntimeError('preexisting package identity changed')
package_version = run(['dpkg-query','-W','-f=${Version}','wsclean']).strip()
if package_version != '3.6-1':
    raise RuntimeError('unexpected WSClean package')
binary = Path('/usr/bin/wsclean')
receipt = {'snapshot_url':snapshot,'suite':'trixie/main','architecture':'amd64','wsclean_package_version':package_version,'wsclean_binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'download_bytes':sum(x['size'] for x in actual),'download_limit_bytes':limit,'packages':actual,'complete_dpkg_packages':after,'preexisting_packages':before,'preexisting_packages_unchanged':True,'keyring_sha256':hashlib.sha256(Path('/usr/share/keyrings/debian-archive-keyring.gpg').read_bytes()).hexdigest(),'signed_metadata_required':True,'snapshot_valid_until_disabled':True,'version_output':run([str(binary),'-version'])}
Path('/opt/rang/imaging-packages.json').write_text(json.dumps(receipt,indent=2)+'\n')
# Do not delete source artifacts or parent-layer caches. This tiny child keeps
# the verified packages and exact download plan for provenance.
PY

RUN python -m pip check
WORKDIR /workspace
ENTRYPOINT ["stimela"]
