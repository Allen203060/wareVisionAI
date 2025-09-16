import google.generativeai as genai
from PIL import Image # Used to handle images
import os

# --- 1. Configuration ---
# It's recommended to set your API key as an environment variable for security.
# In your terminal: export GOOGLE_API_KEY="YOUR_API_KEY"
# However, for this script, you can paste it directly.
API_KEY = 'YOUR_API_KEY_HERE' # Paste your key here

try:
    genai.configure(api_key=API_KEY)
except Exception as e:
    print(f"Error configuring API key: {e}")
    exit()


# --- 2. Image Loading ---
try:
  # Make sure the filename matches your image file.
  img = Image.open('product-image.jpg')
except FileNotFoundError:
  print("Please ensure an image named 'product-image.jpg' is in the same directory as this script.")
  img = None


# --- 3. Prompt Definition ---
# This prompt instructs the model on its role, what to extract, and the output format.
prompt = """
You are an expert inventory management assistant.
Analyze the attached image of a product.
Extract ONLY the following information:
1. Product Name
2. Brand Name
3. Expiration Date (in YYYY-MM-DD format)

Provide the output ONLY in a clean JSON format with the keys:
"product_name", "brand", and "expiry_date".
If a value is not found, use "null".
"""


# --- 4. Call the AI and Get the Result ---
if img:
  print("Image loaded successfully. Sending request to Gemini API...")
  try:
    # Use a recommended model. 'gemini-1.5-flash-latest' is great for this task.
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    response = model.generate_content([prompt, img])

    # --- 5. Print the clean result ---
    print("\n--- AI Model Output ---")
    # Clean the response to ensure it's a valid JSON string
    clean_response = response.text.replace("```json", "").replace("```", "").strip()
    print(clean_response)
  except Exception as e:
    print(f"An error occurred while calling the Gemini API: {e}")

else:
  print("Skipping AI call because no image was loaded.")
