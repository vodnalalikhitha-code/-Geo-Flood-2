import os
import geopandas as gpd
import streamlit as st

DATA_DIR       = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
BUILDINGS_FILE = os.path.join(DATA_DIR, 'buildings.geojson')

_CACHE: dict = {}

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_buildings(bounds=None):
    cache_key = str(bounds)
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    try:
        bdf = gpd.read_file(BUILDINGS_FILE)
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
    except Exception as e:
        return None, str(e)
