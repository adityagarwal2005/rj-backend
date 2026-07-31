from django.core.management.base import BaseCommand

from apps.orders import services


class Command(BaseCommand):
    help = "Send abandoned-cart reminders and auto-cancel stale unpaid orders."

    def handle(self, *args, **options):
        reminded = services.send_abandoned_order_reminders()
        cancelled = services.auto_cancel_stale_pending_orders()
        self.stdout.write(self.style.SUCCESS(f"Reminded {reminded} order(s), auto-cancelled {cancelled} stale order(s)."))
