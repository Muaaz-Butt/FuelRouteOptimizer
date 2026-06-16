from django.urls import path
from . import api_views

urlpatterns = [
    path('optimize/', api_views.OptimizeRouteAPIView.as_view(), name='optimize-route'),
]
