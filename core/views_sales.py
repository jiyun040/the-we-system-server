from copy import copy
import re

from datetime import date, datetime, timedelta

import pymysql
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, JsonResponse
from django.utils import timezone

from .api import ApiError, endpoint, parse_json
from .models import SalesLedgerArchive, SalesLedgerRecord, SalesLedgerMonth
from .pdam_sales import sales_query


def _parse_month(value):
    try:
        return datetime.strptime(value, "%Y-%m").date().replace(day=1)
    except (TypeError, ValueError) as exc:
        raise ApiError("month는 YYYY-MM 형식이어야 합니다.", fields={"month": "형식을 확인해 주세요."}) from exc


def _archive_name(archive):
    name = archive.file.name.rsplit("/", 1)[-1]
    default = f"매출관리대장_{archive.year}년_연간보관"
    if re.fullmatch(rf"{re.escape(default)}_[A-Za-z0-9]{{7}}\.xlsx", name):
        return f"{default}.xlsx"
    return name


@endpoint(["GET", "POST", "PATCH", "DELETE"])
def ledger_archives(request):
    if request.method == "GET":
        items = [
            {
                "year": archive.year,
                "name": _archive_name(archive),
                "updatedAt": archive.updated_at.isoformat(),
            }
            for archive in SalesLedgerArchive.objects.order_by("-year")
        ]
        return JsonResponse({"items": items})
    if request.method in {"PATCH", "DELETE"}:
        try:
            year = int(request.GET.get("year", ""))
            archive = SalesLedgerArchive.objects.get(year=year)
        except (TypeError, ValueError, SalesLedgerArchive.DoesNotExist) as exc:
            raise ApiError("해당 연도 보관 파일이 없습니다.", status=404, code="not_found") from exc
        if request.method == "DELETE":
            archive.file.delete(save=False)
            archive.delete()
            return JsonResponse({"deleted": year})
        data = parse_json(request)
        name = str(data.get("name", "")).strip()
        if not name:
            raise ApiError("파일 이름을 입력해 주세요.")
        if not name.lower().endswith(".xlsx"):
            name += ".xlsx"
        old_name = archive.file.name
        new_name = f"sales-ledger-archives/{name}"
        if old_name != new_name:
            if archive.file.storage.exists(new_name):
                raise ApiError("이미 사용 중인 파일 이름입니다.")
            with archive.file.open("rb") as source:
                saved_name = archive.file.storage.save(new_name, source)
            archive.file.name = saved_name
            archive.save(update_fields=["file", "updated_at"])
            archive.file.storage.delete(old_name)
        else:
            archive.save(update_fields=["updated_at"])
        return JsonResponse({"year": year, "name": archive.file.name.rsplit("/", 1)[-1]})
    try:
        year = int(request.POST.get("year", ""))
    except (TypeError, ValueError) as exc:
        raise ApiError("year는 연도 숫자여야 합니다.", fields={"year": "형식을 확인해 주세요."}) from exc
    uploaded = request.FILES.get("file")
    if not uploaded:
        raise ApiError("엑셀 파일을 첨부해 주세요.", fields={"file": "필수 항목입니다."})
    archive, _ = SalesLedgerArchive.objects.get_or_create(year=year)
    old_name = archive.file.name
    target = f"sales-ledger-archives/매출관리대장_{year}년_연간보관.xlsx"
    storage = archive.file.storage
    if storage.exists(target):
        storage.delete(target)
    archive.file.name = storage.save(target, uploaded)
    archive.save(update_fields=["file", "updated_at"])
    if old_name and old_name != archive.file.name:
        storage.delete(old_name)
    return JsonResponse({"year": archive.year, "name": archive.file.name.rsplit("/", 1)[-1]})


@endpoint(["GET"])
def ledger_archive_download(request, year):
    try:
        archive = SalesLedgerArchive.objects.get(year=year)
    except SalesLedgerArchive.DoesNotExist as exc:
        raise ApiError("해당 연도 보관 파일이 없습니다.", status=404, code="not_found") from exc
    response = FileResponse(archive.file.open("rb"), as_attachment=True, filename=f"매출관리대장_{year}년_연간보관.xlsx")
    return response


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
    query = sales_query(settings.PDAM_SALES_QUERY)
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
            "record_date": _to_date(source.get("record_date")) or start_date,
            "end_date": _to_date(source.get("end_date")),
            "pdam_status": pdam_status,
            "source_category": source_category,
            "source_deleted": str(source.get("is_deleted", 0)).lower() in {"1", "true"},
        }
        record = existing.get(source_id)
        if record is None:
            creates.append(SalesLedgerRecord(
                source_id=source_id,
                category=source_category if source_category in {"본사", "가맹"} else "",
                status="종료" if pdam_status == "종료" else "신규",
                **source_fields,
            ))
            continue
        previous_pdam_status = record.pdam_status
        previous_status = record.status
        changed = any(getattr(record, field) != value for field, value in source_fields.items())
        for field, value in source_fields.items():
            setattr(record, field, value)
        if pdam_status == "종료":
            record.status = "종료"
        elif previous_pdam_status == "종료":
            record.status = "진행"
        # 종료된 행에 분류가 비어 있어도 기존 본사/가맹 분류를 유지한다.
        category = source_category if source_category in {"본사", "가맹"} else record.category
        changed = changed or record.category != category or record.status != previous_status
        record.category = category
        if changed:
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
                ["project_name", "contractor", "partner", "elevator", "start_date", "record_date", "end_date", "pdam_status", "source_category", "source_deleted", "status", "category", "updated_at"],
                batch_size=500,
            )
        elif not creates and existing:
            # Keep the refresh timestamp without rewriting every unchanged row.
            SalesLedgerRecord.objects.filter(pk=next(iter(existing.values())).pk).update(updated_at=synced_at)


def sync_pdam_sales_records_if_stale():
    latest = SalesLedgerRecord.objects.order_by("-updated_at").values_list("updated_at", flat=True).first()
    if latest and timezone.now() - latest < timedelta(minutes=5):
        return
    sync_pdam_sales_records()


MONTH_FIELDS = (
    "start_date", "end_date", "billing_date", "invoice_date", "deposit_date",
    "invoice_issuer", "supply_amount", "adjustment_amount", "adjustment_reason",
    "installment", "status", "note",
)


def _monthly_record(source, month):
    if getattr(source, "ledger_month", None) == month:
        return source
    record = copy(source)
    record.ledger_month = month
    record.contract_start_date = source.start_date
    record.contract_end_date = source.end_date
    months = list(source.months.all())
    saved = next((item for item in months if item.month == month), None)
    prior_issued = [item.installment for item in months if item.month < month and item.invoice_date]
    if source.invoice_date and source.invoice_date.replace(day=1) < month and not any(
        item.month == source.invoice_date.replace(day=1) for item in months
    ):
        prior_issued.append(source.installment)
    month_delta = (month.year - source.start_date.year) * 12 + month.month - source.start_date.month
    # 계산서가 아직 발행되지 않은 현장은 1회차를 유지하고,
    # 이전 월까지 발행된 경우 시작 월부터 경과한 회차를 적용한다.
    next_installment = max(1, month_delta) if prior_issued else 1
    ended = source.pdam_status == "종료" or source.status == "종료"
    record.start_date = max(source.start_date, month)
    record.end_date = min(source.end_date, _month_end(month)) if ended and source.end_date else _month_end(month)
    record.status = "종료" if ended and (not source.end_date or source.end_date <= _month_end(month)) else "진행" if source.start_date < month else "신규"
    if saved:
        for field in MONTH_FIELDS:
            if field not in {"start_date", "end_date", "status"}:
                setattr(record, field, getattr(saved, field))
        record.start_date = saved.start_date or record.start_date
        record.end_date = min(saved.end_date, record.end_date) if saved.end_date else record.end_date
        if saved.status == "종료" and record.status != "종료":
            record.status = "종료"
        if not saved.invoice_date:
            record.installment = next_installment
    elif months or (source.billing_date and source.billing_date.replace(day=1) != month):
        record.billing_date = record.invoice_date = record.deposit_date = None
        record.supply_amount = record.adjustment_amount = 0
        record.adjustment_reason = ""
        record.installment = next_installment
    return record


def _data(record, month=None):
    if month is not None:
        record = _monthly_record(record, month)
    return {
        "id": str(record.pk), "projectName": record.project_name,
        "month": month.strftime("%Y-%m") if month else "",
        "contractStartDate": getattr(record, "contract_start_date", record.start_date).isoformat(),
        "contractEndDate": (getattr(record, "contract_end_date", record.end_date) or "").isoformat() if getattr(record, "contract_end_date", record.end_date) else "",
        "recordDate": (record.record_date or record.start_date).isoformat(),
        "contractor": record.contractor, "partner": record.partner,
        "elevator": record.elevator, "startDate": record.start_date.isoformat(),
        "endDate": record.end_date.isoformat() if record.end_date else "",
        "category": record.category, "billingDate": record.billing_date.isoformat() if record.billing_date else "",
        "invoiceDate": record.invoice_date.isoformat() if record.invoice_date else "",
        "depositDate": record.deposit_date.isoformat() if record.deposit_date else "",
        "supplyAmount": record.supply_amount, "installment": record.installment,
        "adjustmentAmount": record.adjustment_amount,
        "adjustmentReason": record.adjustment_reason,
        "status": record.status, "note": record.note,
        "invoiceIssuer": record.invoice_issuer.strip() or "협력사",
    }


def _records_for_month(month, query="", status=""):
    # This condition includes monthly carry-over projects; the selected month is
    # anchored by use-start date and constrained by the end date when present.
    records = SalesLedgerRecord.objects.filter(
        source_deleted=False, start_date__lte=_month_end(month)
    ).filter(
        Q(end_date__isnull=True)
        | Q(end_date__gte=month)
        | Q(months__month=month)
    ).distinct()
    if query:
        records = records.filter(Q(project_name__icontains=query) | Q(contractor__icontains=query) | Q(partner__icontains=query))
    if status:
        records = records.filter(status=status)
    return records.prefetch_related("months").order_by("project_name", "elevator", "id")


@endpoint(["GET"])
def ledger(request):
    month = _parse_month(request.GET.get("month"))
    sync_pdam_sales_records_if_stale()
    records = list(_records_for_month(month))
    records = [_monthly_record(item, month) for item in records]
    query = request.GET.get("q", "").strip().casefold()
    if query:
        records = [item for item in records if any(
            query in value.casefold()
            for value in (item.project_name, item.contractor, item.partner, item.note)
        )]
    requested_status = request.GET.get("status", "").strip()
    if requested_status:
        records = [item for item in records if item.status == requested_status]
    records.sort(key=lambda item: (item.category == "가맹", item.project_name, item.elevator))
    billed = [item for item in records if item.billing_date]
    unpaid = [item for item in billed if not item.deposit_date]
    return JsonResponse({"items": [_data(item, month) for item in records], "summary": {
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
    month = _parse_month(data["month"]) if data.get("month") else None
    source_record = record
    if month:
        if record.start_date > _month_end(month) or (record.end_date and record.end_date < month):
            raise ApiError("해당 월의 사용 항목이 아닙니다.")
        record = _monthly_record(record, month)
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
    if record.pdam_status == "종료" and (not month or not source_record.end_date or source_record.end_date <= _month_end(month)):
        status = "종료"
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
    try:
        adjustment_amount = int(data.get("adjustmentAmount", record.adjustment_amount) or 0)
    except (TypeError, ValueError) as exc:
        raise ApiError("조정액을 숫자로 입력해 주세요.") from exc
    if adjustment_amount < 0:
        raise ApiError("조정액은 0 이상이어야 합니다.")
    adjustment_reason = data.get("adjustmentReason", record.adjustment_reason)
    if not isinstance(adjustment_reason, str) or len(adjustment_reason.strip()) > 500:
        raise ApiError("조정사항은 500자 이내로 입력해 주세요.")
    invoice_issuer = data.get("invoiceIssuer", record.invoice_issuer)
    if not isinstance(invoice_issuer, str) or len(invoice_issuer.strip()) > 120:
        raise ApiError("계산서 발행처는 120자 이내로 입력해 주세요.", fields={"invoiceIssuer": "120자 이내 문자열이어야 합니다."})
    with transaction.atomic():
        record.invoice_issuer = invoice_issuer.strip() or "협력사"
        record.category = category
        record.billing_date = _to_date(data.get("billingDate", record.billing_date))
        record.invoice_date = _to_date(data.get("invoiceDate", record.invoice_date))
        record.deposit_date = _to_date(data.get("depositDate", record.deposit_date))
        record.supply_amount, record.installment, record.status = supply_amount, installment, status
        record.adjustment_amount = adjustment_amount
        record.adjustment_reason = adjustment_reason.strip()
        record.note = str(data.get("note", record.note)).strip()[:500]
        if month:
            for field, key in [("start_date", "startDate"), ("end_date", "endDate")]:
                value = _to_date(data.get(key)) if key in data else getattr(record, field)
                if value is None or not month <= value <= _month_end(month):
                    raise ApiError("사용일은 선택한 월 안의 날짜여야 합니다.")
                setattr(record, field, value)
            if record.end_date < record.start_date:
                raise ApiError("사용 종료일은 시작일 이후여야 합니다.")
            SalesLedgerMonth.objects.update_or_create(
                record=source_record, month=month,
                defaults={field: getattr(record, field) for field in MONTH_FIELDS},
            )
            source_record.category = category
            source_record.save(update_fields=["category", "updated_at"])
        else:
            record.save()
    return JsonResponse(_data(record, month))


@endpoint(["GET"])
def statements(request):
    month = _parse_month(request.GET.get("month"))
    project_name = request.GET.get("projectName", "").strip()
    if not project_name:
        raise ApiError("공사명이 필요합니다.", fields={"projectName": "필수 항목입니다."})
    sync_pdam_sales_records_if_stale()
    items = _records_for_month(month).filter(project_name=project_name)
    return JsonResponse({"projectName": project_name, "items": [_data(item, month) for item in items]})
