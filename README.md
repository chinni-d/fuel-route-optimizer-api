# Fuel Route Optimizer API

A production-ready Django REST API built to optimize routing and fuel costs for long-haul journeys across the USA. This API determines the most cost-effective fuel stops along a driven route based on fuel capacity, vehicle mileage, and real-time geospatial calculations.

---

## 🎯 Core Features & Logic
- **Intelligent Route Geocoding:** Uses a fast, in-memory US Cities database (`us_cities.csv`) to resolve start/end points instantly without hitting external rate limits.
- **Optimized Routing:** Integrates with the public OSRM (Open Source Routing Machine) API, utilizing precisely **one external API call** per request. Responses are aggressively cached in memory.
- **Smart Fuel Segmentation:** Calculates exact segments using cumulative path distances. Assumes:
  - **Vehicle Range:** 500 miles max per tank
  - **Fuel Efficiency:** 10 mpg
  - **Tank Capacity:** 50 gallons
- **Cost Minimization Algorithm:** Leverages `scipy.spatial.cKDTree` to rapidly perform radius searches along the polyline. Automatically identifies and selects the absolutely cheapest gas station within a safe, reachable window.
- **Mathematical Accuracy:** Computes the total required fuel (`Total Distance / 10`) and ensures zero double-counting, accurately distributing costs over each segment of the journey.
- **Compressed Output:** Down-samples the raw thousands of map coordinates into a lightweight, client-friendly array to drastically reduce API response size.

---

## 🌍 Live Deployment
This API is actively deployed and available at:
**`https://api.manikantadarapureddy.in/api/route-optimize/`**

---

## 🚀 Local Setup Instructions

### 1. Clone the Repository
```bash
git clone https://github.com/chinni-d/fuel-route-optimizer-api.git
cd fuel-route-optimizer-api
```

### 2. Install Dependencies
Ensure you have Python 3.9+ installed. Install the necessary packages via pip:
```bash
pip install -r requirements.txt
```
*(This installs Django, Django REST Framework, pandas, numpy, scipy, and requests)*

### 3. Start the Server
Since this app relies on in-memory operations and CSV databases, no external SQL migrations are required for the core logic. Just run the server:
```bash
python manage.py runserver
```
The API will be available at `http://127.0.0.1:8000`.

---

## 💡 Usage & Testing

### API Endpoint
`POST /api/route-optimize/`

### Input Payload
Send a JSON payload with `start` and `end` locations. Format must be `"City, ST"`.

**Example Request (Postman or cURL):**
```bash
curl -X POST http://127.0.0.1:8000/api/route-optimize/ \
-H "Content-Type: application/json" \
-d '{"start": "New York, NY", "end": "Los Angeles, CA"}'
```

### Expected Output
The system mathematically traverses the 2,800-mile journey, making exactly 6 optimal stops, outputting the cheapest pitstops along the actual path.

```json
{
    "distance_miles": 2800.63,
    "fuel_stops": [
        {
            "city": "Youngstown",
            "state": "OH",
            "price_per_gallon": 3.059
        },
        {
            "city": "Peru",
            "state": "IL",
            "price_per_gallon": 2.969
        },
        {
            "city": "Waco",
            "state": "NE",
            "price_per_gallon": 2.799
        },
        {
            "city": "Longmont",
            "state": "CO",
            "price_per_gallon": 3.057
        },
        {
            "city": "Green River",
            "state": "UT",
            "price_per_gallon": 3.282
        },
        {
            "city": "North Las Vegas",
            "state": "NV",
            "price_per_gallon": 3.282
        }
    ],
    "total_cost": 863.42,
    "route_polyline": [
        [-73.99, 40.73],
        [-74.20, 40.85],
        "... (sampled array for lightweight rendering)"
    ]
}
```
