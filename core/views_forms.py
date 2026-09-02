from django.http import HttpResponse, JsonResponse
from django.utils.text import slugify

from .api import ApiError, endpoint, parse_json, require_fields
from .models import ApprovalFormTemplate
from .serializers import form_data


FORM_FIELDS = {
    "category": "category",
    "name": "name",
    "description": "description",
    "defaultTitle": "default_title",
    "defaultContent": "default_content",
    "receivers": "receivers",
    "references": "references",
    "viewers": "viewers",
    "publicReceivers": "public_receivers",
    "cooperationDepartment": "cooperation_department",
    "agreement": "agreement",
    "documentLayout": "document_layout",
    "lineItemRows": "line_item_rows",
    "approvalLines": "approval_lines",
    "enabled": "is_enabled",
}


def normalize_approval_lines(value):
    if not isinstance(value, list):
        raise ApiError(
            "결재라인 형식을 확인해 주세요.",
            fields={"approvalLines": "목록 형식이어야 합니다."},
        )
    normalized = []
    used_ids = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ApiError(
                "결재라인 형식을 확인해 주세요.",
                fields={"approvalLines": "각 결재라인은 객체여야 합니다."},
            )
        line_id = str(item.get("id") or f"line-{index + 1}").strip()
        name = str(item.get("name") or "").strip()
        raw_user_ids = item.get("userIds")
        if not line_id or line_id in used_ids or not name or not isinstance(raw_user_ids, list):
            raise ApiError(
                "결재라인 이름과 결재자를 확인해 주세요.",
                fields={"approvalLines": "이름과 결재자 목록이 필요합니다."},
            )
        user_ids = []
        for raw_user_id in raw_user_ids:
            user_id = str(raw_user_id or "").strip()
            if user_id and user_id not in user_ids:
                user_ids.append(user_id)
        if not user_ids:
            raise ApiError(
                "결재라인마다 한 명 이상의 결재자를 선택해 주세요.",
                fields={"approvalLines": "결재자가 없습니다."},
            )
        used_ids.add(line_id)
        normalized.append({"id": line_id, "name": name, "userIds": user_ids})
    return normalized


def form_values(data):
    values = {
        internal: data[external]
        for external, internal in FORM_FIELDS.items()
        if external in data
    }
    if "approvalLines" in data:
        values["approval_lines"] = normalize_approval_lines(data["approvalLines"])
    return values


@endpoint(["GET", "POST"], dev_fallback=True)
def forms(request):
    if request.method == "GET":
        queryset = ApprovalFormTemplate.objects.all()
        if not request.api_user.is_staff:
            queryset = queryset.filter(is_enabled=True)
        return JsonResponse({"forms": [form_data(form) for form in queryset]})
    if not request.api_user.is_staff:
        raise ApiError("관리자 권한이 필요합니다.", status=403, code="permission_denied")
    data = parse_json(request)
    require_fields(data, ["name", "category", "defaultTitle"])
    requested_slug = str(data.get("id") or slugify(data["name"], allow_unicode=False)).strip()
    if not requested_slug:
        requested_slug = f"form-{ApprovalFormTemplate.objects.count() + 1}"
    if ApprovalFormTemplate.objects.filter(slug=requested_slug).exists():
        raise ApiError("이미 사용 중인 양식 ID입니다.", code="form_conflict")
    values = form_values(data)
    form = ApprovalFormTemplate.objects.create(slug=requested_slug, **values)
    return JsonResponse(form_data(form), status=201)


@endpoint(["GET", "PATCH", "DELETE"], dev_fallback=True)
def form_detail(request, form_id):
    form = ApprovalFormTemplate.objects.filter(slug=form_id).first()
    if form is None:
        raise ApiError("양식을 찾을 수 없습니다.", status=404, code="not_found")
    if request.method == "GET":
        return JsonResponse(form_data(form))
    if not request.api_user.is_staff:
        raise ApiError("관리자 권한이 필요합니다.", status=403, code="permission_denied")
    if request.method == "DELETE":
        form.delete()
        return HttpResponse(status=204)
    data = parse_json(request)
    updated = []
    for internal, value in form_values(data).items():
        setattr(form, internal, value)
        updated.append(internal)
    if updated:
        form.save(update_fields=updated + ["updated_at"])
    return JsonResponse(form_data(form))
