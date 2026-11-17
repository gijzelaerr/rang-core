"""Print `<sif name> docker://<repo>@<digest>` for every image in versions.json
(research/e3-caracal.md 10.14). Stimela 1.8.3 names a cab's SIF
`<base with / as _>_<tag>.sif` in the image dir (stimela/recipe.py)."""

import json
import sys

for im in json.load(open(sys.argv[1]))["images"]:
    repo, tag = im["image"].rsplit(":", 1)
    base = repo.split("/", 1)[1]
    print(f"{base.replace('/', '_')}_{tag}.sif docker://{repo}@{im['digest']}")
