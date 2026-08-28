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
    "enabled": "is_enabled",
}


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
    values = {internal: data[external] for external, internal in FORM_FIELDS.items() if external in data}
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
    for external, internal in FORM_FIELDS.items():
        if external in data:
            setattr(form, internal, data[external])
            updated.append(internal)
    if updated:
        form.save(update_fields=updated + ["updated_at"])
    return JsonResponse(form_data(form))
