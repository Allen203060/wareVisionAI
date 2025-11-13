# 🤖 WareVision: The AI-Powered Inventory System 

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-4.2%2B-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![DRF](https://img.shields.io/badge/Django_Rest_Framework-3.14-A30000?logo=django&logoColor=white)](https://www.django-rest-framework.org/)
[![JavaScript](https://img.shields.io/badge/JavaScript-ES6%2B-F7DF1E?logo=javascript&logoColor=black)](https://developer.mozilla.org/en-US/docs/Web/JavaScript)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3.4-38B2AC?logo=tailwind-css&logoColor=white)](https://tailwindcss.com/)
[![Ollama](https://img.shields.io/badge/Ollama-Local_LLM-blueviolet)](https://ollama.ai/)
[![Gemini](https://img.shields.io/badge/Google_Gemini-1.5_Flash-4285F4?logo=google-gemini&logoColor=white)](https://gemini.google.com/)
[![Telegram](https://img.shields.io/badge/Telegram_Bot-20.0-26A5E4?logo=telegram&logoColor=white)](https://python-telegram-bot.org/)

WareVision is a smart, conversational inventory management system. Instead of clicking buttons and filling forms, you can manage your stock using plain English. It's powered by a locally-hosted, fine-tuned language model that understands your commands.

It also features a **Human-in-the-Loop (HITL) scanner**, allowing you to scan product expiry dates with your phone's Telegram app and have them appear in the dashboard for one-click confirmation.

## 📸 Application Preview

*(**Action Required:** Take a screenshot of your running application and replace the link below!)*

![Ventura Dashboard Screenshot](https://raw.githubusercontent.com/username/repo/main/screenshot.png)

---

## ✨ Core Features

* **Natural Language Commands:** Manage your entire inventory through a single chat bar. Try "add 10 loaves of bread at 150rs each, expiring in 2 weeks," "delete all expired items," or "change the price of apples to 60."
* **AI "Propose & Confirm" Workflow:** The AI proposes a database action (like a `CREATE` or `UPDATE`), which you must review and confirm in a modal. This prevents AI hallucinations from corrupting your data.
* **Telegram HITL Scanner:** A Telegram bot uses the **Google Gemini** model (via LangChain) to read product names and expiry dates from photos. Scanned items are automatically added to a queue on the dashboard for you to verify.
* **Automated Email Alerts:** A background cron job automatically scans the inventory for expired or low-stock items and sends a daily HTML alert email via the Gmail API.
* **Real-time Dashboard:** A clean, responsive UI built with Tailwind CSS that shows key stats like total products, stock value, and items expiring soon.
* **Local-First AI:** The core query feature runs on a locally-hosted, fine-tuned `Phi-3-mini` model served via **Ollama**, ensuring your data stays private and the service runs with no API costs.

---

## ⚙️ How It Works (System Architecture)

Ventura operates on three primary data flows:

### 1. Natural Language Query (from the Web UI)

This is the main interaction loop for managing inventory from the dashboard.

1.  **UI ➡️ Backend:** A user types "change the price of oranges to 20" into the web UI. The JavaScript frontend sends this raw text string to the `/api/query/` endpoint.
2.  **Backend ➡️ AI (Ollama):** The `ProposeActionAPIView` in `views.py` receives the text. It builds a complex prompt containing the user's query, critical rules, and the **entire current inventory** (as a compact JSON string). This prompt is sent to the local Ollama server running the `phi3-finetuned-inventory:v2` model.
3.  **AI (Ollama) ➡️ Backend:** The fine-tuned model processes the prompt and returns a structured JSON object, like `{"action": "UPDATE", "product_name": "Oranges", "data": {"price": 20}}`.
4.  **Backend (Logic):** The `ProposeActionAPIView` performs a case-insensitive lookup for "Oranges" in the database. It finds the matching product (e.g., ID 15), adds the correct `product_id: 15` to the JSON, and builds a human-readable description (e.g., "Update 'Oranges': set price to '20'.").
5.  **Backend ➡️ UI:** The backend sends this complete "proposal" back to the frontend.
6.  **UI (HITL):** The JavaScript receives the proposal and opens the **Confirmation Modal**, pre-filling the form with the AI's data.
7.  **UI ➡️ Backend:** The user verifies the data and clicks "Confirm." The final, verified JSON (including the `product_id`) is sent to the `/api/execute-action/` endpoint.
8.  **Backend (Execute):** The `ExecuteActionAPIView` receives the confirmed JSON and safely performs the database operation (`product.save()`).

### 2. Image Scanner (from the Telegram Bot)

This is the Human-in-the-Loop (HITL) flow for adding new items by scanning them.

1.  **User ➡️ Bot:** The user takes a photo of a product's expiry date and sends it to the Telegram bot.
2.  **Bot ➡️ AI (Gemini):** The `bot.py` script sends the image to the **Google Gemini API** (via LangChain) with a prompt asking it to extract the product name and expiry date into a specific JSON format.
3.  **AI (Gemini) ➡️ Bot:** Gemini returns the structured JSON, e.g., `{"action": "CREATE", "data": {"product_name": "Amul Milk", "expiry_date": "2025-11-20", ...}}`.
4.  **Bot ➡️ Backend:** The bot POSTs this JSON to the `/api/product/receive/` endpoint (exposed publicly via ngrok).
5.  **Backend (Queue):** The `ReceiveProductDataView` receives the JSON and pushes the `data` object into a global, in-memory `Queue`.
6.  **UI (Polling):** Meanwhile, the `index.html` JavaScript polls the `/api/product/check-scanned/` endpoint every 3 seconds.
7.  **Backend ➡️ UI:** As soon as the `CheckScannedProductView` finds an item in the queue, it pulls it, builds a full "proposal" (with a description), and sends it to the UI.
8.  **UI (HITL):** The UI receives the proposal and automatically opens the **Confirmation Modal**. The user can then fill in the missing `price`/`quantity` and click **Confirm** to add the new item.

### 3. Automated Inventory Alerts (Background Cron Job)

This flow runs entirely on the server to monitor inventory.

1.  **Cron Scheduler ➡️ Server:** A system-level cron job (e.g., `0 9 * * *` for 9:00 AM daily) executes the `run_inventory_alerts.sh` script.
2.  **Script ➡️ Django:** The script activates the Python virtual environment and runs the Django management command `python manage.py sendInventoryAlerts`.
3.  **Django (Logic):** The command queries the database for any products that are expired (`expiry_date < today`) or low-stock (`quantity < 50`).
4.  **Django ➡️ Google API:** If alerts are found, the `gmail_utils.py` module authenticates with the Gmail API using a `token.json` (OAuth 2.0).
5.  **Google API ➡️ User:** The script sends a formatted HTML email to the admin with a summary of all items needing attention.

---

## 🚀 Technology Stack

* **Backend:** Django, Django Rest Framework (DRF)
* **Frontend:** Vanilla JavaScript (ES6+), Tailwind CSS
* **AI (Core Query):** Ollama, `Phi-3-mini` (Fine-tuned with QLoRA)
* **AI (Image Scanning):** Google Gemini (via LangChain for structured output)
* **Email Alerts:** Gmail API (via `google-api-python-client`)
* **Bot:** `python-telegram-bot`
* **Database:** SQLite3 (default, easily swappable with PostgreSQL)
* **API Client (Bot):** `httpx`
* **Task Scheduling:** System Cron

---

## 📦 Setup & Installation Guide

You need to set up three main components: the **Django Backend**, the **Ollama AI Server**, and the **Telegram Bot**.

### 1. Django Backend (WareVision Project)

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/your-username/ventura.git](https://github.com/your-username/ventura.git)
    cd ventura
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install Python dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Create your Environment File:**
    This project uses a `.env` file to manage all secrets. Copy the example file and then edit it.
    ```bash
    cp .env.example .env
    nano .env
    ```
    Now, fill in the following values in your `.env` file:
    ```dotenv
    # --- Django Settings ---
    # Generate a new key: [https://djecrety.ir/](https://djecrety.ir/)
    SECRET_KEY="your-django-secret-key"
    DEBUG="True"

    # --- Gmail Alert Settings ---
    # This is the email address your alerts will be sent TO.
    ALERT_EMAIL_TO="your-personal-email@gmail.com"
    # This is the email your bot will send FROM. Must be the one you authorize in step 5.
    ALERT_EMAIL_FROM="your-bot-email@gmail.com"

    # --- Telegram Bot & Gemini API ---
    TELEGRAM_BOT_TOKEN="your-token-from-botfather"
    GEMINI_API_KEY="your-google-ai-studio-api-key"
    ```

5.  **Authorize Google API (for Email Alerts):**
    * Go to the [Google Cloud Console](https://console.cloud.google.com/).
    * Create a new project.
    * Enable the **Gmail API**.
    * Go to "Credentials" -> "Create Credentials" -> "OAuth client ID".
    * Select "Desktop application".
    * Download the JSON file, rename it to `credentials.json`, and place it in the project root (where `manage.py` is).
    * **Run the auth flow once manually:** This will open a browser, ask you to log in, and generate a `token.json` file. This token is what the cron job will use later.
    ```bash
    python manage.py sendInventoryAlerts --dry-run
    ```

6.  **Run database migrations:**
    ```bash
    python manage.py migrate
    ```

7.  **(Optional) Seed the database:**
    You can use the `seed_products` command to add initial sample data.
    ```bash
    python manage.py seed_products
    ```

8.  **Run the development server:**
    ```bash
    python manage.py runserver
    ```
    Your application is now running at `http://localhost:8000`.

### 2. AI Model (Ollama)

1.  **Install Ollama:** Follow the instructions at [ollama.ai](https://ollama.ai/).

2.  **Pull the base model:**
    ```bash
    ollama pull phi3
    ```

3.  **Run your fine-tuning scripts:**
    * Run your `trainingMphi.py` script to create the LoRA adapter. This will create a folder like `./phi3-finetuned-inventory`.
    * Run your `merge_model.py` script to merge the adapter with the base model. This will create a merged model folder (e.g., `./phi3-merged-model`).

4.  **Create the model in Ollama:**
    * Ensure your `Modelfile-v2` (or equivalent) is in the same directory.
    * Run the create command (using your tag):
    ```bash
    ollama create phi3-finetuned-inventory:v2 -f Modelfile-v2
    ```

5.  **Verify:** Check that the model is available to be served:
    ```bash
    ollama list
    ```
    You should see `phi3-finetuned-inventory:v2` in the list.

### 3. Telegram Bot & HITL Scanner

1.  **Start ngrok:** Your bot (running on your computer) needs a public URL to send data to your Django server (also on your computer). `ngrok` creates this tunnel.
    ```bash
    ngrok http 8000
    ```

2.  **Update `bot.py`:** Copy the public "Forwarding" URL from your ngrok terminal (e.g., `https://random-name.ngrok-free.dev`) and paste it into the `DJANGO_BACKEND_URL` variable in `bot.py`.
    ```python
    # in bot.py
    DJANGO_BACKEND_URL = "[https://your-ngrok-url-here.ngrok-free.dev/api/product/receive/](https://your-ngrok-url-here.ngrok-free.dev/api/product/receive/)"
    ```

3.  **Run the bot:**
    (Ensure your secrets from Step 1.4 are in your `.env` file)
    ```bash
    python bot.py
    ```

### 4. (Optional) Setup Automated Alers (Cron Job)

The Django server **does not** need to be running for this to work. This is a separate background task.

1.  **Make the script executable:**
    ```bash
    chmod +x run_inventory_alerts.sh
    ```

2.  **Edit your crontab:**
    Open your system's cron job editor:
    ```bash
    crontab -e
    ```

3.  **Add the cron job:**
    Add the following line to the file. This example runs the script **every day at 9:00 AM**. Make sure to **use the absolute path** to your project directory.
    ```crontab
    # Run WareVision email alerts daily at 9am
    0 9 * * * /bin/bash /home/allen/projects/ventura_web/ventura/run_inventory_alerts.sh
    ```
    *(To test it, you can use `*/1 * * * *` to run it every minute, but remove this after testing.)*

4.  **Check logs:** The script will automatically log its output and any errors to the `logs/` directory in your project.

---

## 🎮 How to Use

1.  **Open the Dashboard:** Go to `http://localhost:8000` in your browser.
2.  **Use the Query Bar:**
    * **Add:** "add 20 cartons of milk at 50rs, expiring in 3 weeks"
    * **Update:** "change the price of milk to 55"
    * **Delete:** "delete the milk"
    * **Bulk Delete:** "delete expired items"
    * **Query:** "how many items are running low?"
3.  **Use the HITL Scanner:**
    * Open your Telegram app and find your bot.
    * Send it a clear photo of a product's name and/or expiry date.
    * Wait a few seconds. The bot will reply with the JSON it extracted.
    * Go back to your `http://localhost:8000` dashboard.
    * Within 3-5 seconds, the **Confirmation Modal** will pop up with the scanned data, ready for you to verify, complete (add price/quantity), and confirm.