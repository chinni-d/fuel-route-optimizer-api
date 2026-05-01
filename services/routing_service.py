import pandas as pd
import os
import requests
from django.core.cache import cache
import logging
from services.fuel_optimizer import optimize_fuel_stops

logger = logging.getLogger(__name__)

cities_df = None

def _load_cities():
    global cities_df
    if cities_df is None:
        from django.conf import settings
        cities_path = os.path.join(settings.BASE_DIR, 'data', 'us_cities.csv')
        cities_df = pd.read_csv(cities_path)
        cities_df['CITY_lower'] = cities_df['CITY'].astype(str).str.strip().str.lower()
        cities_df['STATE_lower'] = cities_df['STATE_CODE'].astype(str).str.strip().str.lower()

def geocode_location(location_name):
    """
    Returns (lat, lon) using local us_cities.csv.
    location_name format: "City, ST"
    """
    _load_cities()
    parts = [p.strip() for p in location_name.split(',')]
    if len(parts) != 2:
        raise ValueError("Location must be in 'City, ST' format")
    city, state = parts[0].lower(), parts[1].lower()
    
    match = cities_df[(cities_df['CITY_lower'] == city) & (cities_df['STATE_lower'] == state)]
    if match.empty:
        raise ValueError(f"Could not geocode location: {location_name}")
        
    row = match.iloc[0]
    return float(row['LATITUDE']), float(row['LONGITUDE'])

from django.core.cache import cache

def get_route(start_coords, end_coords):
    """
    Uses OSRM public API to get driving route.
    Returns (distance_miles, route_coords)
    """
    lon1, lat1 = start_coords[1], start_coords[0]
    lon2, lat2 = end_coords[1], end_coords[0]
    
    cache_key = f"route_{lon1}_{lat1}_{lon2}_{lat2}"
    cached_data = cache.get(cache_key)
    if cached_data:
        return cached_data['distance_miles'], cached_data['coordinates']
    
    url = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    
    if data['code'] != 'Ok':
        raise ValueError("Could not find a route")
        
    route = data['routes'][0]
    distance_meters = route['distance']
    distance_miles = distance_meters * 0.000621371
    coordinates = route['geometry']['coordinates'] # [[lon, lat], ...]
    
    cache.set(cache_key, {'distance_miles': distance_miles, 'coordinates': coordinates}, timeout=86400)
    
    return distance_miles, coordinates

def get_optimized_route_and_fuel(start_location, end_location):
    logger.info(f"Geocoding {start_location}")
    start_coords = geocode_location(start_location)
    
    logger.info(f"Geocoding {end_location}")
    end_coords = geocode_location(end_location)
    
    logger.info(f"Getting route from {start_coords} to {end_coords}")
    distance_miles, route_coords = get_route(start_coords, end_coords)
    
    logger.info(f"Total distance: {distance_miles} miles. Optimizing fuel stops...")
    fuel_stops, total_fuel_cost = optimize_fuel_stops(route_coords, distance_miles)
    
    # Sample route coords to reduce response size drastically (Issue 4)
    # A step of 50 significantly compresses the thousands of coordinates down to a lightweight size.
    sampled_coords = route_coords[::50]
    
    return {
        "distance_miles": round(distance_miles, 2),
        "fuel_stops": fuel_stops,
        "total_cost": round(total_fuel_cost, 2),
        "route_polyline": sampled_coords
    }
