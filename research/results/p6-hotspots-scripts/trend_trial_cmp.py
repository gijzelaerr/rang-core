import json, sys
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
keys = sorted(set(a) | set(b))
print({k: a.get(k) == b.get(k) for k in keys})
ca, cb = a["configuration"], b["configuration"]
print("config differs in", [k for k in ca if ca[k] != cb.get(k)])
ra, rb = ca["runtime_receipts"], cb["runtime_receipts"]
print("receipts differ in", [k.split("/")[-1] for k in ra if ra[k] != rb.get(k)])
