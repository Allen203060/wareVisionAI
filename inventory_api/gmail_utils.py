# inventory_api/gmail_utils.py
import os
import base64
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Union

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from django.conf import settings

logger = logging.getLogger(__name__)

# SCOPES
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

# read paths & emails from settings (via .env)
CREDENTIALS_PATH = getattr(settings, "GMAIL_CONFIG", {}).get(
    "CREDENTIALS_PATH", os.path.join(settings.BASE_DIR, "credentials.json")
)
TOKEN_PATH = getattr(settings, "GMAIL_CONFIG", {}).get(
    "TOKEN_PATH", os.path.join(settings.BASE_DIR, "token.json")
)
EMAIL_FROM = getattr(settings, "GMAIL_CONFIG", {}).get("FROM", "me")
EMAIL_TO = getattr(settings, "GMAIL_CONFIG", {}).get("TO", None)


class GmailAuthError(RuntimeError):
    pass


def _is_wsl() -> bool:
    """
    Return True if running inside WSL. We use this to pick console auth automatically.
    """
    try:
        if "WSL_DISTRO_NAME" in os.environ:
            return True
        if os.path.exists("/proc/version"):
            with open("/proc/version", "r", encoding="utf-8") as f:
                txt = f.read().lower()
                if "microsoft" in txt or "wsl" in txt:
                    return True
    except Exception:
        pass
    return False


def _ensure_file_permissions(path: str):
    """Try to set restrictive permissions on token/credential files (non-fatal)."""
    try:
        if os.path.exists(path):
            os.chmod(path, 0o600)
    except Exception:
        logger.debug("Could not chmod %s (non-fatal).", path, exc_info=True)


def _manual_console_flow(flow: InstalledAppFlow) -> Credentials:
    """
    Manual console flow compatible with all google-auth-oauthlib versions.
    Prints a URL that you open in a browser and prompts for the authorization code.
    """
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    print("\nPlease visit this URL to authorize this application:\n")
    print(auth_url)
    print("\nAfter approving, copy the code shown and paste it below.")
    auth_code = input("Enter the authorization code: ").strip()
    if not auth_code:
        raise GmailAuthError("No authorization code provided.")
    # exchange the code
    flow.fetch_token(code=auth_code)
    creds = flow.credentials
    return creds


def get_gmail_service(interactive: Optional[bool] = None):
    """
    Return an authorized Gmail API service.

    Behavior:
      - If interactive is None, it will auto-detect WSL and use console auth there.
      - If interactive is True, it tries a local browser (run_local_server).
      - If interactive is False, it uses manual console flow (no browser).
    """
    # Decide interactive behavior
    if interactive is None:
        interactive = not _is_wsl()

    creds: Optional[Credentials] = None

    # Load token if present
    if os.path.exists(TOKEN_PATH):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        except Exception as e:
            logger.warning("Failed to load token file %s: %s", TOKEN_PATH, e, exc_info=True)
            creds = None

    # If invalid/absent, try refresh or re-auth
    if not creds or not creds.valid:
        # try refresh if possible
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.warning("Failed to refresh token: %s", e, exc_info=True)
                creds = None

        # If still no valid creds, perform auth flow
        if not creds:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(f"Credentials file not found: {CREDENTIALS_PATH}")

            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)

            try:
                if interactive:
                    # This will open a browser on desktop environments
                    creds = flow.run_local_server(port=0)
                else:
                    # Use manual console flow (works across google_auth_oauthlib versions)
                    creds = _manual_console_flow(flow)
            except Exception as e:
                # Surface a helpful message
                logger.exception("Failed during OAuth flow: %s", e)
                raise GmailAuthError(
                    "OAuth authorization failed. If you're headless, run locally to create token.json or "
                    "ensure you paste the authorization code when prompted."
                ) from e

            # Save token
            try:
                with open(TOKEN_PATH, "w", encoding="utf-8") as token_file:
                    token_file.write(creds.to_json())
                _ensure_file_permissions(TOKEN_PATH)
            except Exception as e:
                logger.warning("Could not save token file to %s: %s", TOKEN_PATH, e, exc_info=True)

    # Build service
    try:
        service = build("gmail", "v1", credentials=creds)
        return service
    except Exception as e:
        logger.exception("Failed to build Gmail service: %s", e)
        raise GmailAuthError("Could not create Gmail service client.") from e


def send_html_email(service, html_body: str, subject: str, recipient: Optional[str] = None) -> dict:
    """
    Send an HTML email using Gmail API service.
    Returns the Gmail API response on success.
    """
    recipient = recipient or EMAIL_TO
    if recipient is None:
        raise ValueError("Recipient email not configured. Set ALERT_EMAIL_TO or GMAIL_CONFIG['TO'].")

    message = MIMEMultipart("alternative")
    message["to"] = recipient
    message["subject"] = subject
    message.attach(MIMEText(html_body, "html"))

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    try:
        resp = service.users().messages().send(userId=EMAIL_FROM, body={"raw": raw_message}).execute()
        logger.info("Sent email to %s; message id: %s", recipient, resp.get("id"))
        return resp
    except HttpError as e:
        logger.exception("Gmail API returned an error: %s", e)
        raise
    except Exception as e:
        logger.exception("Unexpected error sending email: %s", e)
        raise


def build_html_body(alert_df: Union["pd.DataFrame", list, dict], total_expired: int, total_low_stock: int) -> str:
    """
    Build the HTML body. Accepts a pandas.DataFrame or list-of-dicts.
    Uses a Pandas Styler if available, otherwise falls back to a plain table.
    """
    try:
        import pandas as pd
    except Exception:
        pd = None

    html_table = ""
    if pd and isinstance(alert_df, pd.DataFrame):
        # Try to use Styler (requires jinja2)
        try:
            def highlight_row(row):
                today = datetime.now().date()
                expiry_date = None
                try:
                    expiry_date = pd.to_datetime(row.get("expiry_date"), errors="coerce").date()
                except Exception:
                    expiry_date = None
                if expiry_date and expiry_date <= today:
                    return ['background-color: #ffcccc'] * len(row)
                elif (row.get("quantity") is not None) and (int(row.get("quantity") or 0) < 50):
                    return ['background-color: #fff3cd'] * len(row)
                else:
                    return [''] * len(row)

            styled = alert_df.style.apply(highlight_row, axis=1).hide(axis="index")
            html_table = styled.to_html(justify="center")
        except Exception:
            # fallback to simple table if Styler/jinja2 not available
            rows = alert_df.to_dict("records")
            cols = ["product_name", "quantity", "price", "expiry_date"]
            header_cells = "".join([f"<th>{c.replace('_',' ').title()}</th>" for c in cols])
            row_html = ""
            for r in rows:
                cells = "".join([f"<td>{r.get(c, '')}</td>" for c in cols])
                row_html += f"<tr>{cells}</tr>"
            html_table = f"<table><thead><tr>{header_cells}</tr></thead><tbody>{row_html}</tbody></table>"
    else:
        # alert_df is list/dict or pandas not present: build plain table
        rows = alert_df if isinstance(alert_df, list) else (alert_df.to_dict("records") if pd else [])
        cols = ["product_name", "quantity", "price", "expiry_date"]
        header_cells = "".join([f"<th>{c.replace('_',' ').title()}</th>" for c in cols])
        row_html = ""
        for r in rows:
            cells = "".join([f"<td>{r.get(c, '')}</td>" for c in cols])
            row_html += f"<tr>{cells}</tr>"
        html_table = f"<table><thead><tr>{header_cells}</tr></thead><tbody>{row_html}</tbody></table>"

    html_body = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: 'Segoe UI', Arial, sans-serif;
                background-color: #f9f9f9;
                color: #333;
                margin: 20px;
            }}
            h2 {{ color: #2c3e50; }}
            table {{
                border-collapse: collapse;
                width: 80%;
                margin-top: 10px;
                font-size: 14px;
            }}
            th, td {{
                border: 1px solid #999;
                padding: 8px;
                text-align: center;
            }}
            th {{ background-color: #2c3e50; color: white; }}
            .summary {{ background-color: #eef; padding: 10px; border-radius: 6px; width: fit-content; }}
        </style>
    </head>
    <body>
        <h2>🧠 WareVision-AI Inventory Alert</h2>
        <div class="summary">
            <p><b>Summary:</b></p>
            <ul>
                <li>Expired Items: <b>{total_expired}</b></li>
                <li>Low Stock Items: <b>{total_low_stock}</b></li>
                <li>Generated On: <b>{datetime.now().strftime("%d-%m-%Y  %H:%M:%S")}</b></li>
            </ul>
        </div>
        <p>The following products need your attention:</p>
        {html_table}
        <p>Please restock or remove expired items.</p>
        <br>
        <p style="color:gray;font-size:12px;">
            This is an automated alert from your <b>WareVision-AI Inventory Monitor</b>.<br>
            Please do not reply to this email.
        </p>
        <em>— Automated Inventory System</em>
    </body>
    </html>
    """
    return html_body
