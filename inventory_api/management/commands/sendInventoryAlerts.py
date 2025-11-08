# inventory_api/management/commands/send_inventory_alerts.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import date
from inventory_api.models import Product
import logging
from django.conf import settings

min_q = getattr(settings, "ALERT_MIN_QUANTITY", 50)

from inventory_api.gmail_utils import get_gmail_service, build_html_body, send_html_email

try:
    import pandas as pd
except Exception:
    pd = None

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Scan inventory for expired/low-stock items and send email alerts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--min_quantity",
            type=int,
            default=50,
            help="Threshold below which stock is considered low (default: 50)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Don't send email, just print what would be sent.",
        )

    def handle(self, *args, **options):
        min_q = options["min_quantity"]
        dry_run = options["dry_run"]

        today = date.today()
        expired_qs = Product.objects.filter(expiry_date__lt=today)
        low_stock_qs = Product.objects.filter(quantity__lt=min_q)

        # Combine uniquely
        combined_qs = (expired_qs | low_stock_qs).distinct()

        if not combined_qs.exists():
            self.stdout.write(self.style.SUCCESS(f"[{timezone.now()}] No expired/low-stock items found."))
            return

        # Build DataFrame or list of dicts for email utils
        rows = []
        for p in combined_qs:
            rows.append({
                "id": p.id,
                "product_name": p.product_name,
                "quantity": p.quantity,
                "price": float(p.price) if p.price is not None else None,
                "expiry_date": p.expiry_date.isoformat() if p.expiry_date else None,
            })

        df = None
        if pd:
            df = pd.DataFrame(rows)
        else:
            df = rows  # list of dicts

        total_expired = expired_qs.count()
        total_low_stock = low_stock_qs.count()

        html_body = build_html_body(df, total_expired, total_low_stock)
        subject = f"⚠️ {combined_qs.count()} Inventory Alerts Detected — {date.today().strftime('%d-%m-%Y')}"

        if dry_run:
            # Print to console (debug)
            self.stdout.write("DRY RUN: Would send email with subject: " + subject)
            self.stdout.write(html_body)
            return

        # send
        try:
            service = get_gmail_service()
            send_html_email(service, html_body, subject)
            self.stdout.write(self.style.SUCCESS(f"Email sent successfully. {combined_qs.count()} items included."))
        except Exception as e:
            logger.exception("Failed to send inventory alert email:")
            self.stderr.write(self.style.ERROR(f"Failed to send email: {e}"))
