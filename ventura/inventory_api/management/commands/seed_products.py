import json
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from inventory_api.models import Product

class Command(BaseCommand):
    help = 'Seeds the database with initial product data.'

    def handle(self, *args, **kwargs):
        # Clear existing data to avoid duplicates
        Product.objects.all().delete()
        self.stdout.write(self.style.WARNING('Existing products deleted.'))

        # Use a dynamic date for "today"
        today = date.today()

        # This is the dummy data from your project plan.
        products_data = [
            {"product_name": "Organic Milk", "price": 4.99, "expiry_date": (today + timedelta(days=45)).strftime('%Y-%m-%d')},
            {"product_name": "Cheddar Cheese", "price": 6.50, "expiry_date": (today + timedelta(days=60)).strftime('%Y-%m-%d')},
            {"product_name": "Whole Wheat Bread", "price": 3.25, "expiry_date": (today + timedelta(days=5)).strftime('%Y-%m-%d')},
            {"product_name": "Greek Yogurt", "price": 1.75, "expiry_date": (today + timedelta(days=25)).strftime('%Y-%m-%d')},
            {"product_name": "Free-Range Eggs", "price": 5.00, "expiry_date": (today + timedelta(days=28)).strftime('%Y-%m-%d')},
            {"product_name": "Apple Juice", "price": 3.99, "expiry_date": (today + timedelta(days=180)).strftime('%Y-%m-%d')},
            {"product_name": "Baby Spinach", "price": 2.99, "expiry_date": (today + timedelta(days=8)).strftime('%Y-%m-%d')},
            {"product_name": "Chicken Breast", "price": 12.50, "expiry_date": (today + timedelta(days=3)).strftime('%Y-%m-%d')},
            {"product_name": "Avocado", "price": 2.10, "expiry_date": (today + timedelta(days=6)).strftime('%Y-%m-%d')},
            {"product_name": "Sourdough Loaf", "price": 5.50, "expiry_date": (today - timedelta(days=2)).strftime('%Y-%m-%d')},
            {"product_name": "Hummus", "price": 4.20, "expiry_date": (today + timedelta(days=15)).strftime('%Y-%m-%d')},
            {"product_name": "Almond Milk", "price": 3.50, "expiry_date": (today + timedelta(days=50)).strftime('%Y-%m-%d')},
            {"product_name": "Salmon Fillet", "price": 15.00, "expiry_date": (today + timedelta(days=1)).strftime('%Y-%m-%d')},
            {"product_name": "Craft Beer 6-Pack", "price": 14.99, "expiry_date": (today + timedelta(days=90)).strftime('%Y-%m-%d')},
            {"product_name": "Bag of Oranges", "price": 7.00, "expiry_date": (today + timedelta(days=12)).strftime('%Y-%m-%d')},
            {"product_name": "Imported Olives", "price": 8.50, "expiry_date": (today - timedelta(days=30)).strftime('%Y-%m-%d')},
            {"product_name": "Artisanal Salami", "price": 11.25, "expiry_date": (today + timedelta(days=40)).strftime('%Y-%m-%d')},
            {"product_name": "Kombucha", "price": 4.75, "expiry_date": (today + timedelta(days=20)).strftime('%Y-%m-%d')},
            {"product_name": "Fresh Pasta", "price": 6.00, "expiry_date": today.strftime('%Y-%m-%d')},
            {"product_name": "Premium Coffee Beans", "price": 18.00, "expiry_date": (today + timedelta(days=365)).strftime('%Y-%m-%d')}
        ]

        for product_data in products_data:
            Product.objects.create(**product_data)

        self.stdout.write(self.style.SUCCESS(f'{len(products_data)} products have been added to the database.'))

