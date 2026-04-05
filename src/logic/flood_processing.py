import numpy as np
import geopandas as gpd
from shapely.geometry import shape
from shapely.ops import unary_union
import os

NDWI_THRESHOLD = 0.0

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
TIF_PATH = os.path.join(DATA_DIR, 'Dehradun_NDWI.tif')

# Module-level cache so the TIF is only processed once per process lifetime
_FLOOD_CACHE = {"gdf": None, "bounds": None, "status": None}


def load_and_process_tif():
    # Return from in-memory cache if already loaded
    if _FLOOD_CACHE["status"] == "success":
        return _FLOOD_CACHE["gdf"], _FLOOD_CACHE["bounds"], "success"

    if not os.path.exists(TIF_PATH):
        return None, None, f"TIF file not found at: {TIF_PATH}"
    try:
        import rasterio
        from rasterio.features import shapes
        from rasterio.enums import Resampling

        with rasterio.open(TIF_PATH) as src:
            # Downsample by 2x for speed — still accurate enough for flood zones
            out_shape = (1, max(src.height // 2, 1), max(src.width // 2, 1))
            data = src.read(
                1,
                out_shape=out_shape,
                resampling=Resampling.average
            ).astype(np.float32)

            # Build a scaled transform matching the downsampled grid
            from rasterio.transform import from_bounds
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

        # Extract polygons — limit to meaningful ones (area > tiny noise pixels)
        flood_polygons = [
            shape(g)
            for g, v in shapes(flood_mask, transform=transform)
            if v == 1
        ]

        if not flood_polygons:
            _FLOOD_CACHE["status"] = "no_flood"
            return None, None, "No flood zones detected."

        # Merge overlapping polygons immediately → fewer geometries, faster joins later
        merged = unary_union(flood_polygons)
        if merged.geom_type == "Polygon":
            merged = [merged]
        elif merged.geom_type == "MultiPolygon":
            merged = list(merged.geoms)
        else:
            merged = flood_polygons  # fallback

        # Filter out tiny noise polygons (< 0.000001 sq-deg ≈ ~10 m²)
        merged = [g for g in merged if g.area > 1e-6]

        flood_gdf = gpd.GeoDataFrame(geometry=merged, crs=crs).to_crs(epsg=4326)

        bounds_wgs84 = {
            "min_lon": bounds.left,  "max_lon": bounds.right,
            "min_lat": bounds.bottom, "max_lat": bounds.top,
        }

        # Store in module-level cache
        _FLOOD_CACHE["gdf"]    = flood_gdf
        _FLOOD_CACHE["bounds"] = bounds_wgs84
        _FLOOD_CACHE["status"] = "success"

        return flood_gdf, bounds_wgs84, "success"

    except Exception as e:
        return None, None, str(e)


def get_flood_statistics(flood_gdf):
    if flood_gdf is None or flood_gdf.empty:
        return {}
    try:
        area_km2 = flood_gdf.to_crs(epsg=32644).geometry.area.sum() / 1e6
        return {
            "total_flood_area_km2": round(area_km2, 3),
            "flood_polygon_count": len(flood_gdf),
        }
    except Exception:
        return {"total_flood_area_km2": 0, "flood_polygon_count": 0}
