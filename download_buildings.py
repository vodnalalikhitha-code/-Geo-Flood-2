"""
Run this script ONCE locally on your machine:
    python download_buildings.py

It will download all OSM building footprints for Dehradun and save them
as 'data/buildings.geojson' in your project root.

Commit that file to GitHub — the app will then load it instantly at runtime
without ever calling OpenStreetMap again.

Requirements: osmnx, geopandas (already in your requirements.txt)
"""

import os
import geopandas as gpd
import osmnx as ox

DEHRADUN_LAT = 30.3165
DEHRADUN_LON = 78.0469

# Bounding box — same as used in the app
D = 0.01
N = DEHRADUN_LAT + D
S = DEHRADUN_LAT - D
E = DEHRADUN_LON + D
W = DEHRADUN_LON - D

# Also fetch the TIF bounds area so post-flood mode is covered too
# (slightly larger bbox to cover both modes)
N2 = DEHRADUN_LAT + 0.05
S2 = DEHRADUN_LAT - 0.05
E2 = DEHRADUN_LON + 0.05
W2 = DEHRADUN_LON - 0.05

OUTPUT_DIR  = os.path.join(os.path.dirname(__file__), "data")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "buildings.geojson")

os.makedirs(OUTPUT_DIR, exist_ok=True)

print("Downloading OSM buildings for Dehradun (this takes 1-3 min)...")
bdf = ox.features_from_bbox(bbox=(N2, S2, E2, W2), tags={"building": True})

print(f"  Raw features fetched: {len(bdf)}")
bdf = bdf[bdf.geometry.type.isin(['Polygon', 'MultiPolygon'])].copy()
bdf = bdf.to_crs(epsg=4326)

# Simplify geometry — reduces file size and speeds up spatial joins
bdf["geometry"] = bdf["geometry"].simplify(0.000025, preserve_topology=True)

# Keep only essential columns
keep = [c for c in ['geometry', 'building', 'name', 'addr:street'] if c in bdf.columns]
bdf  = bdf[keep]
bdf['building_id'] = range(len(bdf))

# Reset index so GeoJSON serialises cleanly
bdf = bdf.reset_index(drop=True)

bdf.to_file(OUTPUT_FILE, driver="GeoJSON")
print(f"  Saved {len(bdf)} buildings → {OUTPUT_FILE}")
print("\nDone! Now commit 'data/buildings.geojson' to your GitHub repo.")
