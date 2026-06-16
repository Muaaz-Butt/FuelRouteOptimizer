from rest_framework import serializers


class CoordinateSerializer(serializers.Serializer):
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()


class OptimizeRequestSerializer(serializers.Serializer):
    origin = CoordinateSerializer()
    destination = CoordinateSerializer()
    # optional vehicle params (defaults: mpg=10, tank_range_miles=500)
    mpg = serializers.FloatField(min_value=1.0, default=10.0, required=False)
    tank_range_miles = serializers.FloatField(min_value=1.0, default=500.0, required=False)
    max_results = serializers.IntegerField(min_value=1, max_value=20, default=5)


class StopEstimateSerializer(serializers.Serializer):
    opis_truckstop_id = serializers.IntegerField()
    canonical_name = serializers.CharField()
    address = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    retail_price = serializers.FloatField()
    added_distance_km = serializers.FloatField()
    estimated_cost = serializers.FloatField()


class OptimizeResponseSerializer(serializers.Serializer):
    origin = CoordinateSerializer()
    destination = CoordinateSerializer()
    route_polyline = serializers.CharField(allow_null=True, required=False)
    distance_miles = serializers.FloatField()
    suggested_stops = StopEstimateSerializer(many=True)
    total_money_spent = serializers.FloatField()
