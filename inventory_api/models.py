from django.db import models


class Product(models.Model):
    """
    Represents a product in the inventory.
    """
    product_name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.IntegerField(default=1) 
    expiry_date = models.DateField()

    def __str__(self):
        return self.product_name

    class Meta:
        ordering = ['expiry_date'] 
