from flask import Flask, render_template, request, jsonify
import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional, Dict, Any
import time
import secrets
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max
app.config['UPLOAD_FOLDER'] = 'uploads'

# Create uploads folder
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ============================================================================
# CONFIGURATION
# ============================================================================
ORS_API_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjdhY2ZkOTdhMTNiNGQwMjFjMDYyYWJiYTljNzUwODQ1MjgzNDcwZmY3OTc4NDBmYWVjODk5NmE3IiwiaCI6Im11cm11cjY0In0="  # Replace with your OpenRouteService API key
ORS_BASE_URL = "https://api.openrouteservice.org"
DEFAULT_TIMEOUT = 15
MAX_WORKERS = 3  # Parallel geocoding workers

# ============================================================================
# ROUTE OPTIMIZER CLASS
# ============================================================================
class RouteOptimizer:
    """
    Handles all routing operations:
    1. Geocoding addresses to coordinates
    2. Calculating optimal routes
    3. Getting distance and duration metrics
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": api_key,
            "Content-Type": "application/json"
        })
    
    def geocode_address(self, address: str) -> Optional[Tuple[float, float]]:
        """
        Convert text address to GPS coordinates (longitude, latitude).
        
        Args:
            address: Text address like "Anna Nagar, Chennai, India"
            
        Returns:
            Tuple of (longitude, latitude) or None if failed
        """
        if not address or not isinstance(address, str):
            return None
        
        try:
            # Rate limiting to avoid API throttling
            time.sleep(0.25)
            
            response = self.session.get(
                f"{ORS_BASE_URL}/geocode/search",
                params={"text": address.strip(), "size": 1},
                timeout=DEFAULT_TIMEOUT
            )
            
            if response.status_code == 200:
                features = response.json().get("features", [])
                if features:
                    coords = features[0]["geometry"]["coordinates"]
                    # Return as (longitude, latitude)
                    return (float(coords[0]), float(coords[1]))
            
            elif response.status_code == 429:
                # Rate limit hit, wait and retry
                print(f"Rate limit hit, waiting...")
                time.sleep(1)
                return self.geocode_address(address)
            
            else:
                print(f"Geocoding failed for '{address}': Status {response.status_code}")
        
        except requests.exceptions.Timeout:
            print(f"Timeout geocoding: {address}")
        except Exception as e:
            print(f"Error geocoding '{address}': {str(e)}")
        
        return None
    
    def batch_geocode(self, addresses: List[str]) -> List[Optional[Tuple[float, float]]]:
        """
        Geocode multiple addresses in parallel for speed.
        
        Args:
            addresses: List of address strings
            
        Returns:
            List of coordinates in same order as input addresses
        """
        results = [None] * len(addresses)
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Submit all geocoding tasks
            future_to_index = {
                executor.submit(self.geocode_address, addr): i 
                for i, addr in enumerate(addresses)
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    results[index] = future.result()
                except Exception as e:
                    print(f"Error in batch geocode at index {index}: {str(e)}")
                    results[index] = None
        
        return results
    
    def calculate_route(self, coordinates: List[Tuple[float, float]]) -> Optional[Dict[str, Any]]:
        """
        Calculate optimal driving route through all coordinates.
        
        Args:
            coordinates: List of (longitude, latitude) tuples
            
        Returns:
            Dictionary with route geometry, distance, duration, and bounding box
        """
        if len(coordinates) < 2:
            return None
        
        try:
            response = self.session.post(
                f"{ORS_BASE_URL}/v2/directions/driving-car/geojson",
                json={
                    "coordinates": coordinates,
                    "instructions": False,
                    "elevation": False
                },
                timeout=DEFAULT_TIMEOUT
            )
            
            if response.status_code == 200:
                data = response.json()
                feature = data['features'][0]
                summary = feature['properties']['summary']
                
                return {
                    'geometry': feature['geometry']['coordinates'],
                    'bbox': feature['bbox'],
                    'distance_km': round(summary['distance'] / 1000, 1),
                    'distance_mi': round(summary['distance'] / 1609.34, 1),
                    'duration_min': round(summary['duration'] / 60, 1),
                    'duration_hours': round(summary['duration'] / 3600, 2)
                }
            
            elif response.status_code == 403:
                print("API Authentication Failed - Check your API key")
            elif response.status_code == 429:
                print("Rate limit exceeded")
            else:
                print(f"Route calculation error: {response.status_code}")
                print(f"Response: {response.text}")
        
        except requests.exceptions.Timeout:
            print("Request timeout")
        except Exception as e:
            print(f"Error calculating route: {str(e)}")
        
        return None

# ============================================================================
# FLASK ROUTES
# ============================================================================

@app.route('/')
def index():
    """Render the main dashboard page."""
    return render_template('index.html')

@app.route('/api/optimize', methods=['POST'])
def optimize_route():
    """
    Main endpoint for route optimization.
    
    Workflow:
    1. Validate inputs (start, end, file)
    2. Read and parse CSV/Excel file
    3. Extract locations from "Location" column
    4. Geocode all addresses (start + stops + end)
    5. Calculate optimal route
    6. Return formatted response with metrics
    """
    try:
        # ================================================================
        # STEP 1: Validate API Key
        # ================================================================
        if ORS_API_KEY == "YOUR_API_KEY_HERE" or not ORS_API_KEY:
            return jsonify({
                'success': False,
                'error': 'API key not configured. Please add your OpenRouteService API key in app.py'
            }), 400
        
        # ================================================================
        # STEP 2: Get Form Data
        # ================================================================
        start_location = request.form.get('start_location', '').strip()
        end_location = request.form.get('end_location', '').strip()
        
        # Validate required fields
        if not start_location:
            return jsonify({
                'success': False,
                'error': 'Start location is required'
            }), 400
        
        if not end_location:
            return jsonify({
                'success': False,
                'error': 'End location is required'
            }), 400
        
        # ================================================================
        # STEP 3: Validate File Upload
        # ================================================================
        if 'file' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No file uploaded. Please upload a CSV or Excel file.'
            }), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No file selected'
            }), 400
        
        # ================================================================
        # STEP 4: Read File (CSV or Excel)
        # ================================================================
        filename = secure_filename(file.filename)
        
        try:
            if filename.lower().endswith('.csv'):
                # Try different encodings
                try:
                    df = pd.read_csv(file, encoding='utf-8')
                except:
                    file.seek(0)  # Reset file pointer
                    try:
                        df = pd.read_csv(file, encoding='latin-1')
                    except:
                        file.seek(0)
                        df = pd.read_csv(file, encoding='iso-8859-1')
            elif filename.lower().endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file)
            else:
                return jsonify({
                    'success': False,
                    'error': 'Invalid file format. Please upload CSV or Excel (.xlsx) file'
                }), 400
        
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Error reading file: {str(e)}'
            }), 400
        
        # ================================================================
        # STEP 5: Validate Data Structure
        # ================================================================
        if 'Location' not in df.columns:
            return jsonify({
                'success': False,
                'error': f'File must contain a "Location" column. Found columns: {", ".join(df.columns.tolist())}'
            }), 400
        
        # ================================================================
        # STEP 6: Clean and Validate Location Data
        # ================================================================
        # Remove rows with empty locations
        df = df.dropna(subset=['Location'])
        
        # Convert to string and strip whitespace
        df['Location'] = df['Location'].astype(str).str.strip()
        
        # Remove empty strings
        df = df[df['Location'] != '']
        
        # Debug: Print locations being processed
        print("\n" + "="*70)
        print("LOCATIONS FROM FILE:")
        print("="*70)
        for idx, loc in enumerate(df['Location'].tolist(), 1):
            print(f"{idx}. {loc}")
        print("="*70 + "\n")
        
        if df.empty:
            return jsonify({
                'success': False,
                'error': 'No valid locations found in the file. Please check your data.'
            }), 400
        
        # Limit to 50 locations for performance
        if len(df) > 50:
            return jsonify({
                'success': False,
                'error': f'Too many locations ({len(df)}). Maximum supported is 50. Please reduce your locations.'
            }), 400
        
        print(f"Processing {len(df)} delivery locations...")
        
        # ================================================================
        # STEP 7: Geocode All Addresses
        # ================================================================
        optimizer = RouteOptimizer(ORS_API_KEY)
        
        # Store original locations before geocoding
        original_locations = df['Location'].tolist()
        
        # Create list: [start, location1, location2, ..., locationN, end]
        all_addresses = [start_location] + original_locations + [end_location]
        
        print(f"Geocoding {len(all_addresses)} addresses...")
        
        # Geocode all addresses in parallel
        all_coords = optimizer.batch_geocode(all_addresses)
        
        # Extract coordinates
        start_coord = all_coords[0]
        end_coord = all_coords[-1]
        delivery_coords = all_coords[1:-1]
        
        # Create a new dataframe to preserve original location names
        df_with_coords = pd.DataFrame({
            'Location': original_locations,
            'Coordinates': delivery_coords
        })
        
        # ================================================================
        # STEP 8: Validate Geocoding Results
        # ================================================================
        if not start_coord:
            return jsonify({
                'success': False,
                'error': f'Could not locate start address: "{start_location}". Please enter a more specific address.'
            }), 400
        
        if not end_coord:
            return jsonify({
                'success': False,
                'error': f'Could not locate end address: "{end_location}". Please enter a more specific address.'
            }), 400
        
        # Identify failed geocoding attempts
        failed_locations = df_with_coords[df_with_coords['Coordinates'].isna()]['Location'].tolist()
        
        # Filter out failed locations - KEEP ORIGINAL NAMES
        df_clean = df_with_coords.dropna(subset=['Coordinates']).reset_index(drop=True)
        
        if df_clean.empty:
            return jsonify({
                'success': False,
                'error': 'All delivery locations failed to geocode. Please check your addresses.'
            }), 400
        
        success_count = len(df_clean)
        total_count = len(df_with_coords)
        
        print(f"Geocoding complete: {success_count}/{total_count} successful")
        
        if failed_locations:
            print(f"Failed locations: {failed_locations}")
        
        # ================================================================
        # STEP 9: Calculate Optimal Route
        # ================================================================
        # Build coordinate list: [start, stop1, stop2, ..., stopN, end]
        route_coordinates = [start_coord] + df_clean['Coordinates'].tolist() + [end_coord]
        
        print(f"Calculating route through {len(route_coordinates)} points...")
        
        route_result = optimizer.calculate_route(route_coordinates)
        
        if not route_result:
            return jsonify({
                'success': False,
                'error': 'Failed to calculate route. Please try again or check your locations.'
            }), 500
        
        print(f"Route calculated: {route_result['distance_km']} km, {route_result['duration_min']} min")
        
        # ================================================================
        # STEP 10: Build Response with Stop Sequence
        # ================================================================
        stops = []
        
        # Calculate time increments based on actual route segments
        # Distribute time proportionally across stops
        total_duration = route_result['duration_min']
        num_segments = len(df_clean) + 1  # Number of road segments
        
        cumulative_time = 0
        
        print("\n" + "="*70)
        print("BUILDING STOP SEQUENCE:")
        print("="*70)
        
        for idx, row in df_clean.iterrows():
            # Calculate estimated time to reach this stop
            # Time increases proportionally through the route
            cumulative_time = total_duration * (idx + 1) / num_segments
            
            location_name = str(row['Location'])
            
            print(f"Stop {idx + 1}: {location_name} - ETA: {round(cumulative_time, 0)} min")
            
            stops.append({
                'order': idx + 1,
                'location': location_name,  # Ensure string type
                'coordinates': {
                    'lat': float(row['Coordinates'][1]),
                    'lng': float(row['Coordinates'][0])
                },
                'estimated_time_min': int(round(cumulative_time, 0))
            })
        
        print("="*70 + "\n")
        
        # ================================================================
        # STEP 11: Format Final Response
        # ================================================================
        response_data = {
            'success': True,
            'route': {
                'geometry': route_result['geometry'],
                'bbox': route_result['bbox'],
                'distance_km': route_result['distance_km'],
                'distance_mi': route_result['distance_mi'],
                'duration_min': route_result['duration_min'],
                'duration_hours': route_result['duration_hours']
            },
            'start': {
                'location': start_location,
                'coordinates': {
                    'lat': start_coord[1],
                    'lng': start_coord[0]
                }
            },
            'end': {
                'location': end_location,
                'coordinates': {
                    'lat': end_coord[1],
                    'lng': end_coord[0]
                }
            },
            'stops': stops,
            'total_stops': len(stops),
            'failed_locations': failed_locations,
            'success_rate': f"{success_count}/{total_count}"
        }
        
        return jsonify(response_data), 200
    
    except Exception as e:
        print(f"Server error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            'success': False,
            'error': f'Server error: {str(e)}'
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Health check endpoint to verify:
    1. Server is running
    2. API key is configured
    """
    api_configured = ORS_API_KEY != "YOUR_API_KEY_HERE" and bool(ORS_API_KEY)
    
    return jsonify({
        'status': 'ok',
        'api_configured': api_configured,
        'message': 'API key configured' if api_configured else 'Please configure API key in app.py'
    }), 200

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================
if __name__ == '__main__':
    print("=" * 70)
    print("🚀 SmartRoute Optimizer Server Starting...")
    print("=" * 70)
    print(f"📍 Server URL: http://localhost:5000")
    print(f"📍 Health Check: http://localhost:5000/api/health")
    print()
    
    if ORS_API_KEY == "YOUR_API_KEY_HERE":
        print("⚠️  WARNING: API Key not configured!")
        print("   Get your free key at: https://openrouteservice.org/dev/#/signup")
        print("   Then replace 'YOUR_API_KEY_HERE' in app.py")
    else:
        print("✅ API Key configured")
    
    print()
    print("=" * 70)
    print()
    
    app.run(debug=True, host='0.0.0.0', port=5000)