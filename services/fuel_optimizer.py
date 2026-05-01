import os
import math
import pandas as pd
import numpy as np
import logging
from scipy.spatial import cKDTree

logger = logging.getLogger(__name__)

class FuelStationDatabase:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FuelStationDatabase, cls).__new__(cls)
            cls._instance._load_data()
        return cls._instance

    def _load_data(self):
        from django.conf import settings
        fuel_path = os.path.join(settings.BASE_DIR, 'data', 'fuel-prices-for-be-assessment.csv')
        cities_path = os.path.join(settings.BASE_DIR, 'data', 'us_cities.csv')

        try:
            fuel_df = pd.read_csv(fuel_path)
            cities_df = pd.read_csv(cities_path)

            # Normalize city and state for merging
            fuel_df['City_lower'] = fuel_df['City'].astype(str).str.strip().str.lower()
            fuel_df['State_lower'] = fuel_df['State'].astype(str).str.strip().str.lower()
            
            cities_df['CITY_lower'] = cities_df['CITY'].astype(str).str.strip().str.lower()
            cities_df['STATE_lower'] = cities_df['STATE_CODE'].astype(str).str.strip().str.lower()

            # Drop duplicates in cities_df to avoid multiplying fuel stations
            cities_unique = cities_df.drop_duplicates(subset=['CITY_lower', 'STATE_lower'])

            # Merge to get coordinates for fuel stations
            self.stations = pd.merge(
                fuel_df, 
                cities_unique[['CITY_lower', 'STATE_lower', 'LATITUDE', 'LONGITUDE']], 
                left_on=['City_lower', 'State_lower'], 
                right_on=['CITY_lower', 'STATE_lower'], 
                how='inner'
            )
            
            logger.info(f"Loaded {len(self.stations)} fuel stations with coordinates out of {len(fuel_df)}")

            # Create a spatial index (KDTree) for fast nearest-neighbor lookups
            # Coordinates need to be in radians for haversine distance
            self.coords_rad = np.radians(self.stations[['LATITUDE', 'LONGITUDE']].values)
            self.tree = cKDTree(self.coords_rad)

        except Exception as e:
            logger.error(f"Error loading datasets: {e}")
            self.stations = pd.DataFrame()
            self.tree = None

    def get_stations_within_radius(self, lat, lon, radius_miles):
        if self.tree is None or self.stations.empty:
            return pd.DataFrame()

        # Earth radius in miles
        R = 3958.8
        radius_rad = radius_miles / R

        query_pt = np.radians([lat, lon])
        indices = self.tree.query_ball_point(query_pt, radius_rad)
        
        return self.stations.iloc[indices]

fuel_db = FuelStationDatabase()

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 3958.8
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def optimize_fuel_stops(route_coords, total_distance_miles):
    """
    route_coords: list of [lon, lat]
    total_distance_miles: float
    """
    if total_distance_miles <= 500:
        return [], 0.0

    # Calculate cumulative distance for each point in the route
    cum_distances = [0.0]
    for i in range(1, len(route_coords)):
        prev_lon, prev_lat = route_coords[i-1]
        curr_lon, curr_lat = route_coords[i]
        dist = haversine_distance(prev_lat, prev_lon, curr_lat, curr_lon)
        cum_distances.append(cum_distances[-1] + dist)

    cum_distances = np.array(cum_distances)
    
    max_range = 500.0
    current_dist = 0.0
    stops = []
    total_cost = 0.0
    
    # We assume vehicle starts with a full tank (50 gallons)
    # We refuel when we get low. At each stop, we assume we buy 50 gallons
    gallons_per_stop = 50.0 
    
    while current_dist + max_range < total_distance_miles:
        # Define a window to look for fuel: e.g. between 350 and 480 miles from current
        window_start = current_dist + 350.0
        window_end = current_dist + 480.0
        
        # Find all route coordinates within this distance window
        start_idx = np.searchsorted(cum_distances, window_start)
        end_idx = np.searchsorted(cum_distances, window_end)
        
        if start_idx >= len(route_coords):
            break
            
        if start_idx == end_idx:
            end_idx = min(start_idx + 1, len(route_coords))
            
        window_coords = route_coords[start_idx:end_idx]
        
        # Sample points to speed up KDTree query
        sampled_window = window_coords[::5]
        
        radius_miles = 30.0
        R = 3958.8
        radius_rad = radius_miles / R
        
        if fuel_db.tree is None or fuel_db.stations.empty:
            logger.warning("No fuel database available")
            break
            
        pts_lat_lon = [[pt[1], pt[0]] for pt in sampled_window]
        query_pts = np.radians(pts_lat_lon)
        
        list_of_indices = fuel_db.tree.query_ball_point(query_pts, radius_rad)
        
        unique_indices = set()
        for indices in list_of_indices:
            unique_indices.update(indices)
            
        if not unique_indices:
            # Expand search if nothing found
            radius_rad = 60.0 / R
            list_of_indices = fuel_db.tree.query_ball_point(query_pts, radius_rad)
            for indices in list_of_indices:
                unique_indices.update(indices)
                
        if not unique_indices:
            logger.warning(f"No fuel stations found in window {window_start}-{window_end}")
            current_dist += 450.0 # Force advance
            continue
            
        candidate_stations = fuel_db.stations.iloc[list(unique_indices)]
        best_station = candidate_stations.loc[candidate_stations['Retail Price'].idxmin()]
        
        best_lat, best_lon = best_station['LATITUDE'], best_station['LONGITUDE']
        min_dist = float('inf')
        closest_dist_val = window_start # fallback
        
        for idx_window, pt in enumerate(sampled_window):
            pt_lon, pt_lat = pt[0], pt[1]
            dist_to_station = haversine_distance(pt_lat, pt_lon, best_lat, best_lon)
            if dist_to_station < min_dist:
                min_dist = dist_to_station
                original_idx = start_idx + (idx_window * 5)
                if original_idx < len(cum_distances):
                    closest_dist_val = cum_distances[original_idx]
                    
        stops.append({
            "city": best_station['City'],
            "state": best_station['State'],
            "price_per_gallon": best_station['Retail Price'],
            "distance_along_route": closest_dist_val
        })
        
        current_dist = closest_dist_val

    # Calculate precise fuel cost
    total_cost = 0.0
    previous_stop_dist = 0.0
    
    for i, stop in enumerate(stops):
        # Calculate distance for this segment
        segment_dist = stop["distance_along_route"] - previous_stop_dist
        gallons_needed = segment_dist / 10.0
        
        # If this is the last stop, also account for the final leg to the destination
        if i == len(stops) - 1:
            final_leg_dist = total_distance_miles - stop["distance_along_route"]
            gallons_needed += final_leg_dist / 10.0
            
        # Cost is gallons * price
        segment_cost = gallons_needed * stop["price_per_gallon"]
        total_cost += segment_cost
        
        # Update for next iteration
        previous_stop_dist = stop["distance_along_route"]
        
        # Remove the internal key before returning
        del stop["distance_along_route"]
        
    return stops, total_cost
