from django.contrib import admin
from django.urls import path, include
from inventory_api.views import *   

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('inventory_api.urls')), 
    path('', index, name='index'),
    path('api/v1/', include('inventory_api.urls')),
]