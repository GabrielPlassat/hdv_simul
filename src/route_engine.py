"""
Route engine: OpenStreetMap routing + elevation data
Uses free/open APIs:
  - Nominatim  → geocoding (addresses → lat/lon)
  - OSRM       → route geometry
  - Open-Topo-Data → elevation along route
"""

import time
import math
import requests
import numpy as np
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
# Geocoding (Nominatim)
# ──────────────────────────────────────────────────────────────────────────────

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

def geocode(address: str, timeout: int = 10) -> Optional[dict]:
    """
    Convert an address string to lat/lon using Nominatim.
    Returns dict with 'lat', 'lon', 'display_name' or None.
    """
    params = {
        "q":      address,
        "format": "json",
        "limit":  1,
    }
    headers = {"User-Agent": "BET-Simulator/1.0 (educational POC)"}
    try:
        r = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=timeout)
        r.raise_for_status()
        results = r.json()
        if results:
            return {
                "lat":          float(results[0]["lat"]),
                "lon":          float(results[0]["lon"]),
                "display_name": results[0]["display_name"],
            }
    except Exception as e:
        print(f"Geocoding error: {e}")
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Routing (OSRM)
# ──────────────────────────────────────────────────────────────────────────────

OSRM_URL = "https://router.project-osrm.org/route/v1/driving"

def get_osrm_route(origin: dict, destination: dict, timeout: int = 15) -> Optional[dict]:
    """
    Get driving route from OSRM between two lat/lon points.

    Returns dict with:
        - distance_m    : total route distance [m]
        - duration_s    : estimated travel time [s]
        - coordinates   : list of [lon, lat] waypoints (decoded polyline)
        - geometry      : raw encoded polyline
    """
    coords = f"{origin['lon']},{origin['lat']};{destination['lon']},{destination['lat']}"
    url = f"{OSRM_URL}/{coords}"
    params = {
        "overview":    "full",
        "geometries":  "geojson",
        "steps":       "false",
    }
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()

        if data.get("code") != "Ok" or not data.get("routes"):
            return None

        route = data["routes"][0]
        coords_list = route["geometry"]["coordinates"]  # [lon, lat] pairs

        return {
            "distance_m":  route["distance"],
            "duration_s":  route["duration"],
            "coordinates": coords_list,   # [[lon, lat], ...]
        }
    except Exception as e:
        print(f"OSRM routing error: {e}")
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Elevation (Open-Topo-Data)
# ──────────────────────────────────────────────────────────────────────────────

TOPO_URL = "https://api.opentopodata.org/v1/srtm30m"

def get_elevations(coordinates: list, batch_size: int = 100, timeout: int = 20) -> list:
    """
    Fetch elevation [m] for a list of [lon, lat] coordinates.
    Uses Open-Topo-Data (SRTM 30m, free, no key required).

    Returns list of elevation values [m] matching input coordinates.
    """
    elevations = []

    # Sample points to keep API calls reasonable (max 100/request)
    n = len(coordinates)
    if n > 200:
        # Subsample to ~200 points for long routes
        indices = np.linspace(0, n - 1, 200, dtype=int)
        sampled = [coordinates[i] for i in indices]
    else:
        sampled = coordinates
        indices  = list(range(n))

    # Process in batches
    raw_elevs = []
    for i in range(0, len(sampled), batch_size):
        batch = sampled[i:i + batch_size]
        locations = "|".join(f"{lat},{lon}" for lon, lat in batch)
        try:
            r = requests.get(
                TOPO_URL,
                params={"locations": locations},
                timeout=timeout,
            )
            r.raise_for_status()
            results = r.json().get("results", [])
            raw_elevs.extend([res.get("elevation") or 0.0 for res in results])
            time.sleep(0.3)  # be polite to free API
        except Exception as e:
            print(f"Elevation API error: {e}")
            raw_elevs.extend([0.0] * len(batch))

    # Interpolate back to full coordinate list if we subsampled
    if n > 200:
        sampled_dist = [0.0]
        for k in range(1, len(indices)):
            prev = coordinates[indices[k - 1]]
            curr = coordinates[indices[k]]
            sampled_dist.append(sampled_dist[-1] + haversine_m(prev[1], prev[0], curr[1], curr[0]))

        full_dist = [0.0]
        for k in range(1, n):
            prev = coordinates[k - 1]
            curr = coordinates[k]
            full_dist.append(full_dist[-1] + haversine_m(prev[1], prev[0], curr[1], curr[0]))

        # Linear interpolation
        elevations = list(np.interp(full_dist, sampled_dist, raw_elevs))
    else:
        elevations = raw_elevs

    return elevations


# ──────────────────────────────────────────────────────────────────────────────
# Route segmentation
# ──────────────────────────────────────────────────────────────────────────────

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in metres between two lat/lon points (Haversine formula)."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlam  = math.radians(lon2 - lon1)
    a     = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def build_route_segments(
    coordinates: list,
    elevations:  list,
    n_segments:  int = 50,
    avg_speed_kmh: float = 50.0,
) -> list:
    """
    Aggregate route waypoints into n_segments for the physics model.
    Each segment gets: distance_m, slope_deg, cumulative_km, elevation_m.

    Args:
        coordinates:    [[lon, lat], ...] from OSRM
        elevations:     elevation [m] for each coordinate
        n_segments:     number of output segments
        avg_speed_kmh:  default speed per segment

    Returns:
        list of segment dicts
    """
    n = len(coordinates)
    if n < 2:
        return []

    # Build cumulative distance + elevation arrays
    cum_dist_m = [0.0]
    for i in range(1, n):
        lon1, lat1 = coordinates[i - 1]
        lon2, lat2 = coordinates[i]
        d = haversine_m(lat1, lon1, lat2, lon2)
        cum_dist_m.append(cum_dist_m[-1] + d)

    total_dist_m = cum_dist_m[-1]

    # Segment boundaries
    segment_edges = np.linspace(0, total_dist_m, n_segments + 1)

    segments = []
    for k in range(n_segments):
        d_start = segment_edges[k]
        d_end   = segment_edges[k + 1]
        seg_dist = d_end - d_start
        if seg_dist <= 0:
            continue

        # Interpolate elevation at segment start and end
        elev_start = float(np.interp(d_start, cum_dist_m, elevations))
        elev_end   = float(np.interp(d_end,   cum_dist_m, elevations))
        alt_diff_m = elev_end - elev_start

        # Slope in degrees
        slope_deg  = math.degrees(math.atan2(alt_diff_m, seg_dist))

        # Mid-point elevation for display
        elev_mid = (elev_start + elev_end) / 2.0

        segments.append({
            "distance_m":      seg_dist,
            "slope_deg":       slope_deg,
            "alt_diff_m":      alt_diff_m,
            "elevation_m":     elev_mid,
            "cum_km":          d_start / 1000.0,
            "speed_kmh":       avg_speed_kmh,
        })

    return segments


def full_route_pipeline(
    origin_address:      str,
    destination_address: str,
    avg_speed_kmh:       float = 50.0,
    n_segments:          int   = 60,
) -> Optional[dict]:
    """
    Complete pipeline: geocoding → routing → elevation → segmentation.

    Returns dict with route info + segments, or None on failure.
    """
    # Geocode
    origin      = geocode(origin_address)
    destination = geocode(destination_address)

    if origin is None:
        return {"error": f"Adresse introuvable : '{origin_address}'"}
    if destination is None:
        return {"error": f"Adresse introuvable : '{destination_address}'"}

    # Route
    route = get_osrm_route(origin, destination)
    if route is None:
        return {"error": "Impossible d'obtenir l'itinéraire OSRM"}

    # Elevation
    elevations = get_elevations(route["coordinates"])

    # Segments
    segments = build_route_segments(
        coordinates   = route["coordinates"],
        elevations    = elevations,
        n_segments    = n_segments,
        avg_speed_kmh = avg_speed_kmh,
    )

    # Total altitude stats
    elev_array   = np.array(elevations)
    alt_diff_total = float(elev_array[-1] - elev_array[0])
    total_ascent   = float(np.sum(np.maximum(np.diff(elev_array), 0)))
    total_descent  = float(np.sum(np.maximum(-np.diff(elev_array), 0)))

    return {
        "origin":          origin,
        "destination":     destination,
        "distance_m":      route["distance_m"],
        "duration_s":      route["duration_s"],
        "coordinates":     route["coordinates"],
        "elevations":      elevations,
        "segments":        segments,
        "alt_diff_m":      alt_diff_total,
        "total_ascent_m":  total_ascent,
        "total_descent_m": total_descent,
    }
