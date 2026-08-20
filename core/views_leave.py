import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone

from .api import ApiError, endpoint, parse_json, require_fields
from .models import (
    ApprovalDocument,
    ApprovalHistory,
    ApprovalStep,
    LeaveRequest,
    PortalSetting,
    User,
)
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
@transaction.atomic
def leave_requests(request):
    user = request.api_user
    if request.method == "GET":
        rows = queryset()
        user_id = request.GET.get("userId")
        status = request.GET.get("status")
        if not user.is_staff and user.username != "ceo":
            rows = rows.filter(user=user)
        elif user_id:
            rows = rows.filter(user__username=user_id)
        if status:
            rows = rows.filter(status=status)
        return JsonResponse({"leaveRequests": [leave_data(item) for item in rows]})

    data = parse_json(request)
    require_fields(data, ["type", "startDate", "endDate", "days"])
    target = user
    direct_entry_requested = bool(data.get("directEntry", False))
    if direct_entry_requested and not user.is_staff:
        raise ApiError(
            "관리자만 휴가를 직권 등록할 수 있습니다.",
            status=403,
            code="permission_denied",
        )
    direct_entry = direct_entry_requested
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
    if not direct_entry:
        ceo = User.objects.select_related("department").filter(username="ceo").first()
        document = ApprovalDocument.objects.create(
            public_id=f"LEAVE-DOC-{leave.public_id}",
            title=f"{target.display_name} {leave.leave_type} 신청",
            drafter=target,
            department_name=target.department.name if target.department else "",
            form_name="휴가 신청서",
            status=ApprovalDocument.Status.PENDING,
            drafted_at=timezone.localdate(),
            due_date=start,
            progress=50,
            document_no=leave.public_id,
            effective_date=start,
            content=(
                f"휴가 종류: {leave.leave_type}\n기간: {start} ~ {end}\n"
                f"사용 일수: {leave.days}일\n신청 사유: {leave.reason}"
            ),
            received_request=True,
            can_cancel=False,
            can_reuse=False,
            can_edit=False,
            receivers=["대표"],
            references=["경영관리팀"],
        )
        ApprovalStep.objects.create(
            document=document,
            order=0,
            approver=target,
            name=target.display_name,
            department=target.department.name if target.department else "",
            step_type="신청",
            role=target.position,
            status="완료",
            approved_at=timezone.now(),
        )
        ApprovalStep.objects.create(
            document=document,
            order=1,
            approver=ceo,
            name=ceo.display_name if ceo else "대표",
            department=ceo.department.name if ceo and ceo.department else "경영관리팀",
            step_type="승인",
            role=ceo.position if ceo else "대표",
            status="진행중",
        )
        ApprovalHistory.objects.create(
            public_id=f"HIS-{leave.public_id}",
            document=document,
            category="휴가 신청",
            actor=target,
            actor_label=f"{target.display_name} {target.position}".strip(),
            description="휴가 신청 결재 요청",
            snapshot=f"{leave.leave_type} · {start} ~ {end}",
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
    if not request.api_user.is_staff and request.api_user.username != "ceo":
        raise ApiError("휴가 결재 권한이 필요합니다.", status=403, code="permission_denied")
    data = parse_json(request)
    with transaction.atomic():
        leave = LeaveRequest.objects.select_for_update().filter(public_id=leave_id).first()
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
        document = ApprovalDocument.objects.filter(
            public_id=f"LEAVE-DOC-{leave.public_id}"
        ).first()
        if document:
            document.status = (
                ApprovalDocument.Status.APPROVED
                if action == "approve"
                else ApprovalDocument.Status.REJECTED
            )
            document.progress = 100 if action == "approve" else document.progress
            document.save(update_fields=["status", "progress", "updated_at"])
            document.steps.filter(status="진행중").update(
                status="완료" if action == "approve" else "반려",
                approved_at=timezone.now(),
            )
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
    ApprovalDocument.objects.filter(public_id=f"LEAVE-DOC-{leave.public_id}").update(
        status=ApprovalDocument.Status.CANCELED,
        updated_at=timezone.now(),
    )
    return JsonResponse(leave_data(leave))


@endpoint(["POST"], dev_fallback=True)
def acknowledge_leave(request, leave_id):
    leave = queryset().filter(public_id=leave_id, user=request.api_user).first()
    if leave is None:
        raise ApiError("휴가 신청을 찾을 수 없습니다.", status=404, code="not_found")
    leave.acknowledged = True
    leave.save(update_fields=["acknowledged", "updated_at"])
    return JsonResponse(leave_data(leave))
