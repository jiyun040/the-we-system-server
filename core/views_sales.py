from datetime import date, datetime, timedelta

import pymysql
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone

from .api import ApiError, endpoint, parse_json
from .models import SalesLedgerRecord


def _parse_month(value):
    try:
        return datetime.strptime(value, "%Y-%m").date().replace(day=1)
    except (TypeError, ValueError) as exc:
        raise ApiError("month는 YYYY-MM 형식이어야 합니다.", fields={"month": "형식을 확인해 주세요."}) from exc


def _month_end(month):
    return date(month.year + (month.month == 12), (month.month % 12) + 1, 1) - date.resolution


def _to_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def _pdam_rows():
    """Return rows directly from the configured PDAM DB, never through HTTP."""
    query = settings.PDAM_SALES_QUERY
    if not query or not settings.PDAM_DB_NAME:
        return []
    if not query.lstrip().lower().startswith("select"):
        raise ApiError("PDAM_SALES_QUERY는 SELECT 문만 허용합니다.", status=500)
    try:
        connection = pymysql.connect(
            host=settings.PDAM_DB_HOST,
            port=settings.PDAM_DB_PORT,
            user=settings.PDAM_DB_USER,
            password=settings.PDAM_DB_PASSWORD,
            database=settings.PDAM_DB_NAME,
            connect_timeout=10,
            read_timeout=30,
            charset="utf8mb4",
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                names = [column[0] for column in cursor.description]
                return [dict(zip(names, values)) for values in cursor.fetchall()]
        finally:
            connection.close()
    except pymysql.MySQLError as exc:
        raise ApiError(
            "PDAM DB에 연결하지 못했습니다. .env의 접속 정보를 확인해 주세요.",
            status=503,
            code="pdam_connection_failed",
        ) from exc


def sync_pdam_sales_records():
    """Bulk-upsert PDAM rows without blocking the web server per device."""
    sources = _pdam_rows()
    source_ids = [str(item.get("source_id") or "").strip() for item in sources]
    existing = SalesLedgerRecord.objects.in_bulk(
        [source_id for source_id in source_ids if source_id], field_name="source_id"
    )
    creates, updates = [], []
    for source in sources:
        source_id = str(source.get("source_id") or "").strip()
        project_name = str(source.get("project_name") or "").strip()
        start_date = _to_date(source.get("start_date"))
        if not source_id or not project_name or start_date is None:
            continue
        pdam_status = str(source.get("status") or "").strip()
        source_category = str(source.get("category") or "").strip()
        source_fields = {
            "project_name": project_name,
            "contractor": str(source.get("contractor") or "").strip(),
            "partner": str(source.get("partner") or "").strip(),
            "elevator": str(source.get("elevator") or "").strip(),
            "start_date": start_date,
            "end_date": _to_date(source.get("end_date")),
            "pdam_status": pdam_status,
            "source_category": source_category,
        }
        record = existing.get(source_id)
        if record is None:
            creates.append(SalesLedgerRecord(
                source_id=source_id,
                category="" if pdam_status == "종료" else source_category if source_category in {"본사", "가맹"} else "",
                status="종료" if pdam_status == "종료" else "신규",
                **source_fields,
            ))
            continue
        for field, value in source_fields.items():
            setattr(record, field, value)
        if pdam_status == "종료":
            record.status, record.category = "종료", ""
        updates.append(record)
    synced_at = timezone.now()
    for record in updates:
        record.updated_at = synced_at
    with transaction.atomic():
        if creates:
            SalesLedgerRecord.objects.bulk_create(creates, batch_size=500)
        if updates:
            SalesLedgerRecord.objects.bulk_update(
                updates,
                ["project_name", "contractor", "partner", "elevator", "start_date", "end_date", "pdam_status", "source_category", "status", "category", "updated_at"],
                batch_size=500,
            )


def sync_pdam_sales_records_if_stale():
    latest = SalesLedgerRecord.objects.order_by("-updated_at").values_list("updated_at", flat=True).first()
    if latest and timezone.now() - latest < timedelta(minutes=5):
        return
    sync_pdam_sales_records()


def _data(record):
    return {
        "id": str(record.pk), "projectName": record.project_name,
        "contractor": record.contractor, "partner": record.partner,
        "elevator": record.elevator, "startDate": record.start_date.isoformat(),
        "endDate": record.end_date.isoformat() if record.end_date else "",
        "category": record.category, "billingDate": record.billing_date.isoformat() if record.billing_date else "",
        "invoiceDate": record.invoice_date.isoformat() if record.invoice_date else "",
        "depositDate": record.deposit_date.isoformat() if record.deposit_date else "",
        "supplyAmount": record.supply_amount, "installment": record.installment,
        "status": record.status, "note": record.note,
        "invoiceIssuer": record.invoice_issuer,
    }


def _records_for_month(month, query="", status=""):
    # This condition includes monthly carry-over projects; the selected month is
    # anchored by use-start date and constrained by the end date when present.
    records = SalesLedgerRecord.objects.filter(start_date__lte=_month_end(month)).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=month)
    )
    if query:
        records = records.filter(Q(project_name__icontains=query) | Q(contractor__icontains=query) | Q(partner__icontains=query))
    if status:
        records = records.filter(status=status)
    return records.order_by("project_name", "elevator", "id")


@endpoint(["GET"])
def ledger(request):
    month = _parse_month(request.GET.get("month"))
    sync_pdam_sales_records_if_stale()
    records = list(_records_for_month(month, request.GET.get("q", "").strip(), request.GET.get("status", "").strip()))
    records.sort(key=lambda item: (item.category == "가맹", item.project_name, item.elevator))
    billed = [item for item in records if item.billing_date]
    unpaid = [item for item in billed if not item.deposit_date]
    return JsonResponse({"items": [_data(item) for item in records], "summary": {
        "supplyAmount": sum(item.supply_amount for item in records), "billCount": len(billed),
        "unbilledCount": len(records) - len(billed),
        "unissuedInvoiceCount": sum(1 for item in billed if not item.invoice_date),
        "unpaidAmount": sum(item.supply_amount for item in unpaid),
    }})


@endpoint(["PATCH"])
def ledger_detail(request, record_id):
    try:
        record = SalesLedgerRecord.objects.get(pk=record_id)
    except SalesLedgerRecord.DoesNotExist as exc:
        raise ApiError("청구 항목을 찾을 수 없습니다.", status=404, code="not_found") from exc
    data = parse_json(request)
    category = str(data.get("category", record.category)).strip()
    if category not in {"", "본사", "가맹"}:
        raise ApiError("분류는 본사 또는 가맹만 선택할 수 있습니다.")
    try:
        installment = int(data.get("installment", record.installment) or 1)
    except (TypeError, ValueError) as exc:
        raise ApiError("회차를 숫자로 입력해 주세요.") from exc
    if installment < 1:
        raise ApiError("회차는 1회차부터 입력해 주세요.", fields={"installment": "1 이상이어야 합니다."})
    requested_status = str(data.get("status", record.status))
    if record.pdam_status == "종료":
        status, category = "종료", ""
    elif requested_status in {"신규", "진행", "종료"}:
        status = requested_status
    else:
        status = "진행" if installment >= 2 else "신규"
    try:
        supply_amount = int(data.get("supplyAmount", record.supply_amount) or 0)
    except (TypeError, ValueError) as exc:
        raise ApiError("공급가를 숫자로 입력해 주세요.") from exc
    if supply_amount < 0:
        raise ApiError("공급가는 0 이상이어야 합니다.")
    invoice_issuer = data.get("invoiceIssuer", record.invoice_issuer)
    if not isinstance(invoice_issuer, str) or len(invoice_issuer.strip()) > 120:
        raise ApiError("계산서 발행처는 120자 이내로 입력해 주세요.", fields={"invoiceIssuer": "120자 이내 문자열이어야 합니다."})
    with transaction.atomic():
        record.invoice_issuer = invoice_issuer.strip()
        record.category = category
        record.billing_date = _to_date(data.get("billingDate"))
        record.invoice_date = _to_date(data.get("invoiceDate"))
        record.deposit_date = _to_date(data.get("depositDate"))
        record.supply_amount, record.installment, record.status = supply_amount, installment, status
        record.note = str(data.get("note", "")).strip()[:500]
        record.save()
    return JsonResponse(_data(record))


@endpoint(["GET"])
def statements(request):
    month = _parse_month(request.GET.get("month"))
    project_name = request.GET.get("projectName", "").strip()
    if not project_name:
        raise ApiError("공사명이 필요합니다.", fields={"projectName": "필수 항목입니다."})
    sync_pdam_sales_records_if_stale()
    items = _records_for_month(month).filter(project_name=project_name)
    return JsonResponse({"projectName": project_name, "items": [_data(item) for item in items]})
