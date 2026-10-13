import json
from datetime import date

from django.test import TestCase

from core.models import SalesLedgerRecord, User


class SalesAdjustmentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='sales-adjustment', password='test')
        self.client.force_login(self.user)
        self.record = SalesLedgerRecord.objects.create(
            source_id='adjustment-test', project_name='검증 현장',
            start_date=date(2026, 9, 1), supply_amount=2700000,
        )

    def test_adjustment_survives_save_reload_and_unrelated_update(self):
        url = f'/api/v1/sales/ledger/{self.record.pk}'
        saved = self.client.patch(url, data=json.dumps({
            'supplyAmount': 2700000,
            'adjustmentAmount': 300000,
            'adjustmentReason': '계약 네고',
            'note': '계약 네고',
        }), content_type='application/json')
        self.assertEqual(saved.status_code, 200, saved.content)
        self.record.refresh_from_db()
        self.assertEqual(self.record.adjustment_amount, 300000)
        self.assertEqual(self.record.adjustment_reason, '계약 네고')
        self.assertEqual(saved.json()['adjustmentAmount'], 300000)
        self.assertEqual(saved.json()['adjustmentReason'], '계약 네고')
        ledger = self.client.get('/api/v1/sales/ledger?month=2026-09')
        item = ledger.json()['items'][0]
        self.assertEqual(item['adjustmentAmount'], 300000)
        self.assertEqual(item['adjustmentReason'], '계약 네고')
        later = self.client.patch(url, data=json.dumps({'status': '진행'}), content_type='application/json')
        self.assertEqual(later.json()['adjustmentAmount'], 300000)
        self.assertEqual(later.json()['adjustmentReason'], '계약 네고')
