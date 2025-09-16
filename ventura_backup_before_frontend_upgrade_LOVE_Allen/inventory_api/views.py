
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import FormParser, MultiPartParser, JSONParser
from django.shortcuts import render, redirect
from django.core import management
from .models import Product
from .serializers import ProductSerializer
from .mcp import get_llm_reasoning
import json



def index(request):
    
    return render(request, 'index.html')


class ProductListAPIView(generics.ListAPIView):
    """
    API view to retrieve a list of all products.
    """
    queryset = Product.objects.all()
    serializer_class = ProductSerializer



class ProposeActionAPIView(APIView):
    """
    Receives a natural language query, asks the LLM to propose a database action,
    and returns that proposed action to the frontend for confirmation.
    """
    parser_classes = [JSONParser]

    def post(self, request, *args, **kwargs):
        user_query = request.data.get('query')
        if not user_query:
            return Response({"error": "Query not provided"}, status=status.HTTP_400_BAD_REQUEST)

        products = Product.objects.all()
        inventory_data = list(products.values('id', 'product_name', 'price', 'expiry_date'))
        for item in inventory_data:
            item['expiry_date'] = item['expiry_date'].isoformat()
            item['price'] = float(item['price'])
        inventory_json = json.dumps(inventory_data, indent=2)

        prompt = f"""
        You are an inventory management database agent. Based on the user's query and the current inventory data, generate a JSON object describing the database operation to perform.

        The user's query is: "{user_query}"
        The current inventory data is: {inventory_json}

        Return a single, clean JSON object with the following structure:
        {{
          "action": "ACTION_TYPE",
          "product_id": ID_OF_PRODUCT_TO_MODIFY,
          "data": {{ "field_to_update": "new_value" }}
        }}

        - "action" can be "UPDATE" or "DELETE".
        - "product_id" must be the integer ID of the product the user is referring to.
        - "data" is a dictionary of fields to update. For "UPDATE", this must contain the fields to change. For "DELETE", this can be an empty object.
        - If you cannot determine a clear action or product, return an empty JSON object {{}}.
        """

        llm_response = get_llm_reasoning(prompt)

        if not llm_response or "error" in llm_response:
            return Response(llm_response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if not llm_response or "error" in llm_response:
            return Response(llm_response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            product_id = llm_response.get('product_id')
            action = llm_response.get('action')

            # **FIX:** The LLM might return a list of IDs if the query is ambiguous.
            # This code now handles that case by safely taking the first ID from the list.
            if isinstance(product_id, list):
                if not product_id:
                    return Response({"error": "Model identified multiple products but the list was empty."}, status=status.HTTP_400_BAD_REQUEST)
                # Take the first ID to propose a single, clear action
                product_id = product_id[0]
                # Update the llm_response object so the correct ID is sent to the frontend
                llm_response['product_id'] = product_id

            if product_id and action:
                product = Product.objects.get(id=product_id)
                llm_response['product_name'] = product.product_name
                if action == "DELETE":
                    llm_response['description'] = f"Delete the product '{product.product_name}'."
                elif action == "UPDATE":
                    update_data = llm_response.get('data', {})
                    changes = ", ".join([f"set {field} to '{value}'" for field, value in update_data.items()])
                    llm_response['description'] = f"Update the product '{product.product_name}': {changes}."
        except Product.DoesNotExist:
            return Response({"error": f"LLM suggested an action on a non-existent product ID: {product_id}"}, status=status.HTTP_404_NOT_FOUND)
        except TypeError as e:
            # This can happen if product_id is not an int or list, but something else.
            return Response({"error": f"Invalid format for product_id from LLM: {product_id}. Error: {e}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response(llm_response, status=status.HTTP_200_OK)

class ExecuteActionAPIView(APIView):
    """
    Receives a confirmed action from the frontend and executes it on the database.
    """
    parser_classes = [JSONParser]

    def post(self, request, *args, **kwargs):
        confirmed_action = request.data
        action = confirmed_action.get('action')
        product_id = confirmed_action.get('product_id')

        if not action or product_id is None:
            return Response({"error": "Invalid action object"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            product_to_modify = Product.objects.get(id=product_id)

            if action == "UPDATE":
                update_data = confirmed_action.get('data', {})
                for field, value in update_data.items():
                    if hasattr(product_to_modify, field):
                        setattr(product_to_modify, field, value)
                product_to_modify.save()
                return Response({"message": f"Product '{product_to_modify.product_name}' updated successfully."}, status=status.HTTP_200_OK)

            elif action == "DELETE":
                product_name = product_to_modify.product_name
                product_to_modify.delete()
                return Response({"message": f"Product '{product_name}' deleted successfully."}, status=status.HTTP_200_OK)

            else:
                return Response({"error": "Invalid action specified"}, status=status.HTTP_400_BAD_REQUEST)

        except Product.DoesNotExist:
            return Response({"error": f"Product with ID {product_id} not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": f"An error occurred: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)