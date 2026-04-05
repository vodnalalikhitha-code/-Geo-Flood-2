import geopandas as gpd
import streamlit as st

DEHRADUN_LAT = 30.3165
DEHRADUN_LON = 78.0469


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_buildings(bounds=None):
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
        keep = [c for c in ['geometry', 'building', 'name', 'addr:street'] if c in bdf.columns]
        bdf  = bdf[keep]
        bdf['building_id'] = range(len(bdf))
        return bdf, "success"
    except Exception as e:
        return None, str(e)
