import os
import json
import httpx  # For sending data to Django
import logging
import base64
from io import BytesIO
from typing import Optional

# --- LangChain & Pydantic Imports ---
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

# --- Telegram Imports ---
from telegram import Update, File
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- CONFIGURATION ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
# You must have GOOGLE_API_KEY set in your environment for LangChain
if not os.environ.get('GEMINI_API_KEY'):
    print("Error: GEMINI_API_KEY environment variable not set.")
    exit()

# !! PASTE YOUR NGROK URL HERE !!
# This URL should match the one in your urls.py (e.g., /api/product/receive/)
DJANGO_BACKEND_URL = "https://multiview-transomed-ines.ngrok-free.dev/api/product/receive/"

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- STEP 3: Define the JSON Schema with Pydantic ---
# This tells LangChain *exactly* what JSON structure you want.

class ProductData(BaseModel):
    """Extracted data for a single product."""
    product_name: Optional[str] = Field(
        None, description="The main brand and name of the product"
    )
    price: Optional[float] = Field(
        None, description="The price of the product, if visible"
    )
    quantity: Optional[str] = Field(
        None, description="The quantity or weight (e.g., '100g', '6 pack'), if visible"
    )
    expiry_date: Optional[str] = Field(
        None, description="The expiration date, MUST be formatted as YYYY-MM-DD"
    )

class ProductAction(BaseModel):
    """The complete JSON object to be sent to the API."""
    action: str = Field(
        default="CREATE", description="The action to perform, defaults to CREATE"
    )
    data: ProductData = Field(
        description="The nested object containing product details"
    )


# --- AGENT LOGIC (LangChain) ---

async def process_image_with_langchain(image_bytes: bytes) -> ProductAction:
    """
    Uses LangChain and Gemini to extract structured data from an image.
    """
    logger.info("Initializing LangChain model...")
    
    # 1. Initialize the multimodal LLM
    # We use gemini-1.5-flash for speed
    # NEW (The fix)
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        logger.error("GEMINI_API_KEY not found in environment.")
        return None  # Or raise an error

    
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=api_key)
    
    # 2. Bind the Pydantic schema to the model
    # This forces the model to output JSON matching your ProductAction class
    structured_llm = llm.with_structured_output(ProductAction)

    # 3. Create the prompt message with the image
    prompt_text = """
    Analyze the attached image of a product.
    Extract the product_name and the expiry_date.
    If you see a price or quantity, extract those too.
    The expiry_date MUST be formatted as YYYY-MM-DD.
    If any field is not found, its value must be null.
    """
    
    # Base64-encode the image for the API
    image_b64 = base64.b64encode(image_bytes).decode('utf-8')
    image_url = f"data:image/jpeg;base64,{image_b64}"

    message = HumanMessage(
        content=[
            {"type": "text", "text": prompt_text},
            {"type": "image_url", "image_url": image_url}
        ]
    )

    logger.info("Calling LLM for structured extraction...")
    try:
        # 4. Invoke the chain
        response = await structured_llm.ainvoke([message])
        # 'response' is now a Pydantic object (ProductAction)
        return response 
        
    except Exception as e:
        logger.error(f"Error calling LangChain/Gemini: {e}")
        return None


# --- DJANGO SENDER ---

async def send_to_django(data: dict):
    """Sends the JSON data to the Django backend."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(DJANGO_BACKEND_URL, json=data, timeout=10.0)
            
            # --- FIX: Check for any 2xx success code (200, 201, 202, etc.) ---
            if 200 <= response.status_code < 300:
                logger.info(f"Successfully sent data to Django: {response.status_code} - {response.text}")
                try:
                    # Try to parse the JSON response from Django
                    return response.json()
                except json.JSONDecodeError:
                    # If Django sends a 2xx response with no body (like 204)
                    logger.warning("Django returned a non-JSON success response.")
                    return {"message": "Data sent successfully (no JSON content in response)."}
            else:
                # This will now only log for 4xx or 5xx errors
                logger.error(f"Non-success response from Django: {response.status_code} - {response.text}")
                return {"error": f"Django server returned {response.status_code}"}

        except httpx.RequestError as e:
            logger.error(f"Could not connect to Django backend: {e}")
            return {"error": "Could not connect to Django backend. Is ngrok running?"}

# --- TELEGRAM HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message."""
    await update.message.reply_text(
        "Hi! Send me a photo of a product, and I'll use LangChain to extract its details."
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles incoming photos."""
    message = update.message
    if not message.photo:
        await message.reply_text("Please send a photo.")
        return

    await message.reply_text("Processing with LangChain... 🤖")

    try:
        # Download the photo into memory
        photo_file: File = await message.photo[-1].get_file()
        image_stream = BytesIO()
        await photo_file.download_to_memory(image_stream)
        image_bytes = image_stream.getvalue()

        # 1. Process image with LangChain
        # This returns our Pydantic ProductAction object
        extracted_data_object = await process_image_with_langchain(image_bytes)
        
        if not extracted_data_object:
            await message.reply_text("Error: Could not process the image.")
            return

        # Convert Pydantic object to dict for JSON serialization
        extracted_data_dict = extracted_data_object.model_dump()

        await message.reply_text(
            "Extracted data:\n"
            f"```json\n{json.dumps(extracted_data_dict, indent=2)}\n```",
            parse_mode='MarkdownV2'
        )

        # 2. Send data to Django
        await message.reply_text("Sending data to Django backend...")
        django_response = await send_to_django(extracted_data_dict)

        if "error" in django_response:
            await message.reply_text(f"Backend error: {django_response['error']}")
        else:
            # --- FIX: Display the custom message from Django ---
            success_message = django_response.get('message', 'Data received by backend.')
            await message.reply_text(f"✅ Success! {success_message}")

    except Exception as e:
        logger.error(f"Error in handle_photo: {e}")
        await message.reply_text(f"An unexpected error occurred: {e}")

# --- MAIN FUNCTION ---
def main():
    """Starts the bot."""
    if not TELEGRAM_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN environment variable not set.")
        return

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("Bot is running. Press Ctrl-C to stop.")
    application.run_polling()

if __name__ == "__main__":
    main()