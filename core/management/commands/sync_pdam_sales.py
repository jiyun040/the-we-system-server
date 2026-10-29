from django.core.management.base import BaseCommand

from core.views_sales import sync_pdam_sales_records


class Command(BaseCommand):
    help = "Synchronize sales ledger records from the PDAM database."

    def handle(self, *args, **options):
        sync_pdam_sales_records()
        self.stdout.write(self.style.SUCCESS("PDAM sales records synchronized."))
