import os
import geopandas as gpd
import streamlit as st

DEHRADUN_LAT = 30.3165
DEHRADUN_LON = 78.0469

# Path to the pre-downloaded GeoJSON (committed to the repo under data/)
DATA_DIR       = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
BUILDINGS_FILE = os.path.join(DATA_DIR, 'buildings.geojson')

# Module-level cache — survives Streamlit reruns within the same process
_CACHE: dict = {}


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_buildings(bounds=None):
    cache_key = str(bounds)
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    # ── Fast path: load from pre-downloaded GeoJSON ───────────────────────────
    if os.path.exists(BUILDINGS_FILE):
        try:
            bdf = gpd.read_file(BUILDINGS_FILE)

            # If bounds are specified, clip to that area
            if bounds:
                bdf = bdf.cx[
                    bounds["min_lon"]:bounds["max_lon"],
                    bounds["min_lat"]:bounds["max_lat"],
                ].copy()

            if 'building_id' not in bdf.columns:
                bdf['building_id'] = range(len(bdf))

            bdf = bdf.reset_index(drop=True)
            _CACHE[cache_key] = (bdf, "success")
            return bdf, "success"

        except Exception:
            pass  # fall through to OSM fetch if file is corrupt

    # ── Slow fallback: fetch live from OpenStreetMap ──────────────────────────
    try:
        import osmnx as ox

        if bounds:
            n = bounds["max_lat"]
            s = bounds["min_lat"]
            e = bounds["max_lon"]
            w = bounds["min_lon"]
        else:
            d = 0.01
            n = DEHRADUN_LAT + d
            s = DEHRADUN_LAT - d
            e = DEHRADUN_LON + d
            w = DEHRADUN_LON - d

        bdf = ox.features_from_bbox(bbox=(n, s, e, w), tags={"building": True})
        bdf = bdf[bdf.geometry.type.isin(['Polygon', 'MultiPolygon'])].copy()
        bdf = bdf.to_crs(epsg=4326)
        bdf["geometry"] = bdf["geometry"].simplify(0.000025, preserve_topology=True)

        keep = [c for c in ['geometry', 'building', 'name', 'addr:street'] if c in bdf.columns]
        bdf  = bdf[keep]
        bdf['building_id'] = range(len(bdf))
        bdf = bdf.reset_index(drop=True)

        _CACHE[cache_key] = (bdf, "success")
        return bdf, "success"

    except Exception as e:
        return None, str(e)
