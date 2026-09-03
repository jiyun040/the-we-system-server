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


def approval_users_for(target):
    setting = PortalSetting.load()
    department_name = target.department.name if target.department else ""
    configured = setting.leave_approval_lines
    user_ids = (
        configured.get(department_name, [])
        if isinstance(configured, dict)
        else []
    )
    candidates = {
        item.username: item
        for item in User.objects.select_related("department").filter(
            username__in=user_ids,
            is_active=True,
        )
    }
    approvers = [
        candidates[user_id]
        for user_id in user_ids
        if user_id in candidates and candidates[user_id].pk != target.pk
    ]
    if approvers:
        return approvers

    fallback = (
        User.objects.select_related("department")
        .filter(username="ceo", is_active=True)
        .exclude(pk=target.pk)
        .first()
    )
    if fallback is None:
        fallback = (
            User.objects.select_related("department")
            .filter(is_staff=True, is_active=True)
            .exclude(pk=target.pk)
            .order_by("pk")
            .first()
        )
    if fallback is None:
        raise ApiError(
            "휴가 결재자를 찾을 수 없습니다. 관리자에서 부서별 휴가 결재라인을 설정해 주세요.",
            code="leave_approval_line_missing",
        )
    return [fallback]


def approval_line_data(approvers):
    return [
        {
            "userId": approver.username,
            "name": approver.display_name,
            "department": approver.department.name if approver.department else "",
            "position": approver.position,
            "status": "진행중" if index == 0 else "예정",
        }
        for index, approver in enumerate(approvers)
    ]


def can_view_leave(user, leave):
    if user.is_staff or user.username == "ceo" or leave.user_id == user.pk:
        return True
    return any(
        isinstance(step, dict) and step.get("userId") == user.username
        for step in (leave.approval_line or [])
    )


def entitlement_for_service_year(policy, service_year):
    normalized = {
        int(year): value
        for year, value in (policy or {}).items()
        if str(year).isdigit() and int(year) > 0
    }
    if not normalized:
        return 15
    applicable_years = [year for year in normalized if year <= service_year]
    selected_year = max(applicable_years) if applicable_years else min(normalized)
    return normalized[selected_year]


@endpoint(["GET", "POST"], dev_fallback=True)
@transaction.atomic
def leave_requests(request):
    user = request.api_user
    if request.method == "GET":
        rows = queryset()
        user_id = request.GET.get("userId")
        status = request.GET.get("status")
        if user_id and (user.is_staff or user.username == "ceo"):
            rows = rows.filter(user__username=user_id)
        if status:
            rows = rows.filter(status=status)
        visible_rows = [item for item in rows if can_view_leave(user, item)]
        return JsonResponse({"leaveRequests": [leave_data(item) for item in visible_rows]})

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
    approvers = [] if direct_entry else approval_users_for(target)
    approval_line = approval_line_data(approvers)
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
        approval_line=approval_line,
        direct_entry=direct_entry,
        registered_by=user if direct_entry else None,
        acknowledged=direct_entry,
    )
    if not direct_entry:
        document = ApprovalDocument.objects.create(
            public_id=f"LEAVE-DOC-{leave.public_id}",
            title=f"{target.display_name} {leave.leave_type} 신청",
            drafter=target,
            department_name=target.department.name if target.department else "",
            form_name="휴가 신청서",
            status=ApprovalDocument.Status.PENDING,
            drafted_at=timezone.localdate(),
            due_date=start,
            progress=int(100 / (len(approvers) + 1)),
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
            receivers=[approver.username for approver in approvers],
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
        for index, approver in enumerate(approvers, start=1):
            ApprovalStep.objects.create(
                document=document,
                order=index,
                approver=approver,
                name=approver.display_name,
                department=approver.department.name if approver.department else "",
                step_type="승인",
                role=approver.position,
                status="진행중" if index == 1 else "예정",
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
    completed_years = today.year - user.hire_date.year
    if (today.month, today.day) < (user.hire_date.month, user.hire_date.day):
        completed_years -= 1
    service_year = max(1, completed_years)
    policy = setting.annual_leave_by_year
    entitlement = entitlement_for_service_year(policy, service_year)
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
    data = parse_json(request)
    with transaction.atomic():
        leave = LeaveRequest.objects.select_for_update().filter(public_id=leave_id).first()
        if leave is None:
            raise ApiError("휴가 신청을 찾을 수 없습니다.", status=404, code="not_found")
        if leave.status != LeaveRequest.Status.PENDING:
            raise ApiError("이미 처리된 휴가 신청입니다.", status=409, code="invalid_state")
        line = [dict(step) for step in (leave.approval_line or []) if isinstance(step, dict)]
        current_index = next(
            (index for index, step in enumerate(line) if step.get("status") == "진행중"),
            None,
        )
        if current_index is not None:
            if line[current_index].get("userId") != request.api_user.username:
                raise ApiError(
                    "현재 순서의 휴가 결재자만 처리할 수 있습니다.",
                    status=403,
                    code="permission_denied",
                )
        elif not request.api_user.is_staff and request.api_user.username != "ceo":
            raise ApiError("휴가 결재 권한이 필요합니다.", status=403, code="permission_denied")

        final_approval = current_index is None or current_index == len(line) - 1
        if action == "approve":
            if current_index is not None:
                line[current_index]["status"] = "완료"
                if not final_approval:
                    line[current_index + 1]["status"] = "진행중"
            leave.status = (
                LeaveRequest.Status.APPROVED
                if final_approval
                else LeaveRequest.Status.PENDING
            )
            leave.ceo_status = "완료" if final_approval else "진행중"
            leave.rejected_by = ""
        else:
            if current_index is not None:
                line[current_index]["status"] = "반려"
            leave.status = LeaveRequest.Status.REJECTED
            leave.ceo_status = "반려"
            leave.rejected_by = request.api_user.display_name
            reason = str(data.get("reason") or "").strip()
            if reason:
                leave.reason = f"{leave.reason}\n반려 사유: {reason}".strip()
        leave.approval_line = line
        leave.save()
        document = ApprovalDocument.objects.filter(
            public_id=f"LEAVE-DOC-{leave.public_id}"
        ).first()
        if document:
            document.status = (
                ApprovalDocument.Status.APPROVED
                if action == "approve" and final_approval
                else ApprovalDocument.Status.PENDING
                if action == "approve"
                else ApprovalDocument.Status.REJECTED
            )
            document.progress = (
                100
                if action == "approve" and final_approval
                else int(((current_index or 0) + 1) / max(len(line), 1) * 100)
                if action == "approve"
                else document.progress
            )
            document.save(update_fields=["status", "progress", "updated_at"])
            current_step = document.steps.filter(status="진행중").first()
            if current_step:
                current_step.status = "완료" if action == "approve" else "반려"
                current_step.approved_at = timezone.now()
                current_step.save(update_fields=["status", "approved_at"])
            if action == "approve" and not final_approval:
                next_step = document.steps.filter(status="예정").order_by("order").first()
                if next_step:
                    next_step.status = "진행중"
                    next_step.save(update_fields=["status"])
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
