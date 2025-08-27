#!/usr/bin/env python3
"""
Geography-only jobsite clustering with:
- Hard cap of 16 jobs per group (rebalance if needed)
- Groups renumbered by proximity to SHOP_ADDRESS (Group 0 = closest)
- Tkinter-based UI (or console fallback) to pick number of clusters K
- Google Maps Geocoding + cache
- Outputs:
    Jobs_Inner.csv  (closest half of groups)
    Jobs_Outer.csv  (furthest half of groups)
    Grouped_Geocoded_Jobsites.csv
    Grouped_Jobs.kml
"""

import os, sys, time, math, argparse
from pathlib import Path
from typing import Tuple
import pandas as pd, numpy as np
from sklearn.cluster import KMeans

try:
    from dotenv import load_dotenv; load_dotenv()
except Exception:
    pass

INPUT_FILE = os.getenv("INPUT_FILE", "Jobsite_List.xlsx")
OUTPUT_INNER_CSV = "Jobs_Inner(forTesting).csv"
OUTPUT_OUTER_CSV = "Jobs_Outer(forTesting).csv"
OUTPUT_GROUPED_CSV = "Grouped_Geocoded_Jobsites.csv"
OUTPUT_KML = "Grouped_Jobs.kml"
GEOCODE_CACHE_CSV = os.getenv("GEOCODE_CACHE_CSV", "geocode_cache.csv")

DEFAULT_K = int(os.getenv("K_CLUSTERS", "35"))
MAX_PER_GROUP = int(os.getenv("MAX_PER_GROUP", "16"))
RAND = 42
GEOCODE_SLEEP_S = float(os.getenv("GEOCODE_SLEEP_S", "0.2"))
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
SHOP_ADDRESS = os.getenv("SHOP_ADDRESS", "414 Hadley street holly michigan 48442").strip()

COL_NAME = "Name"
COL_ADDRESS = "Address"

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2*math.atan2(math.sqrt(a), math.sqrt(1-a))

# ---------------- Geocoding ----------------

def _geocode_google(address: str):
    import requests
    if not GOOGLE_API_KEY: return None, None
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": GOOGLE_API_KEY}
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if data.get("results"):
                    loc = data["results"][0]["geometry"]["location"]
                    return float(loc["lat"]), float(loc["lng"])
                if data.get("status") == "ZERO_RESULTS":
                    return None, None
        except Exception: pass
        time.sleep(0.5*(attempt+1))
    return None, None

def load_geocode_cache():
    if Path(GEOCODE_CACHE_CSV).exists():
        try:
            g = pd.read_csv(GEOCODE_CACHE_CSV)
            if {"Address","Latitude","Longitude"}.issubset(g.columns):
                return g
        except: pass
    return pd.DataFrame(columns=["Address","Latitude","Longitude"])

def save_geocode_cache(df):
    try:
        df.drop_duplicates(subset=["Address"], keep="last").to_csv(GEOCODE_CACHE_CSV, index=False)
    except PermissionError:
        import tempfile
        fallback = Path(tempfile.gettempdir())/f"geocode_cache_{int(time.time())}.csv"
        df.drop_duplicates(subset=["Address"], keep="last").to_csv(fallback, index=False)
        print("Cache locked; wrote fallback:", fallback)

def geocode_address(address, cache):
    if not isinstance(address,str) or not address.strip(): return None,None,cache
    hit = cache[cache["Address"]==address]
    if not hit.empty:
        return float(hit.iloc[0]["Latitude"]), float(hit.iloc[0]["Longitude"]), cache
    lat,lon=_geocode_google(address)
    if lat is not None and lon is not None:
        cache=pd.concat([cache,pd.DataFrame({"Address":[address],"Latitude":[lat],"Longitude":[lon]})],ignore_index=True)
        time.sleep(GEOCODE_SLEEP_S)
    return lat,lon,cache

# ---------------- KML ----------------

def export_kml(df: pd.DataFrame, path: str):
    groups=sorted(df["LocationGroup"].dropna().unique())
    kml=['<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2">\n<Document>\n']
    for g in groups:
        kml.append(f'  <Folder><name>Group {g}</name>\n')
        for _,row in df[df["LocationGroup"]==g].iterrows():
            name=str(row.get(COL_NAME,"")).replace("&","&amp;")
            kml.append(f'    <Placemark><name>{name}</name><Point><coordinates>{row["Longitude"]},{row["Latitude"]},0</coordinates></Point></Placemark>\n')
        kml.append("  </Folder>\n")
    kml.append("</Document></kml>\n")
    Path(path).write_text("".join(kml),encoding="utf-8")

# ---------------- Rebalancer ----------------

def _rebalance_capacity_geo(df,max_per_group=16):
    def _centroids(frame): return frame.groupby("LocationGroup")[["Latitude","Longitude"]].mean()
    for _ in range(50):
        counts=df["LocationGroup"].value_counts().to_dict()
        over=[g for g,c in counts.items() if c>max_per_group]
        if not over: break
        cents=_centroids(df)
        under=[g for g,c in counts.items() if c<max_per_group]
        if not under: break
        for g in over:
            g_idx=df.index[df["LocationGroup"]==g]
            latc,lonc=cents.loc[g]
            d2=(df.loc[g_idx,"Latitude"]-latc)**2+(df.loc[g_idx,"Longitude"]-lonc)**2
            for idx in d2.sort_values(ascending=False).index:
                lat,lon=df.at[idx,"Latitude"],df.at[idx,"Longitude"]
                h=min(under,key=lambda u:(lat-cents.loc[u,"Latitude"])**2+(lon-cents.loc[u,"Longitude"])**2)
                df.at[idx,"LocationGroup"]=h
                counts[g]-=1;counts[h]=counts.get(h,0)+1
                if counts[g]<=max_per_group: break
    return df

# ---------------- Proximity renumbering ----------------

def _relabel_by_shop(df,shop_lat,shop_lon):
    if shop_lat is None: return df
    cents=df.groupby("LocationGroup")[["Latitude","Longitude"]].mean().reset_index()
    cents["Dist"]=cents.apply(lambda r:haversine(r["Latitude"],r["Longitude"],shop_lat,shop_lon),axis=1)
    cents=cents.sort_values("Dist").reset_index(drop=True)
    mapping={row["LocationGroup"]:i for i,row in cents.iterrows()}
    df["LocationGroup"]=df["LocationGroup"].map(mapping)
    return df

# ---------------- K Picker UI ----------------


def _pick_k_interactive(default_k:int, low:int=1, high:int=100, after_first:bool=False, job_count:int=None):
    """
    Entry-only dialog (OK/Cancel) to pick K, with dynamic bounds based on job_count.
    Returns an int K, or None if user cancels.
    Falls back to console (blank = cancel).
    """
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
        root = tk.Tk()
        root.title("Choose number of groups (K)")
        root.geometry("560x220")
        root.resizable(False, False)

        var = tk.StringVar(value=str(default_k))

        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)

        hi = high
        lo = low
        jc = job_count if job_count is not None else high
        if after_first:
            ttk.Label(frame, text=f"You chose {default_k} groups.").pack(anchor="w")
            ttk.Label(frame, text=f"You have {jc} jobs. How many groups would you like ({lo}-{hi})?").pack(anchor="w", pady=(0,8))
        else:
            ttk.Label(frame, text=f"You have {jc} jobs. How many groups would you like ({lo}-{hi})?").pack(anchor="w", pady=(0,8))

        row = ttk.Frame(frame); row.pack(pady=6)
        ttk.Label(row, text="K: ").pack(side="left")
        entry = ttk.Entry(row, width=10, textvariable=var, justify="center")
        entry.pack(side="left")
        entry.focus_set()

        chosen = {"k": None}

        def ok():
            try:
                raw = var.get().strip()
                k = int(raw)
                if not (lo <= k <= hi):
                    messagebox.showerror("Invalid K", f"K must be between {lo} and {hi}.")
                    return
                chosen["k"] = k
                root.destroy()
            except Exception:
                messagebox.showerror("Invalid K", "Please enter a whole number.")
        def cancel():
            root.destroy()

        btns = ttk.Frame(frame)
        btns.pack(pady=12, fill="x")
        ttk.Button(btns, text="OK", command=ok).pack(side="left")
        ttk.Button(btns, text="Cancel", command=cancel).pack(side="left", padx=8)

        root.mainloop()
        return chosen["k"]
    except Exception:
        # Console fallback
        try:
            jc = job_count if job_count is not None else high
            if after_first:
                print(f"You chose {default_k} groups. You have {jc} jobs. Enter a different K ({low}..{high}) or press Enter to cancel:")
            else:
                print(f"You have {jc} jobs. Enter K ({low}..{high}) or press Enter to cancel. Default {default_k}:")
            raw = input("> ").strip()
            if not raw:
                return None
            k = int(raw)
            if k < low: k = low
            if k > high: k = high
            return k
        except Exception:
            return None
            k = int(raw)
            if k < low: k = low
            if k > high: k = high
            return k
        except Exception:
            return None
            k = int(raw)
            if k < low: k = low
            if k > high: k = high
            return k
        except Exception:
            return None



def run_for_k(k:int, input_path:str):
    df = pd.read_excel(input_path)

    # Normalize core columns
    col_map = {}
    for c in df.columns:
        lc = c.lower()
        if lc.startswith("name"): col_map[c] = COL_NAME
        elif lc.startswith("address"): col_map[c] = COL_ADDRESS
        elif lc == "latitude": col_map[c] = "Latitude"
        elif lc == "longitude": col_map[c] = "Longitude"
    if col_map: df.rename(columns=col_map, inplace=True)

    cache = load_geocode_cache()
    lats, lons = [], []
    for addr in df[COL_ADDRESS].astype(str).fillna(""):
        lat, lon, cache = geocode_address(addr, cache)
        lats.append(lat); lons.append(lon)
    df["Latitude"] = lats; df["Longitude"] = lons
    save_geocode_cache(cache)

    df = df.dropna(subset=["Latitude","Longitude"]).reset_index(drop=True)
    if df.empty:
        print("No jobs with coordinates; skipping.")
        return

    # Clamp K to number of rows (n_jobs)
    n_jobs = len(df)
    k = int(max(1, min(k, n_jobs)))

    km = KMeans(n_clusters=k, random_state=RAND, n_init=10)
    df["LocationGroup"] = km.fit_predict(df[["Latitude","Longitude"]].to_numpy())
    df = _rebalance_capacity_geo(df, MAX_PER_GROUP)

    shop_lat, shop_lon, cache = geocode_address(SHOP_ADDRESS, cache)
    df = _relabel_by_shop(df, shop_lat, shop_lon)

    k_actual = df["LocationGroup"].nunique()
    cutoff = (k_actual + 1) // 2
    df_inner = df[df["LocationGroup"].isin(range(cutoff))]
    df_outer = df[df["LocationGroup"].isin(range(cutoff, k_actual))]

    df_inner.to_csv(OUTPUT_INNER_CSV, index=False)
    df_outer.to_csv(OUTPUT_OUTER_CSV, index=False)
    df.to_csv(OUTPUT_GROUPED_CSV, index=False)
    export_kml(df, OUTPUT_KML)
    print(f"[K={k}] Wrote {OUTPUT_INNER_CSV}, {OUTPUT_OUTER_CSV}, {OUTPUT_GROUPED_CSV}, {OUTPUT_KML}")

    km = KMeans(n_clusters=k, random_state=RAND, n_init=10)
    df["LocationGroup"] = km.fit_predict(df[["Latitude","Longitude"]].to_numpy())
    df = _rebalance_capacity_geo(df, MAX_PER_GROUP)

    shop_lat, shop_lon, cache = geocode_address(SHOP_ADDRESS, cache)
    df = _relabel_by_shop(df, shop_lat, shop_lon)

    k_actual = df["LocationGroup"].nunique()
    cutoff = (k_actual + 1) // 2
    df_inner = df[df["LocationGroup"].isin(range(cutoff))]
    df_outer = df[df["LocationGroup"].isin(range(cutoff, k_actual))]

    df_inner.to_csv(OUTPUT_INNER_CSV, index=False)
    df_outer.to_csv(OUTPUT_OUTER_CSV, index=False)
    df.to_csv(OUTPUT_GROUPED_CSV, index=False)
    export_kml(df, OUTPUT_KML)
    print(f"[K={k}] Wrote {OUTPUT_INNER_CSV}, {OUTPUT_OUTER_CSV}, {OUTPUT_GROUPED_CSV}, {OUTPUT_KML}")

# ---------------- Main ----------------

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=None, help="Number of clusters (leave blank for UI)")
    parser.add_argument("--input", type=str, default=INPUT_FILE)
    args = parser.parse_args(argv)

    if args.k is not None:
        # Single run with provided K
        run_for_k(int(max(2, args.k)), args.input)
        return 0

    # UI loop: ask for K, run, then ask again until Cancel
    
    # Determine job count from input file to set bounds
    try:
        _df0 = pd.read_excel(args.input)
        job_count = len(_df0)
        if job_count < 1:
            job_count = 1
    except Exception:
        job_count = 200  # fallback
    last_k = min(DEFAULT_K, job_count)
    ran_once = False
    while True:
        k = _pick_k_interactive(last_k, 1, job_count, after_first=ran_once, job_count=job_count)
        if k is None:
            print("Cancelled. Exiting.")
            break
        k = int(max(2, k))
        run_for_k(k, args.input)
        last_k = k
        ran_once = True

    return 0

if __name__=="__main__":
    sys.exit(main())