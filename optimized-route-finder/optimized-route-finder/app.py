import streamlit as st
import requests
from streamlit_folium import st_folium
import folium
from typing import List, Tuple, Optional

ORS_API_KEY = st.secrets["ORS_API_KEY"]
ORS_BASE = "https://api.openrouteservice.org"

# -----------------------------
# Utilities
# -----------------------------
def geocode(address: str, api_key: str) -> Optional[Tuple[float, float]]:
    if not address:
        return None
    url = f"{ORS_BASE}/geocode/search"
    headers = {"Authorization": api_key}
    params = {"text": address, "size": 1}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        feats = data.get("features", [])
        if not feats:
            return None
        coords = feats[0]["geometry"]["coordinates"]
        return (float(coords[0]), float(coords[1]))
    except Exception as e:
        st.error(f"Geocoding failed for '{address}': {e}")
        return None

def get_route(start: Tuple[float, float], end: Tuple[float, float],
              waypoints: List[Tuple[float, float]], api_key: str) -> Optional[dict]:
    url = f"{ORS_BASE}/v2/directions/driving-car/geojson"
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    coords = [list(start)] + [list(wp) for wp in waypoints] + [list(end)]
    body = {"coordinates": coords, "instructions": True, "elevation": False, "format": "geojson"}
    try:
        r = requests.post(url, headers=headers, json=body, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Routing request failed: {e}")
        return None

def draw_map(start: Tuple[float, float], end: Tuple[float, float],
             waypoints: List[Tuple[float, float]], route_info: dict) -> folium.Map:
    fmap = folium.Map(zoom_start=13)

    # Start pin
    folium.Marker([start[1], start[0]], tooltip="Start",
                  icon=folium.Icon(color="green")).add_to(fmap)

    # Waypoints with numbering
    for i, wp in enumerate(waypoints, start=1):
        folium.Marker([wp[1], wp[0]], tooltip=f"Waypoint {i}",
                      icon=folium.DivIcon(html=f"""<div style="font-size:12pt; color:white; background:blue; border-radius:50%; text-align:center; width:24px; height:24px;">{i}</div>""")).add_to(fmap)

    # End pin
    folium.Marker([end[1], end[0]], tooltip="Destination",
                  icon=folium.Icon(color="red")).add_to(fmap)

    # Route segments coloring
    if route_info and "features" in route_info:
        geom = route_info["features"][0]["geometry"]
        coords = geom["coordinates"]
        folium.PolyLine([(c[1], c[0]) for c in coords], color="orange", weight=5, opacity=0.8).add_to(fmap)
        bbox = route_info["features"][0].get("bbox")
        if bbox:
            fmap.fit_bounds([[bbox[1], bbox[0]], [bbox[3], bbox[2]]])
    return fmap

# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="Optimized Route Finder", layout="wide")
st.title("🗺️ Optimized Route Finder")

col1, col2 = st.columns([1, 2])

with col1:
    start_addr = st.text_input("Start Location", "")
    end_addr = st.text_input("Destination", "")
    waypoints_text = st.text_area("Waypoints (one per line)", "")

if start_addr and end_addr:
    with st.spinner("Computing route..."):
        start_coords = geocode(start_addr, ORS_API_KEY)
        end_coords = geocode(end_addr, ORS_API_KEY)
        waypoint_coords = [geocode(wp.strip(), ORS_API_KEY) for wp in waypoints_text.splitlines() if wp.strip()]
        waypoint_coords = [wp for wp in waypoint_coords if wp]

        if start_coords and end_coords:
            route_info = get_route(start_coords, end_coords, waypoint_coords, ORS_API_KEY)
            if route_info and "features" in route_info:
                fmap = draw_map(start_coords, end_coords, waypoint_coords, route_info)
                with col2:
                    st_folium(fmap, width=800, height=600, returned_objects=[])

                    # Summary
                    summary = route_info["features"][0]["properties"]["summary"]
                    st.success(f"Distance: {summary['distance']/1000:.2f} km, Duration: {summary['duration']/60:.1f} min")

                    # Turn-by-turn directions
                    st.subheader("📝 Directions")
                    steps = route_info["features"][0]["properties"].get("segments", [])[0].get("steps", [])
                    for i, s in enumerate(steps, 1):
                        st.write(f"{i}. {s['instruction']} ({s['distance']:.0f} m, {s['duration']:.0f} sec)")
            else:
                st.error("❌ No route data returned. Check inputs or API key.")
        else:
            st.error("❌ Could not geocode start or destination.")
