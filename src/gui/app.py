import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.logic.rainfall_api import get_current_rainfall, classify_rainfall
from src.logic.buildings import fetch_buildings
from src.logic.flood_processing import load_and_process_tif, get_flood_statistics
from src.logic.prediction import predict_flood_buildings, generate_flood_zones
from src.logic.analysis import intersect_buildings_with_flood

st.set_page_config(page_title="GeoFlood - Dehradun", page_icon="🌊", layout="wide")

DEHRADUN_LAT = 30.3165
DEHRADUN_LON = 78.0469


@st.cache_data(ttl=1800, show_spinner=False)
def cached_rainfall():
    return get_current_rainfall()


@st.cache_data(ttl=86400, show_spinner=False)
def cached_buildings_post():
    flood_gdf, bounds, status = load_and_process_tif()
    if status != "success":
        return None, None, None, status
    buildings_gdf, b_status = fetch_buildings(bounds)
    return flood_gdf, bounds, buildings_gdf, b_status


@st.cache_data(ttl=86400, show_spinner=False)
def cached_buildings_pre():
    return fetch_buildings()


def build_map(buildings_gdf, flood_gdf, flood_col):
    m = folium.Map(location=[DEHRADUN_LAT, DEHRADUN_LON], zoom_start=13, tiles="CartoDB dark_matter")
    if flood_gdf is not None and not flood_gdf.empty:
        folium.GeoJson(flood_gdf.__geo_interface__, name="Flood Zones",
            style_function=lambda x: {"fillColor":"cyan","color":"cyan","weight":2,"fillOpacity":0.3}).add_to(m)
    if buildings_gdf is not None and not buildings_gdf.empty:
        safe    = buildings_gdf[~buildings_gdf[flood_col]]
        flooded = buildings_gdf[buildings_gdf[flood_col]]
        if not safe.empty:
            folium.GeoJson(safe[['geometry']].to_json(), name=f"Safe ({len(safe)})",
                style_function=lambda x: {"fillColor":"#00FF00","color":"#00FF00","weight":0.5,"fillOpacity":0.5}).add_to(m)
        if not flooded.empty:
            folium.GeoJson(flooded[['geometry']].to_json(), name=f"Affected ({len(flooded)})",
                style_function=lambda x: {"fillColor":"#FF0000","color":"#FF0000","weight":0.5,"fillOpacity":0.7}).add_to(m)
    folium.LayerControl().add_to(m)
    return m


def show_legend(mode):
    lbl = "Flooded Buildings" if mode == "post" else "At-Risk Buildings"
    st.markdown(f"""
    <div style="display:flex;gap:20px;align-items:center;background:rgba(255,255,255,0.05);
        border:1px solid rgba(255,255,255,0.15);border-radius:8px;padding:10px 20px;margin-top:6px;font-size:13px;color:white;">
      <b>🗺️ Legend:</b>
      <span><span style="display:inline-block;width:12px;height:12px;background:#FF0000;border-radius:3px;margin-right:5px;"></span>{lbl}</span>
      <span><span style="display:inline-block;width:12px;height:12px;background:#00FF00;border-radius:3px;margin-right:5px;"></span>Safe Buildings</span>
      <span><span style="display:inline-block;width:12px;height:12px;background:cyan;border-radius:3px;margin-right:5px;"></span>Flood Zone</span>
    </div>""", unsafe_allow_html=True)


def run_app():
    st.title("🌊 GeoFlood — Dehradun Flood Intelligence System")
    st.markdown("Real-time flood **detection** & **prediction** · Sentinel-2 NDWI + Open-Meteo + OSM")

    with st.spinner("Fetching live rainfall..."):
        rainfall_data = cached_rainfall()

    # Rainfall dashboard
    st.subheader("🌧️ Live Rainfall — Dehradun")
    c1, c2, c3, c4 = st.columns(4)
    label, _ = classify_rainfall(rainfall_data["current_intensity_mm_hr"])
    c1.metric("Current Intensity", f"{rainfall_data['current_intensity_mm_hr']} mm/hr")
    c2.metric("Last 24 Hours",     f"{rainfall_data['total_24h_mm']} mm")
    c3.metric("IMD Classification", label)
    c4.metric("Last Updated",       rainfall_data["last_updated"])
    if not rainfall_data["daily_df"].empty:
        st.bar_chart(rainfall_data["daily_df"].set_index("date")["rainfall_mm"], use_container_width=True)

    st.divider()
    mode = st.radio("Select Mode", ["🛰️ Post-Flood Detection", "🔮 Pre-Flood Prediction"], horizontal=True)
    st.divider()

    # ── POST FLOOD ────────────────────────────────────────────────────────────
    if mode == "🛰️ Post-Flood Detection":
        st.subheader("🛰️ Post-Flood Detection")
        st.info("Reads **Dehradun_NDWI.tif** → detects flooded buildings via NDWI satellite analysis")

        if st.button("🔍 Detect Flooded Buildings", type="primary"):
            with st.spinner("Loading satellite image + buildings (first time ~1 min, then cached)..."):
                flood_gdf, bounds, buildings_gdf, status = cached_buildings_post()

            if buildings_gdf is None:
                st.error(f"Error: {status}")
                st.stop()

            with st.spinner("Running spatial intersection..."):
                result, stats = intersect_buildings_with_flood(buildings_gdf, flood_gdf)

            flood_stats = get_flood_statistics(flood_gdf)
            st.success("✅ Detection complete!")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Buildings", stats["total_buildings"])
            c2.metric("🔴 Flooded",      stats["flooded_buildings"])
            c3.metric("🟢 Safe",         stats["safe_buildings"])
            c4.metric("Flood Area",      f"{flood_stats.get('total_flood_area_km2', 0)} km²")

            with st.spinner("Rendering map..."):
                st_folium(build_map(result, flood_gdf, "is_flooded"), width=1400, height=600, returned_objects=[])
            show_legend("post")

            st.download_button("📥 Download CSV",
                pd.DataFrame({"building_id": result["building_id"],
                              "is_flooded":  result["is_flooded"],
                              "geometry":    result["geometry"].astype(str)}).to_csv(index=False),
                "flood_detection.csv", "text/csv")

    # ── PRE FLOOD ─────────────────────────────────────────────────────────────
    elif mode == "🔮 Pre-Flood Prediction":
        st.subheader("🔮 Pre-Flood Prediction")
        st.info("Uses live rainfall + Rispana & Bindal river corridors to predict at-risk buildings")

        c1, c2 = st.columns(2)
        with c1:
            use_live = st.checkbox("Use Live Rainfall Data", value=True)
            if use_live:
                rainfall_input = rainfall_data["current_intensity_mm_hr"]
                st.metric("Live Intensity", f"{rainfall_input} mm/hr")
            else:
                rainfall_input = st.slider("Rainfall Intensity (mm/hr)", 0.0, 100.0, 25.0, 0.5)
        with c2:
            duration = st.slider("Rainfall Duration (hours)", 1, 72, 6)

        if st.button("🔮 Run Prediction", type="primary"):
            with st.spinner("Fetching buildings (first time ~1 min, then cached)..."):
                buildings_gdf, b_status = cached_buildings_pre()

            if buildings_gdf is None:
                st.error(f"Buildings error: {b_status}")
                st.stop()

            with st.spinner("Running prediction model..."):
                result, flood_zones = predict_flood_buildings(rainfall_input, duration, buildings_gdf)

            at_risk = int(result['flood_risk'].sum())
            total   = len(result)
            st.success("✅ Prediction complete!")
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Buildings", total)
            c2.metric("🔴 At Risk", at_risk, delta=f"{round(at_risk/total*100,1)}%" if total else "0%")
            c3.metric("🟢 Safe",    total - at_risk)

            with st.spinner("Rendering map..."):
                st_folium(build_map(result, flood_zones, "flood_risk"), width=1400, height=600, returned_objects=[])
            show_legend("pre")

            st.download_button("📥 Download CSV",
                pd.DataFrame({"building_id": result["building_id"],
                              "flood_risk":  result["flood_risk"],
                              "risk_label":  result["risk_label"],
                              "geometry":    result["geometry"].astype(str)}).to_csv(index=False),
                "flood_prediction.csv", "text/csv")


if __name__ == "__main__":
    run_app()
