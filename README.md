# FuelRouteOptimizer
Django REST API that finds optimal fuel stops and fuel costs on US road trips.

Getting started
---------------

Install dependencies:

```bash
pip install -r requirements.txt
```

Run migrations and tests:

```bash
python manage.py migrate
python manage.py test
```

Run development server:

```bash
python manage.py runserver
```

API docs:

- OpenAPI schema: `/api/schema/`
- Swagger UI: `/api/docs/swagger/`
- Redoc: `/api/docs/redoc/`

Postman example
---------------

POST `/api/optimize/` body (JSON):

```json
{
	"origin": {"latitude": 40.7128, "longitude": -74.0060},
	"destination": {"latitude": 34.0522, "longitude": -118.2437},
	"mpg": 10.0,
	"tank_range_miles": 500.0,
	"max_results": 5
}
```

The response will include `route_polyline`, `distance_miles`, `suggested_stops`, and `total_money_spent`.

Docker
------

Build and run with docker-compose:

```bash
docker-compose up --build
```

