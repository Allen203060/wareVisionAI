from rest_framework import serializers
from .models import Product

class ProductSerializer(serializers.ModelSerializer):
    """
    Serializer for the Product model. Converts Product model instances to JSON.
    """
    class Meta:
        model = Product
        fields = ['id', 'product_name', 'price', 'expiry_date']