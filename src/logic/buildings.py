import geopandas as gpd
import streamlit as st

DEHRADUN_LAT = 30.3165
DEHRADUN_LON = 78.0469

# Module-level cache so buildings survive across Streamlit reruns in the same process
_BUILDINGS_CACHE: dict = {}


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_buildings(bounds=None):
    cache_key = str(bounds)
    if cache_key in _BUILDINGS_CACHE:
        return _BUILDINGS_CACHE[cache_key]

    try:
        import osmnx as ox

        # Use a slightly larger but fixed bbox so we can cache one canonical result
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

        # Fetch only building footprints — no extra tags to speed up network call
        bdf = ox.features_from_bbox(
            bbox=(n, s, e, w),
            tags={"building": True}
        )

        # Keep only polygon footprints
        bdf = bdf[bdf.geometry.type.isin(['Polygon', 'MultiPolygon'])].copy()
        bdf = bdf.to_crs(epsg=4326)

        # Simplify geometry slightly for faster spatial joins & map rendering
        bdf["geometry"] = bdf["geometry"].simplify(0.000025, preserve_topology=True)

        keep = [c for c in ['geometry', 'building', 'name', 'addr:street'] if c in bdf.columns]
        bdf  = bdf[keep]
        bdf['building_id'] = range(len(bdf))

        _BUILDINGS_CACHE[cache_key] = (bdf, "success")
        return bdf, "success"

    except Exception as e:
        return None, str(e)
