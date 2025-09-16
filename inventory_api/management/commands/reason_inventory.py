import json
from django.core.management.base import BaseCommand
from inventory_api.models import Product
from inventory_api.mcp import get_llm_reasoning

class Command(BaseCommand):
    help = 'Applies reasoning from a local LLM to the inventory.'

    def handle(self, *args, **kwargs):
        self.stdout.write("Fetching inventory data for LLM reasoning...")
        
        # 1. Fetch all products from the database
        products = Product.objects.all()
        
        # 2. Serialize the data into a simple list of dicts
        inventory_data = list(products.values('id', 'product_name', 'price', 'expiry_date'))
        
        # Convert date objects to strings for JSON serialization
        for item in inventory_data:
            item['expiry_date'] = item['expiry_date'].isoformat()
            item['price'] = float(item['price'])

        inventory_json = json.dumps(inventory_data, indent=2)
        
        # Construct the specific prompt for this command
        prompt = f"""
        You are an inventory management assistant. Based on the following JSON data of products,
        identify the single product that is closest to its expiration date but not yet expired.
        
        Your task is to return a single, clean JSON object with two keys:
        1. "product_id": The ID of the product you have identified.
        2. "action": A string suggesting an action. For the identified product, the action should be "MARK_FOR_DISCOUNT".

        Do not provide any explanation or introductory text, only the JSON object.

        Inventory Data:
        {inventory_json}
        """

        self.stdout.write("Sending data to local LLM...")
        
        # 3. Get the reasoned action from the MCP
        reasoned_action = get_llm_reasoning(prompt) # Pass the constructed prompt

        if not reasoned_action or "error" in reasoned_action:
            self.stderr.write(f"Failed to get reasoning: {reasoned_action.get('error', 'Unknown error')}")
            return

        # 4. Apply the action
        product_id = reasoned_action.get('product_id')
        action = reasoned_action.get('action')

        if action == "MARK_FOR_DISCOUNT" and product_id is not None:
            try:
                product_to_update = Product.objects.get(id=product_id)
                
                # Avoid adding the tag multiple times
                if "[DISCOUNT]" not in product_to_update.product_name:
                    product_to_update.product_name = f"{product_to_update.product_name} [DISCOUNT]"
                    product_to_update.save()
                    self.stdout.write(self.style.SUCCESS(
                        f"Successfully applied discount to product ID {product_id}: {product_to_update.product_name}"
                    ))
                else:
                    self.stdout.write(self.style.WARNING(
                        f"Product ID {product_id} is already marked for discount."
                    ))

            except Product.DoesNotExist:
                self.stderr.write(f"Product with ID {product_id} not found.")
        else:
            self.stdout.write("No specific action was recommended by the model.")