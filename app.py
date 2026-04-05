import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape, Point
import requests
from datetime import datetime, timedelta
import os

st.set_page_config(page_title="GeoFlood - Dehradun", page_icon="🌊", layout="wide")

DEHRADUN_LAT = 30.3165
DEHRADUN_LON = 78.0469
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
TIF_PATH = os.path.join(DATA_DIR, 'Dehradun_NDWI.tif')

RIVER_CORRIDORS = [
    {"name": "Rispana River", "points": [(78.0200,30.3800),(78.0350,30.3600),(78.0500,30.3400),(78.0600,30.3200),(78.0700,30.3000)]},
    {"name": "Bindal River",  "points": [(78.0800,30.3800),(78.0750,30.3600),(78.0700,30.3400),(78.0650,30.3200),(78.0600,30.3000)]},
    {"name": "Song River",    "points": [(78.1200,30.4000),(78.1000,30.3700),(78.0900,30.3400)]},
]

# ─── CACHED DATA FUNCTIONS ────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def get_rainfall():
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": DEHRADUN_LAT, "longitude": DEHRADUN_LON,
        "hourly": "precipitation", "daily": "precipitation_sum",
        "timezone": "Asia/Kolkata", "past_days": 7, "forecast_days": 3
    }
    try:
        r = requests.get(url, params=params, timeout=10).json()
        times = r["hourly"]["time"]
        precip = r["hourly"]["precipitation"]
        now = datetime.now()
        cur = now.strftime("%Y-%m-%dT%H:00")
        start = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:00")
        recent = [p or 0 for t, p in zip(times, precip) if start <= t <= cur]
        daily_df = pd.DataFrame({"date": r["daily"]["time"], "rainfall_mm": [x or 0 for x in r["daily"]["precipitation_sum"]]})
        return {"intensity": round(recent[-1] if recent else 0, 2),
                "total_24h": round(sum(recent), 2),
                "daily_df": daily_df,
                "updated": now.strftime("%Y-%m-%d %H:%M")}
    except:
        return {"intensity": 0, "total_24h": 0, "daily_df": pd.DataFrame(), "updated": "unavailable"}

def classify_rainfall(mm):
    if mm < 2.5:   return "Light Rain", "#00FF00"
    if mm < 7.5:   return "Moderate Rain", "#FFFF00"
    if mm < 35.5:  return "Heavy Rain", "#FFA500"
    if mm < 64.5:  return "Very Heavy Rain", "#FF4500"
    return "Extremely Heavy Rain", "#FF0000"

@st.cache_data(ttl=86400, show_spinner=False)
def load_tif():
    if not os.path.exists(TIF_PATH):
        return None, None, f"TIF not found at {TIF_PATH}"
    try:
        with rasterio.open(TIF_PATH) as src:
            data = src.read(1).astype(float)
            transform = src.transform
            crs = src.crs
            bounds = src.bounds
            nodata = src.nodata
        if nodata is not None:
            data = np.where(data == nodata, np.nan, data)
        mask = (data > 0.0).astype(np.uint8)
        polys = [shape(g) for g, v in shapes(mask, transform=transform) if v == 1]
        if not polys:
            return None, None, "No flood zones detected."
        flood_gdf = gpd.GeoDataFrame(geometry=polys, crs=crs).to_crs(epsg=4326)
        b = {"min_lon": bounds.left, "max_lon": bounds.right, "min_lat": bounds.bottom, "max_lat": bounds.top}
        return flood_gdf, b, "success"
    except Exception as e:
        return None, None, str(e)

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_buildings(bounds=None):
    try:
        import osmnx as ox
        if bounds:
            n, s, e, w = bounds["max_lat"], bounds["min_lat"], bounds["max_lon"], bounds["min_lon"]
        else:
            d = 0.01
            n, s = DEHRADUN_LAT+d, DEHRADUN_LAT-d
            e, w = DEHRADUN_LON+d, DEHRADUN_LON-d
        bdf = ox.features_from_bbox(bbox=(n,s,e,w), tags={"building": True})
        bdf = bdf[bdf.geometry.type.isin(['Polygon','MultiPolygon'])].copy()
        bdf = bdf.to_crs(epsg=4326)
        keep = [c for c in ['geometry','building','name','addr:street'] if c in bdf.columns]
        bdf = bdf[keep]
        bdf['building_id'] = range(len(bdf))
        return bdf, "success"
    except Exception as e:
        return None, str(e)

# ─── MAP BUILDER ──────────────────────────────────────────────────────────────

def build_map(buildings_gdf, flood_gdf, flood_col):
    m = folium.Map(location=[DEHRADUN_LAT, DEHRADUN_LON], zoom_start=13, tiles="CartoDB dark_matter")
    if flood_gdf is not None and not flood_gdf.empty:
        folium.GeoJson(flood_gdf.__geo_interface__, name="Flood Zones",
            style_function=lambda x: {"fillColor":"cyan","color":"cyan","weight":2,"fillOpacity":0.3}).add_to(m)
    if buildings_gdf is not None and not buildings_gdf.empty:
        safe    = buildings_gdf[buildings_gdf[flood_col] == False]
        flooded = buildings_gdf[buildings_gdf[flood_col] == True]
        if not safe.empty:
            folium.GeoJson(safe[['geometry']].to_json(), name=f"Safe ({len(safe)})",
                style_function=lambda x: {"fillColor":"#00FF00","color":"#00FF00","weight":0.5,"fillOpacity":0.5}).add_to(m)
        if not flooded.empty:
            folium.GeoJson(flooded[['geometry']].to_json(), name=f"Flooded ({len(flooded)})",
                style_function=lambda x: {"fillColor":"#FF0000","color":"#FF0000","weight":0.5,"fillOpacity":0.7}).add_to(m)
    folium.LayerControl().add_to(m)
    return m

def show_legend(mode):
    items = [
        ("🔴","#FF0000", "Flooded Buildings" if mode=="post" else "At-Risk Buildings"),
        ("🟢","#00FF00","Safe Buildings"),
        ("🔵","cyan","Flood Zone"),
    ]
    html = '<div style="display:flex;gap:20px;align-items:center;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.15);border-radius:8px;padding:10px 20px;margin-top:6px;font-size:13px;color:white;">'
    html += '<span style="font-weight:bold">🗺️ Legend:</span>'
    for _, color, label in items:
        html += f'<span style="display:flex;align-items:center;gap:6px;"><span style="display:inline-block;width:14px;height:14px;background:{color};border-radius:3px;"></span>{label}</span>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

# ─── PREDICTION HELPERS ───────────────────────────────────────────────────────

def rainfall_to_radius(mm, hrs):
    if mm < 2.5:   base = 500
    elif mm < 7.5: base = 1000
    elif mm < 15:  base = 2000
    elif mm < 35.5:base = 3500
    elif mm < 64.5:base = 5000
    else:          base = 8000
    return base * min(1 + (hrs-1)*0.15, 2.5)

def generate_flood_zones(mm, hrs):
    r = rainfall_to_radius(mm, hrs) / 111000
    zones = []
    for river in RIVER_CORRIDORS:
        for lon, lat in river["points"]:
            zones.append({"geometry": Point(lon, lat).buffer(r), "river": river["name"]})
    gdf = gpd.GeoDataFrame(zones, crs="EPSG:4326").dissolve().reset_index(drop=True)
    return gdf

def predict_buildings(mm, hrs, buildings_gdf):
    flood_zones = generate_flood_zones(mm, hrs)
    label = "Low Risk" if mm < 7.5 else "Moderate Risk" if mm < 35.5 else "High Risk"
    result = gpd.sjoin(buildings_gdf, flood_zones[['geometry']], how='left', predicate='intersects')
    result['flood_risk'] = result['index_right'].notna()
    result['risk_label'] = np.where(result['flood_risk'], label, "Safe")
    result = result.drop_duplicates(subset=['building_id'])
    return result, flood_zones

# ─── MAIN APP ─────────────────────────────────────────────────────────────────

st.title("🌊 GeoFlood — Dehradun Flood Intelligence System")
st.markdown("Real-time flood **detection** & **prediction** using Sentinel-2 NDWI + Open-Meteo")

with st.spinner("Fetching live rainfall..."):
    rain = get_rainfall()

# Rainfall dashboard
st.subheader("🌧️ Live Rainfall — Dehradun")
c1, c2, c3, c4 = st.columns(4)
label, _ = classify_rainfall(rain["intensity"])
c1.metric("Current Intensity", f"{rain['intensity']} mm/hr")
c2.metric("Last 24 Hours", f"{rain['total_24h']} mm")
c3.metric("IMD Classification", label)
c4.metric("Last Updated", rain["updated"])
if not rain["daily_df"].empty:
    st.bar_chart(rain["daily_df"].set_index("date")["rainfall_mm"], use_container_width=True)

st.divider()

mode = st.radio("Select Mode", ["🛰️ Post-Flood Detection", "🔮 Pre-Flood Prediction"], horizontal=True)
st.divider()

# ── POST FLOOD ────────────────────────────────────────────────────────────────
if mode == "🛰️ Post-Flood Detection":
    st.subheader("🛰️ Post-Flood Detection")
    st.info("Reads **Dehradun_NDWI.tif** → finds flooded buildings")

    if st.button("🔍 Detect Flooded Buildings", type="primary"):
        with st.spinner("Loading satellite image..."):
            flood_gdf, bounds, status = load_tif()
        if status != "success":
            st.error(f"Error: {status}")
            st.stop()

        with st.spinner("Fetching buildings (first time ~1 min, then cached)..."):
            buildings_gdf, b_status = fetch_buildings(bounds)
        if buildings_gdf is None:
            st.error(f"Buildings error: {b_status}")
            st.stop()

        with st.spinner("Analysing flood intersections..."):
            result = gpd.sjoin(buildings_gdf, flood_gdf[['geometry']], how='left', predicate='intersects')
            result['is_flooded'] = result['index_right'].notna()
            result = result.drop_duplicates(subset=['building_id'])

        total = len(result)
        flooded = int(result['is_flooded'].sum())
        flood_area = round(flood_gdf.to_crs(epsg=32644).geometry.area.sum() / 1e6, 3)

        st.success("✅ Detection complete!")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Buildings", total)
        c2.metric("🔴 Flooded", flooded)
        c3.metric("🟢 Safe", total - flooded)
        c4.metric("Flood Area", f"{flood_area} km²")

        with st.spinner("Rendering map..."):
            m = build_map(result, flood_gdf, "is_flooded")
            st_folium(m, width=1400, height=600, returned_objects=[])
        show_legend("post")

        st.download_button("📥 Download Report CSV",
            pd.DataFrame({"building_id": result["building_id"], "is_flooded": result["is_flooded"],
                          "geometry": result["geometry"].astype(str)}).to_csv(index=False),
            "flood_detection_report.csv", "text/csv")

# ── PRE FLOOD ─────────────────────────────────────────────────────────────────
elif mode == "🔮 Pre-Flood Prediction":
    st.subheader("🔮 Pre-Flood Prediction")
    st.info("Uses live rainfall + river corridors to predict at-risk buildings")

    c1, c2 = st.columns(2)
    with c1:
        use_live = st.checkbox("Use Live Rainfall Data", value=True)
        if use_live:
            mm = rain["intensity"]
            st.metric("Live Intensity", f"{mm} mm/hr")
        else:
            mm = st.slider("Rainfall Intensity (mm/hr)", 0.0, 100.0, 25.0, 0.5)
    with c2:
        hrs = st.slider("Rainfall Duration (hours)", 1, 72, 6)

    if st.button("🔮 Run Prediction", type="primary"):
        with st.spinner("Fetching buildings (first time ~1 min, then cached)..."):
            buildings_gdf, b_status = fetch_buildings()
        if buildings_gdf is None:
            st.error(f"Buildings error: {b_status}")
            st.stop()

        with st.spinner("Running prediction model..."):
            result, flood_zones = predict_buildings(mm, hrs, buildings_gdf)

        at_risk = int(result['flood_risk'].sum())
        total = len(result)
        st.success("✅ Prediction complete!")
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Buildings", total)
        c2.metric("🔴 At Risk", at_risk, delta=f"{round(at_risk/total*100,1)}%" if total else "0%")
        c3.metric("🟢 Safe", total - at_risk)

        with st.spinner("Rendering map..."):
            m = build_map(result, flood_zones, "flood_risk")
            st_folium(m, width=1400, height=600, returned_objects=[])
        show_legend("pre")

        st.download_button("📥 Download Prediction CSV",
            pd.DataFrame({"building_id": result["building_id"], "flood_risk": result["flood_risk"],
                          "risk_label": result["risk_label"], "geometry": result["geometry"].astype(str)}).to_csv(index=False),
            "flood_prediction_report.csv", "text/csv")
