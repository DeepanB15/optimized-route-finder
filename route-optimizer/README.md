# SmartRoute Optimizer

An interactive Python Flask web app for optimizing multi-stop driving routes using OpenRouteService.

## Project Overview

`SmartRoute Optimizer` helps delivery planners, drivers, and route coordinators turn a list of addresses into a single optimized route. The app loads a CSV or Excel file containing delivery locations, geocodes each address, and then calculates the best driving route from a start location to an end location.

## Key Features

- Web-based user interface with route preview
- Upload CSV or Excel files with a `Location` column
- Support for start and end address input
- Batch geocoding of addresses using OpenRouteService
- Route distance and duration metrics
- Interactive map display using Leaflet
- Stop sequence summary and estimated time per stop
- Health check endpoint for server status

## Repository Structure

- `deliveries.csv` - sample delivery file with a `Location` column
- `route-optimizer/` - main Flask application folder
  - `app.py` - server logic, geocoding, route calculation, and API endpoints
  - `templates/index.html` - front-end UI for uploading files and displaying routes
  - `uploads/` - upload destination for file processing
  - `requirements.txt` - dependency list (currently empty; install dependencies manually as shown below)

## Requirements

- Python 3.9+ recommended
- `Flask`
- `requests`
- `pandas`

Optional dependencies are provided by Flask itself for file upload and request handling.

## Setup

1. Clone or copy the repository.
2. Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Install required packages:

```powershell
pip install flask requests pandas
```

## Configure OpenRouteService API Key

The app uses the OpenRouteService API for geocoding and routing. You must add your own API key in `route-optimizer/app.py`.

1. Sign up at: https://openrouteservice.org/dev/#/signup
2. Open `route-optimizer/app.py`
3. Replace the value of `ORS_API_KEY` with your API key.

```python
ORS_API_KEY = "YOUR_OPENROUTESERVICE_API_KEY"
```

## Run the App

From the project root folder, start the server:

```powershell
cd route-optimizer
python app.py
```

Then open your browser at:

- `http://localhost:5000`

## Usage

1. Enter a start location.
2. Enter an end location.
3. Upload a file in CSV or Excel format.
4. Click `Optimize Route`.
5. View the optimized route, distance, duration, and stop sequence.

## File Format

The uploaded file must contain a `Location` column. Example CSV:

```csv
Location
Koyambedu Market, Chennai
Vadapalani Bus Stand, Chennai
Anna Nagar West Extension, Chennai
T Nagar Shopping Area, Chennai
Adyar Signal, Chennai
```

Supported formats:

- `.csv`
- `.xlsx`
- `.xls`

## API Endpoints

- `GET /` - Main application page
- `POST /api/optimize` - Upload the route file and request optimization
- `GET /api/health` - Health check and API key status

## Notes

- The app limits input to 50 delivery locations to preserve performance.
- If any address cannot be geocoded, it is omitted from route calculation and reported in the response.
- The app uses client-side Leaflet map rendering in `route-optimizer/templates/index.html`.

## Troubleshooting

- If the app fails with an API key error, verify the key and check your OpenRouteService account limits.
- For upload issues, ensure the file includes a `Location` column and is a supported format.
- If the route does not appear, open the browser console to see front-end errors.

## Future Improvements

- Add a `requirements.txt` file with pinned dependency versions
- Improve stop ordering using a true route optimization or TSP solver
- Add support for waypoint reordering and finer route control
- Store uploaded files with timestamps and cleanup old files
- Add testing and validation for the front-end form
