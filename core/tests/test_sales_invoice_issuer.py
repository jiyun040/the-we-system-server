import json
from datetime import date
from unittest.mock import patch
from django.test import TestCase
from core.models import SalesLedgerRecord, User
from core.views_sales import sync_pdam_sales_records


class InvoiceIssuerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="invoice-test", password="test")
        self.client.force_login(self.user)
        self.record = SalesLedgerRecord.objects.create(
            source_id="issuer-test", project_name="상주 현장", contractor="코오롱 글로벌",
            partner="삼창건설", start_date=date(2026, 6, 12),
        )

    def save(self, payload):
        return self.client.patch(f"/api/v1/sales/ledger/{self.record.pk}",
            data=json.dumps(payload), content_type="application/json")

    def test_saved_issuer_survives_fresh_queries_and_pdam_sync(self):
        for issuer in ["코오롱글로벌", "협력사", ""]:
            with self.subTest(issuer=issuer):
                expected = issuer or "협력사"
                response = self.save({"invoiceIssuer": issuer})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["invoiceIssuer"], expected)
                self.record.refresh_from_db()
                self.assertEqual(self.record.invoice_issuer, expected)
                with patch("core.views_sales._pdam_rows", return_value=[{
                    "source_id": "issuer-test", "project_name": "상주 현장",
                    "start_date": "2026-06-12", "contractor": "코오롱 글로벌", "partner": "삼창건설",
                }]):
                    sync_pdam_sales_records()
                for url in ["/api/v1/sales/ledger?month=2026-09",
                            "/api/v1/sales/statements?month=2026-09&projectName=상주 현장"]:
                    result = self.client.get(url)
                    self.assertEqual(result.status_code, 200)
                    self.assertEqual(result.json()["items"][0]["invoiceIssuer"], expected)

    def test_partial_updates_preserve_issuer_and_invalid_values_are_rejected(self):
        self.assertEqual(self.save({"invoiceIssuer": "시공사"}).status_code, 200)
        self.assertEqual(self.save({"note": "메모"}).json()["invoiceIssuer"], "시공사")
        for value in [None, {}, "가" * 121]:
            self.assertEqual(self.save({"invoiceIssuer": value}).status_code, 400)
        self.record.refresh_from_db()
        self.assertEqual(self.record.invoice_issuer, "시공사")
