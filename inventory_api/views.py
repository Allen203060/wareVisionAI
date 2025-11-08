from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import JSONParser
from django.shortcuts import render
from .models import Product
from .serializers import ProductSerializer
from .mcp import get_llm_reasoning
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from datetime import date, timedelta
from queue import Queue
from rest_framework.permissions import AllowAny

scanned_product_queue = Queue()

def index(request):
    return render(request, 'index.html')

class ProductListCreateAPIView(generics.ListCreateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

class ProductDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

class ProposeActionAPIView(APIView):
    parser_classes = [JSONParser]


    def _normalize_llm_response(self, llm_response):
        if not isinstance(llm_response, dict):
            return {}

        action = llm_response.get('action', '').upper()

        if action in ["ADD", "CREATE"]:
            llm_response['action'] = 'CREATE'
            product_data = {}
            # NEW: Check for the nested 'data' object first
            if isinstance(llm_response.get('data'), dict):
                nested_data = llm_response.get('data')
                product_name = nested_data.get('product_name') or nested_data.get('name') or nested_data.get('item_name')
                product_data['product_name'] = product_name
                product_data['price'] = nested_data.get('price')
                product_data['quantity'] = nested_data.get('quantity', 1) 
                
                # --- DATETIME LOGIC (FOR NESTED) ---
                expiry_date = nested_data.get('expiry_date')
                relative_expiry = nested_data.get('relative_expiry')
                if relative_expiry and isinstance(relative_expiry, dict):
                    try:
                        today = date.today()
                        # --- MODIFICATION ---
                        # Simplified to only use 'days'
                        days_to_add = int(relative_expiry.get('days', 0))
                        final_date = today + timedelta(days=days_to_add)
                        # --- END MODIFICATION ---
                        product_data['expiry_date'] = final_date.isoformat()
                    except:
                        product_data['expiry_date'] = None
                else:
                    product_data['expiry_date'] = expiry_date
                # --- END DATETIME LOGIC ---
            
            # FALLBACK: Logic for flat responses (YOUR MODEL USES THIS)
            else:
                product_name = llm_response.pop('product_name', None) or llm_response.pop('item_name', None)
                product_data['product_name'] = product_name
                product_data['price'] = llm_response.pop('price', None)
                product_data['quantity'] = llm_response.pop('quantity', 1)

                # --- DATETIME LOGIC (FOR FLAT) ---
                expiry_date = llm_response.pop('expiry_date', None)
                relative_expiry = llm_response.pop('relative_expiry', None) 

                if relative_expiry and isinstance(relative_expiry, dict):
                    try:
                        today = date.today()
                        # --- MODIFICATION ---
                        # Simplified to only use 'days'
                        days_to_add = int(relative_expiry.get('days', 0))
                        final_date = today + timedelta(days=days_to_add)
                        # --- END MODIFICATION ---
                        product_data['expiry_date'] = final_date.isoformat()
                    except Exception as e:
                        print(f"Error calculating relative date: {e}")
                        product_data['expiry_date'] = None
                else:
                    product_data['expiry_date'] = expiry_date
                # --- END DATETIME LOGIC ---

            llm_response['data'] = product_data
            llm_response['product_id'] = None
            # Clean up top-level keys
            allowed_keys = ['action', 'product_id', 'data']
            for key in list(llm_response.keys()):
                if key not in allowed_keys:
                    del llm_response[key]

        # --- Handle relative_expiry for UPDATE ---
        elif action == "UPDATE":
            data = llm_response.get('data', {})
            relative_expiry = data.get('relative_expiry')
            if relative_expiry and isinstance(relative_expiry, dict):
                try:
                    today = date.today()
                    # --- MODIFICATION ---
                    # Simplified to only use 'days'
                    days_to_add = int(relative_expiry.get('days', 0))
                    final_date = today + timedelta(days=days_to_add)
                    # --- END MODIFICATION ---
                    data['expiry_date'] = final_date.isoformat()
                    del data['relative_expiry']
                except:
                    data['expiry_date'] = None
            llm_response['data'] = data
        # --- END FIX ---

        return llm_response

    def post(self, request, *args, **kwargs):
        user_query = request.data.get('query')
        if not user_query:
            return Response({"error": "Query not provided"}, status=status.HTTP_400_BAD_REQUEST)

        products = Product.objects.all()
        inventory_data = list(products.values('id', 'product_name', 'price', 'quantity', 'expiry_date'))
        for item in inventory_data:
            item['expiry_date'] = item['expiry_date'].isoformat()
            item['price'] = float(item['price'])
        inventory_json = json.dumps(inventory_data, indent=2)
        
        today = date.today()
        today_date_str = today.isoformat()
        
        one_week_from_today = (today + timedelta(days=7)).isoformat()
        inventory_json = json.dumps(inventory_data, separators=(',', ':'))
        
        # --- START PROMPT MODIFICATION ---
        prompt = f"""
            You are a highly-strict inventory management bot. Your ONLY task is to convert a user's request into a single, clean JSON object.

            The current date is {today_date_str}.
            
            The current inventory data is: {inventory_json}

            ---
            CRITICAL RULES:
            1.  You MUST respond with a single, valid JSON object.
            2.  NEVER output any text, explanation, or conversational filler before or after the JSON.
            3.  NEVER include comments (like `//`) or any code (like `new Date()`) inside the JSON.
            4.  NEVER invent, assume, or hallucinate information that is not in the user's request.
            5.  If information required for an `ADD` or `UPDATE` action is missing (e.g., quantity, price), you MUST use the `QUERY_RESPONSE` action to ask a clarifying question.
            
       
            6.  DATE CALCULATION: If a relative date is given (e.g., "in 3 days", "in 2 weeks", "in 3 months"), YOU MUST convert it to a total number of days. Use **1 week = 7 days** and **1 month = 30 days**. Output this in a `relative_expiry` object using the "days" key.
          
            
            7.  ABSOLUTE DATES: If a specific date is given (e.g., "Oct 5, 2025"), use the `expiry_date` field.
            8.  NEVER use `expiry_date` and `relative_expiry` in the same response.
            
            ---
            RESPONSE FORMATS (Use ONLY one of these five):  

            1. For answering a question OR asking for clarification:
            {{"action": "QUERY_RESPONSE",
              "answer": "Your natural language answer or clarifying question."
            }}

            2. For creating a new product:
            (Use "expiry_date" for specific dates, or "relative_expiry" for relative dates. NEVER use both.)
            {{"action": "ADD",
              "item_name": "Product Name",
              "quantity": 1,
              "price": 0.00,
              "expiry_date": "YYYY-MM-DD"
            }}
            
            3. For updating an existing product (Refer to inventory data for product_id):
            {{"action": "UPDATE",
              "product_id": 123,
              "data": {{
                "field_to_update": "new_value"
              }}
            }}

            4. For deleting an existing product (Refer to inventory data for product_id):
            {{"action": "DELETE",
              "product_id": 123
            }}
            
            5. For deleting ALL expired products at once:
            {{"action": "BULK_DELETE_EXPIRED"}}

            ---
            EXAMPLES (Based on your training data):

            User Query: "Add a new product: 50 units of Atta Bread at ₹360 each, expiring Oct 5, 2025."
            Your JSON Response:
            {{"action": "ADD",
              "item_name": "Atta Bread",
              "quantity": 50,
              "price": 360,
              "expiry_date": "2025-10-05"
            }}
            
         
            User Query: "add 5 loaves of sourdough bread at 8.99 each, expiring in 2 weeks"
            Your JSON Response:
            {{"action": "ADD",
              "item_name": "sourdough bread",
              "quantity": 5,
              "price": 8.99,
              "relative_expiry": {{"days": 14}}
            }}
         

            User Query: "add 10 units of bubbly chocolate 50rs expiring in 3 months"
            Your JSON Response:
            {{"action": "ADD",
              "item_name": "bubbly chocolate",
              "quantity": 10,
              "price": 50,
              "relative_expiry": {{"days": 90}}
            }}

            User Query: "add brown bread price is 30rs, expiry is in 3 days"
            Your JSON Response:
            {{"action": "QUERY_RESPONSE",
              "answer": "I can add 'brown bread' (at 30rs, expiring in 3 days), but what is the quantity?"
            }}

            User Query: "Change the price of the Desi Eggs to ₹420"
            Your JSON Response:
            {{"action": "UPDATE",
              "product_id": 5,
              "data": {{
                "price": 420
              }}
            }}

            User Query: "Please remove the sourdough bread from the system."
            Your JSON Response:
            {{"action": "DELETE",
              "product_id": 3
            }}

            User Query: "Delete all expired items."
            Your JSON Response:
            {{"action": "BULK_DELETE_EXPIRED"}}
            
            User Query: "How many Kashmiri Apples are left in the inventory?"
            Your JSON Response:
            {{"action": "QUERY_RESPONSE",
              "answer": "There are 140 units of Kashmiri Apples left in the inventory."
            }}
            
            User Query: "Add new Lemon Dishwash Liquid, costs ₹320."
            Your JSON Response:
            {{"action": "QUERY_RESPONSE",
              "answer": "I can add that product, but what is the quantity?"
            }}
            ---
           _
            Now, process the following user request. Follow the rules and output formats precisely.

            The user's query is: "{user_query}"
            """
        # --- END PROMPT MODIFICATION ---

        llm_response = get_llm_reasoning(prompt)
        llm_response = self._normalize_llm_response(llm_response) # <-- Your existing line

        if not llm_response or "error" in llm_response:
            return Response(llm_response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            action = llm_response.get('action')

            if not action:
                return Response({"error": "Model did not propose a valid action."}, status=status.HTTP_400_BAD_REQUEST)

            if action == "CREATE":
                product_data = llm_response.get('data', {})
                
                # --- START NEW FIX 2 ---
                name = product_data.get('product_name')
                price = product_data.get('price')
                quantity = product_data.get('quantity')
                expiry = product_data.get('expiry_date') # This will be the CALCULATED date

                missing = []
                if not name: missing.append("product name")
                if not price: missing.append("price")
                if not quantity or quantity == 0: missing.append("quantity")
                if not expiry: missing.append("expiry date") 

                if missing:
                    got_parts = []
                    if name: got_parts.append(f"'{name}'")
                    if price: got_parts.append(f"at ₹{price}")
                    if quantity: got_parts.append(f"({quantity} units)")

                    got_str = " ".join(got_parts) if got_parts else "the product"
                    missing_str = " and ".join(missing)
                    
                    answer = f"I can add {got_str}, but I'm missing the {missing_str}. Could you please provide it?"
                    
                    if missing == ['expiry date']:
                          answer = f"I can add {got_str}, but I need the exact expiry date. Please provide it in YYYY-MM-DD format."
                    
                    final_response = {
                        "action": "QUERY_RESPONSE",
                        "answer": answer
                    }
                    return Response(final_response, status=status.HTTP_200_OK)
                # --- END NEW FIX 2 ---

                llm_response['description'] = f"Create new product '{name}' (Quantity: {quantity}) with price ₹{price} and expiry date {expiry}."
            
            elif action == "BULK_DELETE_EXPIRED":
                expired_products = Product.objects.filter(expiry_date__lt=date.today())
                product_count = expired_products.count()
                
                if product_count == 0:
                    llm_response = {
                        "action": "QUERY_RESPONSE",
                        "answer": "There are no expired products to delete."
                    }
                else:
                    product_ids_to_delete = list(expired_products.values_list('id', flat=True))
                    product_names = ", ".join([f"'{p.product_name}'" for p in expired_products])
                    llm_response['description'] = f"Are you sure you want to permanently delete {product_count} expired product(s): {product_names}?"
                    llm_response['data'] = {'ids_to_delete': product_ids_to_delete}

            elif action in ["UPDATE", "DELETE"]:
                product_id = llm_response.get('product_id')
                if isinstance(product_id, list):
                    if not product_id:
                        return Response({"error": "Model identified multiple products but the list was empty."}, status=status.HTTP_400_BAD_REQUEST)
                    product_id = product_id[0]
                    llm_response['product_id'] = product_id

                if product_id:
                    product = Product.objects.get(id=product_id)
                    llm_response['product_name'] = product.product_name
                    if action == "DELETE":
                        llm_response['description'] = f"Delete the product '{product.product_name}' (All {product.quantity} of them)."
                    elif action == "UPDATE":
                        update_data = llm_response.get('data', {})
                        changes = ", ".join([f"set {field} to '{value}'" for field, value in update_data.items()])
                        llm_response['description'] = f"Update the product '{product.product_name}': {changes}."
        except Product.DoesNotExist:
            return Response({"error": f"LLM suggested an action on a non-existent product ID: {product_id}"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": f"Error processing LLM response: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(llm_response, status=status.HTTP_200_OK)
    
class ExecuteActionAPIView(APIView):
    # No changes needed in this class
    parser_classes = [JSONParser]
    def post(self, request, *args, **kwargs):
        confirmed_action = request.data
        action = confirmed_action.get('action')
        product_id = confirmed_action.get('product_id')
        data = confirmed_action.get('data', {})
        if not action:
            return Response({"error": "Invalid action object: 'action' is missing."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            if action == "CREATE":
                serializer = ProductSerializer(data=data)
                if serializer.is_valid():
                    product_name = serializer.validated_data.get('product_name')
                    serializer.save()
                    return Response({"message": f"Product '{product_name}' created successfully."}, status=status.HTTP_201_CREATED)
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            elif action == "BULK_DELETE_EXPIRED":
                ids_to_delete = data.get('ids_to_delete', [])
                if not ids_to_delete:
                    return Response({"error": "No expired product IDs were provided for deletion."}, status=status.HTTP_400_BAD_REQUEST)
                
                deleted_count, _ = Product.objects.filter(id__in=ids_to_delete).delete()
                
                return Response({"message": f"{deleted_count} expired product(s) deleted successfully."}, status=status.HTTP_200_OK)
            
            if product_id is None:
                return Response({"error": "Invalid action object: 'product_id' is missing for UPDATE/DELETE."}, status=status.HTTP_400_BAD_REQUEST)
            
            product_to_modify = Product.objects.get(id=product_id)
            
            if action == "UPDATE":
                serializer = ProductSerializer(product_to_modify, data=data, partial=True)
                if serializer.is_valid():
                    serializer.save()
                    return Response({"message": f"Product '{product_to_modify.product_name}' updated successfully."}, status=status.HTTP_200_OK)
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            elif action == "DELETE":
                product_name = product_to_modify.product_name
                product_to_modify.delete()
                return Response({"message": f"Product '{product_name}' deleted successfully."}, status=status.HTTP_200_OK)
            
            else:
                return Response({"error": "Invalid action specified"}, status=status.HTTP_400_BAD_REQUEST)
        
        except Product.DoesNotExist:
            return Response({"error": f"Product with ID {product_id} not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": f"An error occurred: {str(e)}"}, status=fs.HTTP_500_INTERNAL_SERVER_ERROR)

# ... (ReceiveProductDataView and CheckScannedProductView remain unchanged) ...

class ReceiveProductDataView(APIView):
    """
    Receives product data (from the Telegram bot) and adds it to a
    queue for human-in-the-loop (HITL) review.
    """
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]

    def post(self, request, *args, **kwargs):
        data = request.data
        
        if data.get('action') == 'CREATE' and isinstance(data.get('data'), dict):
            product_data = data['data']
            scanned_product_queue.put(product_data)
            return Response(
                {"message": "Product data received and queued for review."}, 
                status=status.HTTP_202_ACCEPTED
            )
        
        return Response(
            {"error": "Invalid data format. Expected {'action': 'CREATE', 'data': {...}}"},
            status=status.HTTP_400_BAD_REQUEST
        )


class CheckScannedProductView(APIView):
    """
    Allows the frontend dashboard to poll for the next item
    in the scanned product queue.
    """
    def get(self, request, *args, **kwargs):
        if scanned_product_queue.empty():
            return Response(status=status.HTTP_204_NO_CONTENT)
        
        try:
            product_data = scanned_product_queue.get()
            
            name = product_data.get('product_name', 'N/A')
            price = product_data.get('price', 'N/A')
            quantity = product_data.get('quantity', 1) 
            expiry = product_data.get('expiry_date', 'N/A')

            description = f"Confirm Scanned Product: Add '{name}' (Quantity: {quantity}) with price ₹{price} and expiry date {expiry}?"

            product_data['quantity'] = quantity
            product_data['price'] = product_data.get('price') or 0.00
            
            proposal = {
                "action": "CREATE",
                "data": product_data,
                "description": description
            }
            
            return Response(proposal, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({"error": f"Error processing queue: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)