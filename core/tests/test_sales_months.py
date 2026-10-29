import json
from datetime import date
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import TestCase
from django.test import override_settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import SalesLedgerArchive, SalesLedgerRecord, SalesLedgerMonth, User
from core.pdam_sales import sales_query, DEFAULT_PDAM_SALES_QUERY
from core.views_sales import _data, _records_for_month, sync_pdam_sales_records


class SalesMonthTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_user(username='monthly-sales'))
        self.record = SalesLedgerRecord.objects.create(
            source_id='long-contract', project_name='장기 현장', elevator='1호기',
            start_date=date(2026, 8, 10), end_date=date(2026, 12, 15),
            pdam_status='진행', status='진행', category='본사',
        )

    def test_active_contract_only_displays_selected_month(self):
        data = _data(self.record, date(2026, 10, 1))
        self.assertEqual((data['startDate'], data['endDate']), ('2026-10-01', '2026-10-31'))
        self.assertEqual((data['contractStartDate'], data['contractEndDate']), ('2026-08-10', '2026-12-15'))
        self.assertEqual(_data(self.record, date(2026, 8, 1))['startDate'], '2026-08-10')
        # An active device's scheduled end is not an actual completion date.
        self.assertEqual(_data(self.record, date(2026, 12, 1))['endDate'], '2026-12-31')

    def test_ended_device_uses_actual_end_only_in_ending_month(self):
        self.record.pdam_status = '종료'
        self.record.status = '종료'
        self.record.end_date = date(2026, 10, 17)
        self.record.save()
        self.assertEqual(_data(self.record, date(2026, 10, 1))['endDate'], '2026-10-17')
        self.assertEqual(_data(self.record, date(2026, 9, 1))['status'], '진행')
        self.assertEqual(_data(self.record, date(2026, 9, 1))['endDate'], '2026-09-30')
        self.assertFalse(_records_for_month(date(2026, 11, 1)).exists())

    def test_billing_next_month_preserves_previous_bill_and_contract(self):
        url = f'/api/v1/sales/ledger/{self.record.pk}'
        for month, amount in [('2026-09', 3000000), ('2026-10', 2800000)]:
            response = self.client.patch(url, data=json.dumps({
                'month': month, 'billingDate': month+'-20', 'supplyAmount': amount,
                'startDate': month+'-01', 'endDate': month+('-30' if month.endswith('09') else '-31'),
            }), content_type='application/json')
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response.json()['supplyAmount'], amount)
        self.record.refresh_from_db()
        self.assertEqual(self.record.start_date, date(2026, 8, 10))
        self.assertEqual(self.record.end_date, date(2026, 12, 15))
        self.assertEqual(_data(self.record, date(2026, 9, 1))['supplyAmount'], 3000000)
        self.assertEqual(_data(self.record, date(2026, 10, 1))['supplyAmount'], 2800000)
        november = self.client.get('/api/v1/sales/ledger?month=2026-11').json()
        self.assertEqual(november['items'][0]['billingDate'], '')
        self.assertEqual(november['items'][0]['startDate'], '2026-11-01')
        self.assertEqual(november['summary']['billCount'], 0)
        statement = self.client.get('/api/v1/sales/statements', {'month':'2026-10', 'projectName':'장기 현장'}).json()
        self.assertEqual(statement['items'][0]['endDate'], '2026-10-31')
        self.assertEqual(statement['items'][0]['supplyAmount'], 2800000)

    def test_next_installment_advances_only_after_invoice_is_saved(self):
        url = f'/api/v1/sales/ledger/{self.record.pk}'
        self.assertEqual(_data(self.record, date(2026, 10, 1))['installment'], 1)
        response = self.client.patch(url, data=json.dumps({
            'month': '2026-09', 'billingDate': '2026-09-20',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(_data(self.record, date(2026, 10, 1))['installment'], 1)
        response = self.client.patch(url, data=json.dumps({
            'month': '2026-09', 'invoiceDate': '2026-09-25',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(_data(self.record, date(2026, 10, 1))['installment'], 2)
        response = self.client.patch(url, data=json.dumps({
            'month': '2026-10', 'note': '다음 달 청구 예정',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(_data(self.record, date(2026, 10, 1))['installment'], 2)
        response = self.client.patch(url, data=json.dumps({
            'month': '2026-10', 'invoiceDate': '2026-10-28',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(_data(self.record, date(2026, 11, 1))['installment'], 3)

    def test_search_includes_note_for_selected_month_only(self):
        url = f'/api/v1/sales/ledger/{self.record.pk}'
        response = self.client.patch(url, data=json.dumps({
            'month': '2026-09', 'note': '특별 네고 적용',
        }), content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        september = self.client.get('/api/v1/sales/ledger', {'month': '2026-09', 'q': '네고'}).json()
        october = self.client.get('/api/v1/sales/ledger', {'month': '2026-10', 'q': '네고'}).json()
        self.assertEqual(len(september['items']), 1)
        self.assertEqual(october['items'], [])

    def test_bad_monthly_dates_do_not_change_any_month(self):
        response = self.client.patch(f'/api/v1/sales/ledger/{self.record.pk}', data=json.dumps({
            'month': '2026-10', 'startDate': '2026-08-01', 'supplyAmount': 42,
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(SalesLedgerMonth.objects.exists())

    def test_overlap_boundaries_and_deleted_records(self):
        for source_id, start, end, deleted in [
            ('prior', date(2026,8,1), date(2026,8,31), False),
            ('first', date(2026,8,1), date(2026,9,1), False),
            ('last', date(2026,9,30), date(2026,10,5), False),
            ('future', date(2026,10,1), None, False),
            ('deleted', date(2026,9,1), None, True),
        ]:
            SalesLedgerRecord.objects.create(source_id=source_id, project_name=source_id,
                start_date=start, end_date=end, source_deleted=deleted)
        self.assertEqual(set(_records_for_month(date(2026,9,1)).values_list('source_id',flat=True)), {'long-contract','first','last'})

    def test_usage_start_controls_month_even_when_record_was_created_earlier(self):
        record = SalesLedgerRecord.objects.create(
            source_id='october-use', project_name='10월 사용 현장',
            start_date=date(2026, 10, 2), end_date=date(2026, 10, 20),
            record_date=date(2026, 9, 21),
        )
        self.assertFalse(_records_for_month(date(2026, 9, 1)).filter(pk=record.pk).exists())
        self.assertTrue(_records_for_month(date(2026, 10, 1)).filter(pk=record.pk).exists())
        self.assertEqual(_data(record, date(2026, 10, 1))['status'], '신규')

    @patch('core.views_sales._pdam_rows')
    def test_resync_corrects_old_category_and_false_ended_state(self, rows):
        self.record.category='가맹'
        self.record.save()
        franchise = SalesLedgerRecord.objects.create(source_id='franchise',project_name='장기 현장',
            start_date=date(2026,8,1),status='종료',pdam_status='종료',category='')
        rows.return_value = [
            {'source_id':'long-contract','project_name':'장기 현장','start_date':'2026-08-10','status':'진행','category':'본사'},
            {'source_id':'franchise','project_name':'장기 현장','start_date':'2026-08-01','status':'진행','category':'가맹'},
            {'source_id':'deleted','project_name':'삭제 현장','start_date':'2026-08-01','status':'진행','category':'본사','is_deleted':1},
        ]
        sync_pdam_sales_records()
        self.record.refresh_from_db(); franchise.refresh_from_db()
        self.assertEqual(self.record.category,'본사')
        self.assertEqual((franchise.category,franchise.status),('가맹','진행'))
        self.assertEqual(_records_for_month(date(2026,9,1)).count(),2)

    def test_legacy_env_query_uses_device_code_and_includes_deletion_flag(self):
        legacy="SELECT CASE WHEN COALESCE(c.fcIdx, 0) <> 0 THEN '가맹' ELSE '본사' END AS category FROM TB_DEVICE d"
        self.assertEqual(sales_query(legacy),DEFAULT_PDAM_SALES_QUERY)
        self.assertIn("d.conduct = 1 THEN '종료'",sales_query(legacy))
        self.assertIn("d.conduct = 2 THEN '가맹' WHEN d.conduct = 0 THEN '본사' ELSE ''",sales_query(legacy))
        self.assertIn('AS is_deleted',sales_query(legacy))

    @patch('core.views_sales._pdam_rows')
    def test_franchise_completion_keeps_category_and_manual_completion_survives_sync(self, rows):
        self.record.category = '가맹'
        self.record.save()
        rows.return_value = [{'source_id':'long-contract','project_name':'장기 현장',
            'start_date':'2026-08-10','status':'종료','category':'본사'}]
        sync_pdam_sales_records()
        self.record.refresh_from_db()
        self.assertEqual((self.record.category,self.record.status),('본사','종료'))
        self.record.pdam_status='진행'
        self.record.save()
        rows.return_value[0]['status']='진행'
        rows.return_value[0]['category']='가맹'
        sync_pdam_sales_records()
        self.record.refresh_from_db()
        self.assertEqual(self.record.status,'종료')

    @patch('core.views_sales._pdam_rows')
    def test_ended_source_without_category_keeps_saved_category(self, rows):
        self.record.category = '가맹'
        self.record.save()
        rows.return_value = [{'source_id': 'long-contract', 'project_name': '장기 현장',
            'start_date': '2026-08-10', 'status': '종료', 'category': ''}]
        sync_pdam_sales_records()
        self.record.refresh_from_db()
        self.assertEqual((self.record.category, self.record.status), ('가맹', '종료'))

    @patch('core.views_sales._pdam_rows')
    def test_first_seen_completed_device_has_no_category(self, rows):
        rows.return_value = [{'source_id':'ended-new','project_name':'종료 현장',
            'start_date':'2026-09-01','end_date':'2026-09-10',
            'status':'종료','category':''}]
        sync_pdam_sales_records()
        record = SalesLedgerRecord.objects.get(source_id='ended-new')
        self.assertEqual((record.status, record.category), ('종료', ''))

    @patch('core.views_sales._pdam_rows')
    def test_unchanged_sync_does_not_rewrite_every_record(self, rows):
        rows.return_value = [{
            'source_id': 'long-contract', 'project_name': '장기 현장',
            'start_date': '2026-08-10', 'end_date': '2026-12-15',
            'status': '진행', 'category': '본사',
        }]
        sync_pdam_sales_records()
        with CaptureQueriesContext(connection) as queries:
            sync_pdam_sales_records()
        updates = [query['sql'] for query in queries if query['sql'].upper().startswith('UPDATE')
                   and 'salesledgerrecord' in query['sql'].lower()]
        self.assertEqual(len(updates), 1, updates)
        self.assertNotIn('project_name', updates[0].lower())

    def test_rearchiving_replaces_file_without_random_filename_suffix(self):
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            for content in (b'first', b'second'):
                response = self.client.post('/api/v1/sales/ledger/archives', {
                    'year': '2026',
                    'file': SimpleUploadedFile('매출관리대장_2026년_연간보관.xlsx', content),
                })
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(response.json()['name'], '매출관리대장_2026년_연간보관.xlsx')
            archive = SalesLedgerArchive.objects.get(year=2026)
            self.assertEqual(archive.file.name, 'sales-ledger-archives/매출관리대장_2026년_연간보관.xlsx')
            with archive.file.open('rb') as saved:
                self.assertEqual(saved.read(), b'second')

    def test_archive_list_hides_legacy_storage_suffix(self):
        SalesLedgerArchive.objects.create(
            year=2026,
            file='sales-ledger-archives/매출관리대장_2026년_연간보관_rmROmPs.xlsx',
        )
        response = self.client.get('/api/v1/sales/ledger/archives')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['items'][0]['name'], '매출관리대장_2026년_연간보관.xlsx')
