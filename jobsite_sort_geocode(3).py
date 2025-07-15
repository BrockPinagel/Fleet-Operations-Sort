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
    1. Groups are created primarily by *location* (ZIP‑prefix buckets).
    2. The sum of `Time to Complete` **plus** a small travel buffer may
       never exceed `MAX_HOURS_PER_GROUP` (default 8 h).
    3. Within each ZIP bucket jobs are packed by longest‑time & highest
       difficulty first to minimise over‑runs.

Change the CONFIG section to match your environment and provide your
own Google Maps API key.
"""

# =====================================================
# 1. Imports
# =====================================================
import re
import time
import math
import requests
import sklearn 
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

import os
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# =====================================================
# 2. CONFIGURATION  🔧 EDIT THESE
# =====================================================
INPUT_FILE = "Updated_Sorted_Jobsite_List.xlsx"          # Input Excel file
OUTPUT_FILE = "Grouped_Geocoded_Jobsites.csv"    # Final CSV output
GOOGLE_API_KEY = "API_KEY"             # <-- paste your key
MAX_HOURS_PER_GROUP = 8.0                         # hrs per crew/day
TRAVEL_BUFFER_PER_JOB = 0.20                      # hrs (~12 min) per hop
GEOCODE_CACHE = "_geocode_cache.csv"             # local cache file

# =====================================================
# 3. Helper Functions
# =====================================================

ADDRESS_RE = re.compile(r"^(.*?),\s*(.*?),\s*([A-Z]{2})\s*(\d{5})(?:.*)$")


def parse_address(addr: str):
    """Return (street, city, state, zip) or fallbacks if pattern fails."""
    m = ADDRESS_RE.match(addr.strip())
    if m:
        return m.group(1), m.group(2), m.group(3), m.group(4)
    return addr, "", "", ""


def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0  # km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))  # km


# =====================================================
# 4. Geocoding (with local CSV cache to save API calls)
# =====================================================

def geocode_address(full_address: str, session: requests.Session) -> tuple[float, float]:
    """Return (lat, lon) using Google Geocoding API."""
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    r = session.get(url, params={"address": full_address, "key": GOOGLE_API_KEY}, timeout=10)
    data = r.json()
    if data.get("status") == "OK":
        loc = data["results"][0]["geometry"]["location"]
        return loc["lat"], loc["lng"]
    return None, None


def geocode_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Add Latitude / Longitude columns, using cache where possible."""
    # Load or create cache dataframe
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
            # append/update cache
            new_row = pd.DataFrame([{"Address": addr, "Latitude": lat, "Longitude": lon}])
            cache_df = pd.concat([cache_df[cache_df["Address"] != addr], new_row], ignore_index=True)
            time.sleep(0.2)  # respectful delay
        lats.append(lat)
        lons.append(lon)
    # Save cache
    cache_df.to_csv(GEOCODE_CACHE, index=False)

    df["Latitude"] = lats
    df["Longitude"] = lons
    return df


# =====================================================
# 5. Grouping Logic
# =====================================================

def assign_groups(df: pd.DataFrame) -> pd.DataFrame:
    """Assign jobs to 30–40 groups, primarily by proximity and time limits.

    Uses k-means clustering on coordinates to form 30 location groups,
    then packs jobs in each group so that total job time + buffer ≤ 8 hours.
    """
    from sklearn.cluster import KMeans

    df = df.copy()
    coords = df[["Latitude", "Longitude"]].dropna()
    kmeans = KMeans(n_clusters=35, random_state=42).fit(coords)
    df.loc[coords.index, "LocationGroup"] = kmeans.labels_

    group_id = 1
    group_labels = [None] * len(df)

    for loc_group, group_df in df.groupby("LocationGroup"):
        # Sort by longest & hardest jobs first
        sorted_jobs = group_df.sort_values(by=["Time to Complete", "Difficulty"], ascending=[False, False])
        current_sum = 0.0

        for idx in sorted_jobs.index:
            job_time = df.at[idx, "Time to Complete"] or 0
            buffer = TRAVEL_BUFFER_PER_JOB if current_sum > 0 else 0
            if current_sum + job_time + buffer > MAX_HOURS_PER_GROUP:
                group_id += 1
                current_sum = 0.0
                buffer = 0
            group_labels[idx] = group_id
            current_sum += job_time + buffer

        group_id += 1  # ensure next location gets new range

    df["Group"] = group_labels
    return df
    return df


# =====================================================
# 6. Main flow
# =====================================================

def main():
    # 6.1 Load Excel
    df = pd.read_excel(INPUT_FILE)

    # --- 6.1.a Resolve column names flexibly -----------------------------
    # Allow variations such as "Difficulty (1 = easy | 3 = difficult)"
    # and "Time to Complete (hrs)".
    col_map = {}
    for col in df.columns:
        low = col.strip().lower()
        if low.startswith("time to complete"):
            col_map[col] = "Time to Complete"
        elif "difficulty" in low:
            col_map[col] = "Difficulty"
        elif low in {"name", "address"}:
            col_map[col] = col.strip().title()
    df.rename(columns=col_map, inplace=True)

    required_cols = {"Name", "Address", "Time to Complete", "Difficulty"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(
            "Missing required columns in Excel. "
            "Make sure you have columns for Name, Address, Time to Complete, and Difficulty. "
            f"Currently missing: {missing}"
        )

    # 6.2 Parse address parts
    parsed = df["Address"].apply(lambda a: pd.Series(parse_address(a)))
    parsed.columns = ["Street", "City", "State", "ZIP"]
    df = pd.concat([df, parsed], axis=1)

    # 6.3 Geocode
    df = geocode_dataframe(df)

    # 6.4 Assign groups
    df = assign_groups(df)

    # 6.5 Sort for readability
    df = df.sort_values(by=["Group", "Time to Complete", "Difficulty", "Name"])

    # 6.6 Export
    df.to_csv(OUTPUT_FILE, index=False)
    print(
        f"✅ All done. Output saved to {OUTPUT_FILE}"
        f"Total groups created: {df['Group'].nunique()}"
    )

# --- EXTRA: Export per‑map CSV for Google My Maps -------------
    MYMAPS_FILE = "MapUpload_Jobsites.csv"
    df[['Name', 'Latitude', 'Longitude', 'LocationGroup']].to_csv(MYMAPS_FILE, index=False)
    print(f"▶ My Maps upload file saved to {MYMAPS_FILE}")


if __name__ == "__main__":
    main()
