import numpy as np
import geopandas as gpd
from shapely.geometry import shape
from shapely.ops import unary_union
import os
import json

NDWI_THRESHOLD = 0.0

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
TIF_PATH = os.path.join(DATA_DIR, 'Dehradun_NDWI.tif')
# Pre-processed flood zones saved as GeoJSON so TIF is never read at runtime
FLOOD_GEOJSON_PATH = os.path.join(DATA_DIR, 'flood_zones.geojson')

_CACHE = {"gdf": None, "bounds": None, "status": None}


def load_and_process_tif():
    # Return from memory cache first
    if _CACHE["status"] == "success":
        return _CACHE["gdf"], _CACHE["bounds"], "success"

    # Fast path: load pre-processed GeoJSON if it exists
    if os.path.exists(FLOOD_GEOJSON_PATH):
        try:
            flood_gdf = gpd.read_file(FLOOD_GEOJSON_PATH)
            # Compute bounds from the GeoJSON itself
            b = flood_gdf.total_bounds  # [minx, miny, maxx, maxy]
            bounds_wgs84 = {
                "min_lon": b[0], "max_lon": b[2],
                "min_lat": b[1], "max_lat": b[3],
            }
            _CACHE["gdf"] = flood_gdf
            _CACHE["bounds"] = bounds_wgs84
            _CACHE["status"] = "success"
            return flood_gdf, bounds_wgs84, "success"
        except Exception:
            pass  # fall through to TIF processing

    # Slow path: process TIF (only runs once, result saved as GeoJSON)
    if not os.path.exists(TIF_PATH):
        return None, None, f"TIF file not found at: {TIF_PATH}"
    try:
        import rasterio
        from rasterio.features import shapes
        from rasterio.enums import Resampling
        from rasterio.transform import from_bounds

        with rasterio.open(TIF_PATH) as src:
            out_shape = (1, max(src.height // 2, 1), max(src.width // 2, 1))
            data = src.read(1, out_shape=out_shape,
                            resampling=Resampling.average).astype(np.float32)
            transform = from_bounds(
                src.bounds.left, src.bounds.bottom,
                src.bounds.right, src.bounds.top,
                out_shape[2], out_shape[1]
            )
            crs    = src.crs
            bounds = src.bounds
            nodata = src.nodata

        if nodata is not None:
            data = np.where(data == nodata, np.nan, data)

        flood_mask = (data > NDWI_THRESHOLD).astype(np.uint8)
        flood_polygons = [shape(g) for g, v in shapes(flood_mask, transform=transform) if v == 1]

        if not flood_polygons:
            return None, None, "No flood zones detected."

        merged = unary_union(flood_polygons)
        if merged.geom_type == "Polygon":
            geoms = [merged]
        elif merged.geom_type == "MultiPolygon":
            geoms = list(merged.geoms)
        else:
            geoms = flood_polygons

        geoms = [g for g in geoms if g.area > 1e-6]
        flood_gdf = gpd.GeoDataFrame(geometry=geoms, crs=crs).to_crs(epsg=4326)

        # Save as GeoJSON so next time it loads instantly
        flood_gdf.to_file(FLOOD_GEOJSON_PATH, driver="GeoJSON")

        bounds_wgs84 = {
            "min_lon": bounds.left,  "max_lon": bounds.right,
            "min_lat": bounds.bottom, "max_lat": bounds.top,
        }
        _CACHE["gdf"]    = flood_gdf
        _CACHE["bounds"] = bounds_wgs84
        _CACHE["status"] = "success"
        return flood_gdf, bounds_wgs84, "success"

    except Exception as e:
        return None, None, str(e)


def get_flood_statistics(flood_gdf):
    if flood_gdf is None or flood_gdf.empty:
        return {}
    try:
        area_km2 = flood_gdf.to_crs(epsg=32644).geometry.area.sum() / 1e6
        return {"total_flood_area_km2": round(area_km2, 3),
                "flood_polygon_count": len(flood_gdf)}
    except Exception:
        return {"total_flood_area_km2": 0, "flood_polygon_count": 0}
