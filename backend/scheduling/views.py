from rest_framework.response import Response
from rest_framework.views import APIView

from config.permissions import IsManager

from . import services


class LoadView(APIView):
    permission_classes = [IsManager]

    def get(self, request):
        return Response(services.equipment_load())
