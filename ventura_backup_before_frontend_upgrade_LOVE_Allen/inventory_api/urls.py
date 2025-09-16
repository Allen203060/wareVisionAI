from django.urls import path
from .views import *

urlpatterns = [
    
    path('products/', ProductListAPIView.as_view(), name='product-list'),
    # New URL for triggering the reasoning process
    path('query/', ProposeActionAPIView.as_view(), name='propose-action'),
    path('execute-action/', ExecuteActionAPIView.as_view(), name='execute-action'),
]