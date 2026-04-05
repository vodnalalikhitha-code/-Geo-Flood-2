import numpy as np
import geopandas as gpd
from shapely.geometry import shape
import os

NDWI_THRESHOLD = 0.0

# Path: goes up from src/logic/ to project root, then into data/
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
TIF_PATH = os.path.join(DATA_DIR, 'Dehradun_NDWI.tif')


def load_and_process_tif():
    if not os.path.exists(TIF_PATH):
        return None, None, f"TIF file not found at: {TIF_PATH}"
    try:
        import rasterio
        from rasterio.features import shapes
        with rasterio.open(TIF_PATH) as src:
            data      = src.read(1).astype(float)
            transform = src.transform
            crs       = src.crs
            bounds    = src.bounds
            nodata    = src.nodata

        if nodata is not None:
            data = np.where(data == nodata, np.nan, data)

        flood_mask = (data > NDWI_THRESHOLD).astype(np.uint8)
        flood_polygons = [shape(g) for g, v in shapes(flood_mask, transform=transform) if v == 1]

        if not flood_polygons:
            return None, None, "No flood zones detected."

        flood_gdf = gpd.GeoDataFrame(geometry=flood_polygons, crs=crs).to_crs(epsg=4326)
        bounds_wgs84 = {
            "min_lon": bounds.left,  "max_lon": bounds.right,
            "min_lat": bounds.bottom,"max_lat": bounds.top
        }
        return flood_gdf, bounds_wgs84, "success"

    except Exception as e:
        return None, None, str(e)


def get_flood_statistics(flood_gdf):
    if flood_gdf is None or flood_gdf.empty:
        return {}
    try:
        area_km2 = flood_gdf.to_crs(epsg=32644).geometry.area.sum() / 1e6
        return {"total_flood_area_km2": round(area_km2, 3), "flood_polygon_count": len(flood_gdf)}
    except:
        return {"total_flood_area_km2": 0, "flood_polygon_count": 0}
