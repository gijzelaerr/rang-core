import json, sys
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
out = []
def walk(x, y, path):
    if len(out) > 40: return
    if type(x) != type(y):
        out.append((path, repr(x)[:80], repr(y)[:80])); return
    if isinstance(x, dict):
        for k in sorted(set(x) | set(y)):
            if k not in x or k not in y: out.append((path + "/" + k, "missing" if k not in x else "", "missing" if k not in y else ""))
            else: walk(x[k], y[k], path + "/" + k)
    elif isinstance(x, list):
        if len(x) != len(y): out.append((path, f"len {len(x)}", f"len {len(y)}")); return
        for i, (u, v) in enumerate(zip(x, y)): walk(u, v, f"{path}[{i}]")
    elif x != y:
        out.append((path, repr(x)[:80], repr(y)[:80]))
walk(a, b, "")
for row in out: print(*row, sep="\t")
print("differences:", len(out))
