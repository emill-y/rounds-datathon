"""NEWS2 (Royal College of Physicians, 2017) scoring, used as the clinical baseline.
Missing vitals (NaN) score 0, which is how a paper chart effectively treats an unmeasured vital."""
import numpy as np, pandas as pd

def _band(x, cuts):
    if pd.isna(x): return 0
    for hi, pts in cuts:
        if x <= hi: return pts
    return cuts[-1][1]

def rr(x):   return _band(x, [(8,3),(11,1),(20,0),(24,2),(1e9,3)])
def spo2_1(x): return _band(x, [(91,3),(93,2),(95,1),(1e9,0)])
def spo2_2(x, on_o2):
    if pd.isna(x): return 0
    if x <= 83: return 3
    if x <= 85: return 2
    if x <= 87: return 1
    if x <= 92 or not on_o2: return 0
    return 1 if x <= 94 else 2 if x <= 96 else 3
def sbp(x):  return _band(x, [(90,3),(100,2),(110,1),(219,0),(1e9,3)])
def hr(x):   return _band(x, [(40,3),(50,1),(90,0),(110,1),(130,2),(1e9,3)])
def temp(x): return _band(x, [(35.0,3),(36.0,1),(38.0,0),(39.0,1),(1e9,2)])
def cons(x):
    if pd.isna(x): return 0
    return 0 if x == 'A' else 3

def parts(r):
    s = spo2_2(r.Oxygen_Saturation, r.On_Oxygen) if r.O2_Scale == 2 else spo2_1(r.Oxygen_Saturation)
    return [rr(r.Respiratory_Rate), s, 2*int(r.On_Oxygen), sbp(r.Systolic_BP), hr(r.Heart_Rate),
            temp(r.Temperature), cons(r.Consciousness)]

def risk_from_parts(p):
    total = sum(p)
    if total >= 7: return 'High'
    if total >= 5 or max(p) == 3: return 'Medium'
    if total >= 1: return 'Low'
    return 'Normal'

def news2_risk(df):
    return df.apply(lambda r: risk_from_parts(parts(r)), axis=1)

def news2_total(df):
    return df.apply(lambda r: sum(parts(r)), axis=1)
