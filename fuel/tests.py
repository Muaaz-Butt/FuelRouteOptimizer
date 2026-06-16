from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from fuel.models import Truckstop, FuelPrice
from fuel.services.optimizer import optimize_route


class OptimizerServiceTests(TestCase):
	def setUp(self):
		# create a couple of truckstops with coordinates and prices
		self.ts1 = Truckstop.objects.create(
			opis_truckstop_id=1,
			canonical_name='Stop A',
			address='1 Main St',
			city='City',
			state='ST',
			latitude=40.0,
			longitude=-75.0,
		)
		self.ts2 = Truckstop.objects.create(
			opis_truckstop_id=2,
			canonical_name='Stop B',
			address='2 Main St',
			city='City',
			state='ST',
			latitude=40.1,
			longitude=-75.1,
		)
		FuelPrice.objects.create(truckstop=self.ts1, rack_id=1, retail_price=1.20, source_row_hash='h1')
		FuelPrice.objects.create(truckstop=self.ts2, rack_id=2, retail_price=1.10, source_row_hash='h2')

	def test_optimize_route_returns_suggestions(self):
		origin = (39.9, -74.9)
		destination = (40.2, -75.2)
		result = optimize_route(origin, destination, mpg=10.0, tank_range_miles=500.0, max_results=2)
		self.assertIn('suggested_stops', result)
		self.assertTrue(isinstance(result['suggested_stops'], list))


class OptimizeAPITests(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.ts = Truckstop.objects.create(
			opis_truckstop_id=3,
			canonical_name='Stop C',
			address='3 Main St',
			city='City',
			state='ST',
			latitude=41.0,
			longitude=-76.0,
		)
		FuelPrice.objects.create(truckstop=self.ts, rack_id=3, retail_price=1.50, source_row_hash='h3')

	def test_api_optimize_post(self):
		url = reverse('optimize-route')
		payload = {
			'origin': {'latitude': 40.0, 'longitude': -75.0},
			'destination': {'latitude': 41.0, 'longitude': -76.0},
			'mpg': 10.0,
			'tank_range_miles': 500.0,
			'max_results': 1,
		}
		resp = self.client.post(url, payload, format='json')
		self.assertEqual(resp.status_code, 200)
		self.assertIn('suggested_stops', resp.json())
