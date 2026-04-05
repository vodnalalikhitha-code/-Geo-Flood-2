import requests
import pandas as pd
from datetime import datetime, timedelta

DEHRADUN_LAT = 30.3165
DEHRADUN_LON = 78.0469


def get_current_rainfall():
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": DEHRADUN_LAT,
        "longitude": DEHRADUN_LON,
        "hourly": "precipitation",
        "daily": "precipitation_sum",
        "timezone": "Asia/Kolkata",
        "past_days": 7,
        "forecast_days": 3
    }
    try:
        r = requests.get(url, params=params, timeout=10).json()
        now = datetime.now()
        cur = now.strftime("%Y-%m-%dT%H:00")
        start = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:00")
        recent = [p or 0 for t, p in zip(r["hourly"]["time"], r["hourly"]["precipitation"]) if start <= t <= cur]
        daily_df = pd.DataFrame({
            "date": r["daily"]["time"],
            "rainfall_mm": [x or 0 for x in r["daily"]["precipitation_sum"]]
        })
        return {
            "current_intensity_mm_hr": round(recent[-1] if recent else 0, 2),
            "total_24h_mm": round(sum(recent), 2),
            "daily_df": daily_df,
            "status": "success",
            "last_updated": now.strftime("%H:%M, %d %b %Y")
        }
    except Exception as e:
        return {
            "current_intensity_mm_hr": 0.3,
            "total_24h_mm": 2.1,
            "daily_df": pd.DataFrame(),
            "status": f"error: {str(e)}",
            "last_updated": datetime.now().strftime("%H:%M, %d %b %Y")
        }


def classify_rainfall(mm_per_hr):
    if mm_per_hr < 2.5:   return "Light Rain", "#00FF00"
    elif mm_per_hr < 7.5: return "Moderate Rain", "#FFFF00"
    elif mm_per_hr < 35.5:return "Heavy Rain", "#FFA500"
    elif mm_per_hr < 64.5:return "Very Heavy Rain", "#FF4500"
    else:                  return "Extremely Heavy Rain", "#FF0000"
