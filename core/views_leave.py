import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone

from .api import ApiError, endpoint, parse_json, require_fields
from .models import LeaveRequest, PortalSetting, User
from .serializers import leave_data


def parse_date(value, field):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ApiError(
            f"{field}은(는) YYYY-MM-DD 형식이어야 합니다.",
            fields={field: "잘못된 날짜입니다."},
        ) from exc


def parse_days(value):
    try:
        days = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ApiError("휴가 일수를 확인해 주세요.", fields={"days": "숫자여야 합니다."}) from exc
    if days <= 0 or days > 365:
        raise ApiError("휴가 일수는 0일보다 크고 365일 이하여야 합니다.", fields={"days": "범위를 벗어났습니다."})
    return days


def next_leave_id():
    return f"LEAVE-{timezone.localdate():%y%m%d}-{uuid.uuid4().hex[:6].upper()}"


def queryset():
    return LeaveRequest.objects.select_related(
        "user", "user__department", "registered_by"
    )


@endpoint(["GET", "POST"], dev_fallback=True)
def leave_requests(request):
    user = request.api_user
    if request.method == "GET":
        rows = queryset()
        user_id = request.GET.get("userId")
        status = request.GET.get("status")
        if not user.is_staff:
            rows = rows.filter(user=user)
        elif user_id:
            rows = rows.filter(user__username=user_id)
        if status:
            rows = rows.filter(status=status)
        return JsonResponse({"leaveRequests": [leave_data(item) for item in rows]})

    data = parse_json(request)
    require_fields(data, ["type", "startDate", "endDate", "days"])
    target = user
    direct_entry = bool(data.get("directEntry", False))
    requested_user_id = str(data.get("userId") or "").strip()
    if requested_user_id and requested_user_id != user.username:
        if not user.is_staff:
            raise ApiError("다른 직원의 휴가를 등록할 권한이 없습니다.", status=403, code="permission_denied")
        target = User.objects.filter(username=requested_user_id, is_active=True).first()
        if target is None:
            raise ApiError("직원을 찾을 수 없습니다.", status=404, code="user_not_found")
        direct_entry = True
    start = parse_date(data["startDate"], "startDate")
    end = parse_date(data["endDate"], "endDate")
    if end < start:
        raise ApiError("종료일은 시작일보다 빠를 수 없습니다.", fields={"endDate": "날짜 범위를 확인해 주세요."})
    leave = LeaveRequest.objects.create(
        public_id=next_leave_id(),
        user=target,
        leave_type=str(data["type"]).strip(),
        start_date=start,
        end_date=end,
        days=parse_days(data["days"]),
        reason=str(data.get("reason") or "").strip(),
        status=LeaveRequest.Status.APPROVED if direct_entry else LeaveRequest.Status.PENDING,
        ceo_status="완료" if direct_entry else "진행중",
        direct_entry=direct_entry,
        registered_by=user if direct_entry else None,
        acknowledged=direct_entry,
    )
    return JsonResponse(leave_data(queryset().get(pk=leave.pk)), status=201)


@endpoint(["GET"], dev_fallback=True)
def leave_summary(request):
    user = request.api_user
    requested_user_id = str(request.GET.get("userId") or "").strip()
    if requested_user_id and requested_user_id != user.username:
        if not user.is_staff:
            raise ApiError("다른 직원의 휴가 현황을 볼 수 없습니다.", status=403, code="permission_denied")
        user = User.objects.filter(username=requested_user_id, is_active=True).first()
        if user is None:
            raise ApiError("직원을 찾을 수 없습니다.", status=404, code="user_not_found")
    setting = PortalSetting.load()
    today = timezone.localdate()
    service_year = max(1, today.year - user.hire_date.year + 1)
    policy = setting.annual_leave_by_year
    entitlement = policy.get(str(min(service_year, 10)), policy.get("10", 15))
    approved = user.leave_requests.filter(status=LeaveRequest.Status.APPROVED)
    pending = user.leave_requests.filter(status=LeaveRequest.Status.PENDING)
    used = sum((item.days for item in approved), Decimal("0"))
    pending_days = sum((item.days for item in pending), Decimal("0"))
    return JsonResponse({
        "userId": user.username,
        "year": today.year,
        "serviceYear": service_year,
        "entitlement": float(entitlement),
        "used": float(used),
        "pending": float(pending_days),
        "remaining": float(Decimal(str(entitlement)) - used),
    })


@endpoint(["POST"], dev_fallback=True)
def act_on_leave(request, leave_id, action):
    if not request.api_user.is_staff:
        raise ApiError("관리자 권한이 필요합니다.", status=403, code="permission_denied")
    data = parse_json(request)
    with transaction.atomic():
        leave = queryset().select_for_update().filter(public_id=leave_id).first()
        if leave is None:
            raise ApiError("휴가 신청을 찾을 수 없습니다.", status=404, code="not_found")
        if leave.status != LeaveRequest.Status.PENDING:
            raise ApiError("이미 처리된 휴가 신청입니다.", status=409, code="invalid_state")
        if action == "approve":
            leave.status = LeaveRequest.Status.APPROVED
            leave.ceo_status = "완료"
            leave.rejected_by = ""
        else:
            leave.status = LeaveRequest.Status.REJECTED
            leave.ceo_status = "반려"
            leave.rejected_by = request.api_user.display_name
            reason = str(data.get("reason") or "").strip()
            if reason:
                leave.reason = f"{leave.reason}\n반려 사유: {reason}".strip()
        leave.save()
    return JsonResponse(leave_data(queryset().get(pk=leave.pk)))


@endpoint(["POST"], dev_fallback=True)
def cancel_leave(request, leave_id):
    leave = queryset().filter(public_id=leave_id).first()
    if leave is None:
        raise ApiError("휴가 신청을 찾을 수 없습니다.", status=404, code="not_found")
    if leave.user_id != request.api_user.id and not request.api_user.is_staff:
        raise ApiError("휴가 신청을 취소할 권한이 없습니다.", status=403, code="permission_denied")
    if leave.status != LeaveRequest.Status.PENDING:
        raise ApiError("승인 대기 중인 신청만 취소할 수 있습니다.", status=409, code="invalid_state")
    leave.status = LeaveRequest.Status.CANCELED
    leave.ceo_status = "취소"
    leave.save(update_fields=["status", "ceo_status", "updated_at"])
    return JsonResponse(leave_data(leave))


@endpoint(["POST"], dev_fallback=True)
def acknowledge_leave(request, leave_id):
    leave = queryset().filter(public_id=leave_id, user=request.api_user).first()
    if leave is None:
        raise ApiError("휴가 신청을 찾을 수 없습니다.", status=404, code="not_found")
    leave.acknowledged = True
    leave.save(update_fields=["acknowledged", "updated_at"])
    return JsonResponse(leave_data(leave))
