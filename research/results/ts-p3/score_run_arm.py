import json, sys, importlib.util
import numpy as np
from pathlib import Path
def load(n):
    s=importlib.util.spec_from_file_location(n, f"C:/Users/gijsm/Worktrees/rang/ts-p3/examples/{n}.py"); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
m2=load("ts_p2_measure"); m1=load("ts_p1_measure")
r=m2.score("tsp2-dev.ms","tsp2-dev.truth.json","lc-arun")
t=json.load(open("tsp2-dev.truth.json")); lc=json.load(open("lc-arun/lightcurve.json"))
tt=dict(t); tt["flux_jy"]=t["amplitude_jy"]
r["A3_T3d"]=m1.recovery(tt, np.array(lc["flux_jy"]), np.array(lc["sigma_meas_jy"]), t["sigma_snap_jy"])
sig=np.array(t["sigma_snap_interval_jy"])
r["sigma_meas_over_sigma_snap"]=float(np.median(np.array(lc["sigma_meas_jy"])/sig))
r["verdict"]={"A1":r["D1"]["pass"],"A2":r["D4"]["pass"],"A3":r["A3_T3d"]["pass"]}
json.dump(r,open("score-arun.json","w"),indent=1)
print(r["verdict"], r["D3"]["per_source"], r["D3b"]["per_source"], r["sigma_meas_over_sigma_snap"])
