from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from fuel.serializers import OptimizeRequestSerializer, OptimizeResponseSerializer
from fuel.services.optimizer import optimize_route


class OptimizeRouteAPIView(APIView):
    def post(self, request):
        serializer = OptimizeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        origin = (data['origin']['latitude'], data['origin']['longitude'])
        destination = (data['destination']['latitude'], data['destination']['longitude'])
        # use defaults: mpg=10, tank_range_miles=500 unless provided
        mpg = data.get('mpg', 10.0)
        tank_range_miles = data.get('tank_range_miles', 500.0)

        payload = optimize_route(
            origin=origin,
            destination=destination,
            mpg=mpg,
            tank_range_miles=tank_range_miles,
            max_results=data.get('max_results', 5),
        )

        out_serializer = OptimizeResponseSerializer(payload)
        return Response(out_serializer.data, status=status.HTTP_200_OK)
