import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import RouteOptimizeRequestSerializer
from services.routing_service import get_optimized_route_and_fuel

logger = logging.getLogger(__name__)

class RouteOptimizeView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = RouteOptimizeRequestSerializer(data=request.data)
        if serializer.is_valid():
            start_location = serializer.validated_data['start']
            end_location = serializer.validated_data['end']
            
            try:
                result = get_optimized_route_and_fuel(start_location, end_location)
                return Response(result, status=status.HTTP_200_OK)
            except Exception as e:
                logger.exception("Error optimizing route")
                return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
