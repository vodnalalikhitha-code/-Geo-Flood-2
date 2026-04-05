import geopandas as gpd


def intersect_buildings_with_flood(buildings_gdf, flood_gdf):
    if buildings_gdf is None or flood_gdf is None:
        return None, {}
    try:
        result = gpd.sjoin(buildings_gdf, flood_gdf[['geometry']], how='left', predicate='intersects')
        result['is_flooded'] = result['index_right'].notna()
        result = result.drop_duplicates(subset=['building_id'])
        total   = len(result)
        flooded = int(result['is_flooded'].sum())
        return result, {
            "total_buildings": total,
            "flooded_buildings": flooded,
            "safe_buildings": total - flooded,
            "flood_percentage": round(flooded / total * 100, 1) if total > 0 else 0
        }
    except Exception as e:
        return None, {"error": str(e)}
