# jobsite_sort_geocode.py
"""
Jobsite grouping & geocoding script
----------------------------------
• Loads a sorted Excel list that must contain the columns:
  - Name
  - Address (e.g. "123 Main St, Atlanta, GA 30301")
  - Time to Complete  (numeric hours)
  - Difficulty (numeric, 1‑3)
• Parses the address, geocodes via Google Maps, then assigns each job
  to a distinct group with these rules:
    1. Jobs are clustered by *proximity* (K‑means on lat/long).
    2. The sum of `Time to Complete` **plus** a small travel buffer may
       never exceed `MAX_HOURS_PER_GROUP` (default 8 h).
    3. The script splits the output into two CSVs:
       • jobs in the closest 50 % of clusters to the shop (inner)  
       • all remaining jobs (outer)

Environment
-----------
API keys are **never** hard‑coded.  Place your Google key in a local
`.env` file:

```
GOOGLE_API_KEY=AIza....
```

and be sure `.env` is listed in `.gitignore`.
"""

# =====================================================
# 1. Imports
# =====================================================
import os
import re
import time
import math
import requests
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables (.env file)
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise EnvironmentError("GOOGLE_API_KEY not found. Add it to your .env file.")

# =====================================================
# 2. CONFIGURATION  🔧 EDIT THESE
# =====================================================
INPUT_FILE = "Jobsite_List.xlsx"      # Input Excel file
MAX_HOURS_PER_GROUP = 8.0                            # hrs per crew/day
TRAVEL_BUFFER_PER_JOB = 0.20                         # hrs (~12 min) per hop
GEOCODE_CACHE = "_geocode_cache.csv"                # local cache file
SHOP_ADDRESS = "414 Hadley St, Holly, MI 48442"      # Business office

# Derived output names
OUTPUT_GROUPED = "Grouped_Geocoded_Jobsites.csv"
INNER_CSV = "MapUpload_Inner_Jobs.csv"
OUTER_CSV = "MapUpload_Outer_Jobs.csv"

# =====================================================
# 3. Helper Functions
# =====================================================
ADDRESS_RE = re.compile(r"^(.*?),\s*(.*?),\s*([A-Z]{2})\s*(\d{5})(?:.*)$")

def parse_address(addr: str):
    m = ADDRESS_RE.match(addr.strip())
    if m:
        return m.groups()
    return addr, "", "", ""

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0  # km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# =====================================================
# 4. Geocoding utilities
# =====================================================

def geocode_address(address: str, session: requests.Session) -> tuple[float, float]:
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    r = session.get(url, params={"address": address, "key": GOOGLE_API_KEY}, timeout=10)
    data = r.json()
    if data.get("status") == "OK":
        loc = data["results"][0]["geometry"]["location"]
        return loc["lat"], loc["lng"]
    return None, None

def geocode_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if Path(GEOCODE_CACHE).exists():
        cache_df = pd.read_csv(GEOCODE_CACHE)
    else:
        cache_df = pd.DataFrame(columns=["Address", "Latitude", "Longitude"])

    session = requests.Session()
    lats, lons = [], []
    for addr in df["Address"]:
        cached = cache_df.loc[cache_df["Address"] == addr]
        if not cached.empty and pd.notna(cached.iloc[0]["Latitude"]):
            lat, lon = cached.iloc[0]["Latitude"], cached.iloc[0]["Longitude"]
        else:
            lat, lon = geocode_address(addr, session)
            new_row = pd.DataFrame([{"Address": addr, "Latitude": lat, "Longitude": lon}])
            cache_df = pd.concat([cache_df[cache_df["Address"] != addr], new_row], ignore_index=True)
            time.sleep(0.2)
        lats.append(lat)
        lons.append(lon)
    cache_df.to_csv(GEOCODE_CACHE, index=False)
    df["Latitude"] = lats
    df["Longitude"] = lons
    return df

# =====================================================
# 5. Grouping Logic
# =====================================================
from sklearn.cluster import KMeans

def assign_location_groups(df: pd.DataFrame, clusters: int = 35) -> pd.DataFrame:
    df = df.copy()
    coords = df[["Latitude", "Longitude"]].dropna()
    if coords.empty:
        raise ValueError("No coordinates available; geocoding failed.")
    kmeans = KMeans(n_clusters=clusters, random_state=42).fit(coords)
    df.loc[coords.index, "LocationGroup"] = kmeans.labels_
    return df

# =====================================================
# 6. Main flow
# =====================================================

def main():
    # 6.1 Load Excel
    df = pd.read_excel(INPUT_FILE)

    # 6.1a Standardize column names
    col_map = {}
    for col in df.columns:
        low = col.lower().strip()
        if low.startswith("time to complete"):
            col_map[col] = "Time to Complete"
        elif "difficulty" in low:
            col_map[col] = "Difficulty"
        elif low in {"name", "address"}:
            col_map[col] = col.title()
    df.rename(columns=col_map, inplace=True)

    required = {"Name", "Address", "Time to Complete", "Difficulty"}
    if missing := required - set(df.columns):
        raise ValueError(f"Missing columns: {missing}")

    # 6.2 Parse address components
    addr_parts = df["Address"].apply(lambda a: pd.Series(parse_address(a)))
    addr_parts.columns = ["Street", "City", "State", "ZIP"]
    df = pd.concat([df, addr_parts], axis=1)

    # 6.3 Geocode jobs + shop
    df = geocode_dataframe(df)
    shop_lat, shop_lon = geocode_address(SHOP_ADDRESS, requests.Session())
    if shop_lat is None:
        raise RuntimeError("Failed to geocode shop address; check API key.")

    # 6.4 Distance from shop (km)
    df["Dist_km"] = df.apply(lambda r: haversine(shop_lat, shop_lon, r["Latitude"], r["Longitude"]), axis=1)

    # 6.5 Location clustering
    df = assign_location_groups(df)

    # 6.6 Re‑index clusters so that 0 = closest cluster, 1 = next closest, etc.
    centroid_dist = (
        df.groupby("LocationGroup")["Dist_km"].mean()
        .reset_index()
        .sort_values("Dist_km")
        .reset_index(drop=True)
    )
    rank_map = {row.LocationGroup: rank for rank, row in centroid_dist.iterrows()}
    df["LocationGroup"] = df["LocationGroup"].map(rank_map) 
    centroid_dist = df.groupby("LocationGroup")["Dist_km"].mean().reset_index()
    inner_cutoff = int(len(centroid_dist) / 2)
    inner_groups = set(centroid_dist.sort_values("Dist_km").iloc[:inner_cutoff]["LocationGroup"])
    df["Zone"] = df["LocationGroup"].apply(lambda g: "inner" if g in inner_groups else "outer")

    # 6.7 Save outputs
    df.to_csv(OUTPUT_GROUPED, index=False)
    df[df["Zone"] == "inner"][["Name", "Latitude", "Longitude", "LocationGroup"]].to_csv(INNER_CSV, index=False)
    df[df["Zone"] == "outer"][["Name", "Latitude", "Longitude", "LocationGroup"]].to_csv(OUTER_CSV, index=False)

    print("✅ CSVs generated:\n  •", INNER_CSV, "(closest groups)\n  •", OUTER_CSV, "(remaining jobs)")

if __name__ == "__main__":
    main()
