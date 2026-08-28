import base64
import binascii
import uuid
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.utils import timezone

from .api import ApiError, endpoint, parse_json, require_fields
from .models import (
    ApprovalAttachment,
    ApprovalDocument,
    ApprovalFormTemplate,
    ApprovalHistory,
    ApprovalStep,
    PortalSetting,
    User,
)
from .serializers import document_data, form_data


def parse_date(value, field, default=None):
    if value in (None, "") and default is not None:
        return default
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ApiError(
            f"{field}은(는) YYYY-MM-DD 형식이어야 합니다.",
            fields={field: "잘못된 날짜입니다."},
        ) from exc


def document_queryset():
    return ApprovalDocument.objects.select_related(
        "drafter", "drafter__department", "form_template"
    ).prefetch_related("steps", "histories", "attachments")


def can_read(user, document):
    if user.is_staff:
        return True
    if document.drafter_id == user.id:
        return True
    if document.steps.filter(approver=user).exists():
        return True
    department = user.department.name if user.department else ""
    if document.department_visible and department == document.department_name:
        return True
    labels = {user.username, user.display_name, department}
    audience = set(document.receivers + document.references + document.viewers)
    return bool(labels & audience)


def history(document, actor, description, category="결재문서 변경"):
    return ApprovalHistory.objects.create(
        public_id=f"HIS-{uuid.uuid4().hex[:16].upper()}",
        document=document,
        category=category,
        actor=actor,
        actor_label=f"{actor.display_name} {actor.position}".strip(),
        description=description,
        snapshot=document.title,
    )


def next_public_id(prefix="APR"):
    today = timezone.localdate()
    base = f"{prefix}-{today:%y%m}-"
    latest = ApprovalDocument.objects.filter(public_id__startswith=base).order_by("public_id").last()
    try:
        number = int(latest.public_id.rsplit("-", 1)[-1]) + 1 if latest else 1
    except ValueError:
        number = ApprovalDocument.objects.filter(public_id__startswith=base).count() + 1
    while ApprovalDocument.objects.filter(public_id=f"{base}{number:03d}").exists():
        number += 1
    return f"{base}{number:03d}"


def validate_attachments(items):
    if not isinstance(items, list):
        raise ApiError("attachments는 배열이어야 합니다.", fields={"attachments": "잘못된 형식입니다."})
    cleaned = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ApiError("첨부파일 형식을 확인해 주세요.")
        name = str(item.get("name") or "").strip()
        encoded = str(item.get("base64Data") or "")
        if not name:
            raise ApiError("첨부파일 이름이 필요합니다.", fields={f"attachments.{index}.name": "필수 항목입니다."})
        if len(encoded) > 14_000_000:
            raise ApiError("첨부파일은 개별 10MB 이하만 등록할 수 있습니다.", status=413, code="file_too_large")
        try:
            if encoded:
                base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ApiError("첨부파일 데이터가 올바른 Base64가 아닙니다.") from exc
        cleaned.append({
            "name": name,
            "mime_type": str(item.get("mimeType") or "application/octet-stream"),
            "base64_data": encoded,
        })
    return cleaned


def replace_attachments(document, items):
    cleaned = validate_attachments(items)
    document.attachments.all().delete()
    ApprovalAttachment.objects.bulk_create(
        [ApprovalAttachment(document=document, **item) for item in cleaned]
    )


def replace_steps(document, supplied, drafter):
    document.steps.all().delete()
    if not supplied:
        approver = User.objects.filter(is_active=True, is_staff=True).exclude(pk=drafter.pk).first()
        if approver is None and not drafter.is_staff:
            approver = User.objects.filter(is_active=True).exclude(pk=drafter.pk).first()
        supplied = [{
            "name": drafter.display_name,
            "department": drafter.department.name if drafter.department else "",
            "type": "신청",
            "role": drafter.position,
            "status": "완료",
            "approverId": drafter.username,
        }]
        if approver:
            supplied.append({
                "name": approver.display_name,
                "department": approver.department.name if approver.department else "",
                "type": "승인",
                "role": approver.position,
                "status": "결재 예정",
                "approverId": approver.username,
            })
    rows = []
    for index, item in enumerate(supplied):
        if not isinstance(item, dict):
            raise ApiError("결재선 형식을 확인해 주세요.")
        approver_id = str(item.get("approverId") or "")
        approver = User.objects.filter(username=approver_id).first() if approver_id else None
        rows.append(ApprovalStep(
            document=document,
            order=index,
            approver=approver,
            name=str(item.get("name") or (approver.display_name if approver else "")),
            department=str(item.get("department") or (approver.department.name if approver and approver.department else "")),
            step_type=str(item.get("type") or "결재"),
            role=str(item.get("role") or (approver.position if approver else "")),
            status=str(item.get("status") or ("완료" if index == 0 else "예정")),
            delegated_by=str(item.get("delegatedBy") or ""),
            requires_original_approval=bool(item.get("requiresOriginalApproval", False)),
        ))
    ApprovalStep.objects.bulk_create(rows)


def set_progress(document):
    steps = list(document.steps.all())
    document.progress = round(sum(step.status == "완료" for step in steps) / len(steps) * 100) if steps else 0


@endpoint(["GET"], auth=False, dev_fallback=True)
def dashboard(request):
    user = request.api_user
    forms = ApprovalFormTemplate.objects.filter(is_enabled=True).order_by("-recent_count", "name")[:5]
    if user is None:
        return JsonResponse({
            "pendingCount": 0, "receivedCount": 0, "referenceCount": 0, "scheduledCount": 0,
            "frequentForms": [form_data(form) for form in forms],
            "processingDocuments": [], "waitingDocuments": [],
        })
    documents = list(document_queryset().exclude(status=ApprovalDocument.Status.DRAFT))
    readable = [doc for doc in documents if can_read(user, doc)]
    waiting = []
    processing = []
    for doc in readable:
        active = next((step for step in doc.steps.all() if step.status == "진행중"), None)
        if active and (active.approver_id == user.id or active.name == user.display_name):
            waiting.append(doc)
        else:
            processing.append(doc)
    labels = {user.username, user.display_name}
    reference_count = sum(bool(labels & set(doc.references)) for doc in readable)
    scheduled_count = sum(
        any((step.approver_id == user.id or step.name == user.display_name) and step.status == "예정" for step in doc.steps.all())
        for doc in readable
    )
    return JsonResponse({
        "pendingCount": len(waiting),
        "receivedCount": sum(doc.received_request for doc in readable),
        "referenceCount": reference_count,
        "scheduledCount": scheduled_count,
        "frequentForms": [form_data(form) for form in forms],
        "processingDocuments": [document_data(doc) for doc in processing],
        "waitingDocuments": [document_data(doc) for doc in waiting],
    })


@endpoint(["GET", "POST"], dev_fallback=True)
def documents(request):
    user = request.api_user
    if request.method == "GET":
        status = request.GET.get("status")
        queryset = document_queryset()
        if status:
            queryset = queryset.filter(status=status)
        rows = [document_data(doc) for doc in queryset if can_read(user, doc)]
        return JsonResponse({"documents": rows})

    data = parse_json(request)
    require_fields(data, ["formId", "title"])
    form = ApprovalFormTemplate.objects.filter(slug=data["formId"], is_enabled=True).first()
    if form is None:
        raise ApiError("사용 가능한 양식을 찾을 수 없습니다.", status=404, code="form_not_found")
    today = timezone.localdate()
    public_id = next_public_id("DRAFT")
    with transaction.atomic():
        document = ApprovalDocument.objects.create(
            public_id=public_id,
            title=str(data["title"]).strip(),
            drafter=user,
            department_name=user.department.name if user.department else "",
            form_template=form,
            form_name=form.name,
            drafted_at=parse_date(data.get("draftedAt"), "draftedAt", today),
            due_date=parse_date(data.get("dueDate"), "dueDate", today),
            effective_date=parse_date(data.get("effectiveDate"), "effectiveDate", today),
            document_no="임시저장",
            cooperation_department=form.cooperation_department,
            agreement=form.agreement,
            content=str(data.get("content") or form.default_content),
            urgent=bool(data.get("urgent", False)),
            department_visible=bool(data.get("departmentVisible", True)),
            receivers=data.get("receivers", form.receivers),
            references=data.get("references", form.references),
            viewers=data.get("viewers", form.viewers),
            public_receivers=data.get("publicReceivers", form.public_receivers),
            linked_documents=data.get("linkedDocuments", []),
            document_layout=str(data.get("documentLayout") or form.document_layout),
            form_fields=data.get("formFields", {}),
            line_items=data.get("lineItems", []),
        )
        replace_steps(document, data.get("steps"), user)
        replace_attachments(document, data.get("attachments", []))
        history(document, user, "새 기안 문서를 임시 저장")
    return JsonResponse(document_data(document_queryset().get(pk=document.pk)), status=201)


@endpoint(["GET", "PATCH", "DELETE"], dev_fallback=True)
def document_detail(request, document_id):
    document = document_queryset().filter(public_id=document_id).first()
    if document is None:
        raise ApiError("결재 문서를 찾을 수 없습니다.", status=404, code="not_found")
    if not can_read(request.api_user, document):
        raise ApiError("문서를 열람할 권한이 없습니다.", status=403, code="permission_denied")
    if request.method == "GET":
        return JsonResponse(document_data(document))
    if request.method == "DELETE":
        if document.status != ApprovalDocument.Status.DRAFT:
            raise ApiError("임시 저장 문서만 삭제할 수 있습니다.", status=409, code="invalid_state")
        if document.drafter_id != request.api_user.id and not request.api_user.is_staff:
            raise ApiError("문서를 삭제할 권한이 없습니다.", status=403, code="permission_denied")
        document.delete()
        return JsonResponse({}, status=204)
    if not document.can_edit or (document.drafter_id != request.api_user.id and not request.api_user.is_staff):
        raise ApiError("문서를 수정할 수 없습니다.", status=409, code="invalid_state")
    data = parse_json(request)
    simple_fields = {
        "title": "title", "content": "content", "urgent": "urgent",
        "departmentVisible": "department_visible", "receivers": "receivers",
        "references": "references", "viewers": "viewers",
        "publicReceivers": "public_receivers", "linkedDocuments": "linked_documents",
        "formFields": "form_fields", "lineItems": "line_items",
    }
    updated = []
    for external, internal in simple_fields.items():
        if external in data:
            setattr(document, internal, data[external])
            updated.append(internal)
    for external, internal in (("draftedAt", "drafted_at"), ("dueDate", "due_date"), ("effectiveDate", "effective_date")):
        if external in data:
            setattr(document, internal, parse_date(data[external], external))
            updated.append(internal)
    with transaction.atomic():
        if updated:
            document.save(update_fields=updated + ["updated_at"])
        if "attachments" in data:
            replace_attachments(document, data["attachments"])
        if "steps" in data:
            replace_steps(document, data["steps"], document.drafter)
        history(document, request.api_user, "기안 문서 수정")
    return JsonResponse(document_data(document_queryset().get(pk=document.pk)))


@endpoint(["POST"], dev_fallback=True)
def submit_document(request, document_id):
    data = parse_json(request)
    with transaction.atomic():
        document = ApprovalDocument.objects.select_for_update().filter(public_id=document_id).first()
        if document is None:
            raise ApiError("결재 문서를 찾을 수 없습니다.", status=404, code="not_found")
        if document.drafter_id != request.api_user.id and not request.api_user.is_staff:
            raise ApiError("문서를 상신할 권한이 없습니다.", status=403, code="permission_denied")
        if document.status != ApprovalDocument.Status.DRAFT:
            raise ApiError("작성 중인 문서만 상신할 수 있습니다.", status=409, code="invalid_state")
        steps = list(document.steps.select_for_update().order_by("order"))
        for index, step in enumerate(steps):
            if index == 0:
                step.status = "완료"
                step.approved_at = step.approved_at or timezone.now()
            elif index == 1:
                step.status = "진행중"
                step.approved_at = None
            else:
                step.status = "결재 예정"
                step.approved_at = None
            step.save(update_fields=["status", "approved_at"])
        next_step = steps[1] if len(steps) > 1 else None
        if next_step:
            document.status = ApprovalDocument.Status.PENDING
        else:
            document.status = ApprovalDocument.Status.APPROVED
        document.public_id = next_public_id("APR")
        document.document_no = document.public_id
        document.received_request = True
        document.can_cancel = document.status != ApprovalDocument.Status.APPROVED
        document.can_edit = False
        document.due_date = parse_date(data.get("dueDate"), "dueDate", timezone.localdate() + timedelta(days=3))
        document.effective_date = parse_date(data.get("effectiveDate"), "effectiveDate", document.due_date)
        set_progress(document)
        document.save()
        history(document, request.api_user, "결재 요청 상신")
    return JsonResponse(document_data(document_queryset().get(pk=document.pk)))


@endpoint(["POST"], dev_fallback=True)
def act_on_document(request, document_id, action):
    data = parse_json(request)
    opinion = str(data.get("opinion") or "").strip()
    reject = action == "reject" or str(data.get("action") or "") == "반려"
    with transaction.atomic():
        document = ApprovalDocument.objects.select_for_update().filter(public_id=document_id).first()
        if document is None:
            raise ApiError("결재 문서를 찾을 수 없습니다.", status=404, code="not_found")
        steps = list(document.steps.select_for_update().order_by("order"))
        active_index = next((index for index, step in enumerate(steps) if step.status == "진행중"), -1)
        if active_index < 0:
            raise ApiError("현재 처리할 결재 단계가 없습니다.", status=409, code="invalid_state")
        active = steps[active_index]
        setting = PortalSetting.load()
        admin_override = request.api_user.is_staff and setting.admin_document_access_enabled
        if not admin_override and active.approver_id != request.api_user.id and active.name != request.api_user.display_name:
            raise ApiError("현재 결재를 처리할 권한이 없습니다.", status=403, code="permission_denied")
        active.status = "반려" if reject else "완료"
        active.approved_at = timezone.now()
        active.save(update_fields=["status", "approved_at"])
        if reject:
            document.status = ApprovalDocument.Status.REJECTED
            document.can_edit = True
            document.can_cancel = False
        elif active_index + 1 < len(steps):
            following = steps[active_index + 1]
            following.status = "진행중"
            following.save(update_fields=["status"])
            document.status = ApprovalDocument.Status.PENDING
            document.can_cancel = False
        else:
            document.status = ApprovalDocument.Status.APPROVED
            document.can_cancel = False
        set_progress(document)
        document.save(update_fields=["status", "can_edit", "can_cancel", "progress", "updated_at"])
        verb = "반려" if reject else "승인"
        history(document, request.api_user, f"{verb}: {opinion}" if opinion else verb)
    return JsonResponse(document_data(document_queryset().get(pk=document.pk)))


@endpoint(["POST"], dev_fallback=True)
def cancel_document(request, document_id):
    with transaction.atomic():
        document = ApprovalDocument.objects.select_for_update().filter(public_id=document_id).first()
        if document is None:
            raise ApiError("결재 문서를 찾을 수 없습니다.", status=404, code="not_found")
        if document.drafter_id != request.api_user.id and not request.api_user.is_staff:
            raise ApiError("상신을 취소할 권한이 없습니다.", status=403, code="permission_denied")
        if not document.can_cancel:
            raise ApiError("이미 결재가 진행되어 상신을 취소할 수 없습니다.", status=409, code="invalid_state")
        if document.steps.exclude(order=0).filter(status="완료").exists():
            raise ApiError("승인 완료 단계가 있어 취소할 수 없습니다.", status=409, code="invalid_state")
        document.status = ApprovalDocument.Status.DRAFT
        document.progress = 0
        document.received_request = False
        document.can_cancel = False
        document.can_edit = True
        document.document_no = "임시저장"
        document.steps.exclude(order=0).update(status="예정", approved_at=None)
        document.save()
        history(document, request.api_user, "상신 취소")
    return JsonResponse(document_data(document_queryset().get(pk=document.pk)))
