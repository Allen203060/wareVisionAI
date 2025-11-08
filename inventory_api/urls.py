from django.urls import path
from .views import *

urlpatterns = [
    
    # URLs for manual CRUD operations
    path('products/', ProductListCreateAPIView.as_view(), name='product-list-create'),
    path('products/<int:pk>/', ProductDetailAPIView.as_view(), name='product-detail'),

    # URLs for the LLM-driven actions
    path('query/', ProposeActionAPIView.as_view(), name='propose-action'),
    path('execute-action/', ExecuteActionAPIView.as_view(), name='execute-action'),
    path('product/receive/', ReceiveProductDataView.as_view(), name='receive_product_data'),
    path('product/check-scanned/', CheckScannedProductView.as_view(), name='check-scanned-product'),
    
]