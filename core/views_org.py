from datetime import date

from django.contrib.auth import get_user_model
from django.http import HttpResponse, JsonResponse

from .api import ApiError, endpoint, parse_json, require_fields
from .models import ApprovalDocument, Department, PortalSetting
from .serializers import settings_data, user_data

User = get_user_model()

DEPARTMENT_ORDER = ["대표이사", "기술부", "연구소", "관리부", "공무", "경리부"]


def department_sort_key(department):
    try:
        return (0, DEPARTMENT_ORDER.index(department.name))
    except ValueError:
        return (1, department.name)


@endpoint(["GET", "POST"], dev_fallback=True)
def departments(request):
    if request.method == "POST":
        if not request.api_user.is_staff:
            raise ApiError("관리자 권한이 필요합니다.", status=403, code="permission_denied")
        data = parse_json(request)
        name = str(data.get("name") or "").strip()
        require_fields({"name": name}, ["name"])
        department, created = Department.objects.get_or_create(name=name)
        return JsonResponse(
            {"id": department.pk, "name": department.name, "description": department.description},
            status=201 if created else 200,
        )
    rows = []
    queryset = sorted(
        Department.objects.prefetch_related("members").exclude(name="시스템관리"),
        key=department_sort_key,
    )
    for department in queryset:
        rows.append(
            {
                "id": department.pk,
                "name": department.name,
                "description": department.description,
                "members": [
                    user_data(user)
                    for user in department.members.filter(is_active=True).exclude(username="admin")
                ],
            }
        )
    return JsonResponse({"departments": rows})


@endpoint(["GET", "POST"], dev_fallback=True)
def employees(request):
    if request.method == "POST":
        if not request.api_user.is_staff:
            raise ApiError("관리자 권한이 필요합니다.", status=403, code="permission_denied")
        data = parse_json(request)
        fields = {key: str(data.get(key) or "").strip() for key in (
            "id", "password", "name", "department", "position", "email", "hireDate"
        )}
        require_fields(fields, fields.keys())
        try:
            hire_date = date.fromisoformat(fields["hireDate"])
        except ValueError as exc:
            raise ApiError("입사일은 YYYY-MM-DD 형식이어야 합니다.", fields={"hireDate": "잘못된 날짜입니다."}) from exc
        if User.objects.filter(username=fields["id"]).exists():
            raise ApiError("이미 사용 중인 아이디입니다.", fields={"id": "중복된 아이디입니다."})
        if User.objects.filter(email__iexact=fields["email"]).exists():
            raise ApiError("이미 사용 중인 이메일입니다.", fields={"email": "중복된 이메일입니다."})
        department, _ = Department.objects.get_or_create(name=fields["department"])
        user = User.objects.create_user(
            username=fields["id"], password=fields["password"], first_name=fields["name"],
            email=fields["email"], department=department, position=fields["position"],
            hire_date=hire_date,
        )
        return JsonResponse({"user": user_data(user)}, status=201)
    users = (
        User.objects.select_related("department")
        .filter(is_active=True)
        .exclude(username="admin")
        .order_by("first_name", "username")
    )
    return JsonResponse({"employees": [user_data(user) for user in users]})


@endpoint(["PATCH", "DELETE"], admin=True)
def employee_detail(request, user_id):
    user = (
        User.objects.select_related("department")
        .filter(username=user_id)
        .exclude(username="admin")
        .first()
    )
    if user is None:
        raise ApiError("직원을 찾을 수 없습니다.", status=404, code="not_found")
    if request.method == "DELETE":
        if user.pk == request.api_user.pk:
            raise ApiError("현재 로그인한 계정은 삭제할 수 없습니다.")
        user.api_tokens.all().delete()
        user.department = None
        user.is_active = False
        user.save(update_fields=["department", "is_active"])
        return HttpResponse(status=204)
    data = parse_json(request)
    updated = []
    if "name" in data:
        name = str(data["name"] or "").strip()
        require_fields({"name": name}, ["name"])
        user.first_name = name
        updated.append("first_name")
    if "email" in data:
        email = str(data["email"] or "").strip()
        require_fields({"email": email}, ["email"])
        if User.objects.exclude(pk=user.pk).filter(email__iexact=email).exists():
            raise ApiError("이미 사용 중인 이메일입니다.", code="email_conflict")
        user.email = email
        updated.append("email")
    if "department" in data:
        department_name = str(data["department"] or "").strip()
        require_fields({"department": department_name}, ["department"])
        user.department, _ = Department.objects.get_or_create(name=department_name)
        updated.append("department")
    if "position" in data:
        user.position = str(data["position"] or "").strip()
        updated.append("position")
    if "hireDate" in data:
        try:
            user.hire_date = date.fromisoformat(str(data["hireDate"]))
        except ValueError as exc:
            raise ApiError("입사일은 YYYY-MM-DD 형식이어야 합니다.") from exc
        updated.append("hire_date")
    password = str(data.get("password") or "").strip()
    if password:
        user.set_password(password)
        updated.append("password")
    if updated:
        user.save(update_fields=updated)
    return JsonResponse({"user": user_data(user)})


@endpoint(["PATCH", "DELETE"], admin=True)
def department_detail(request, department_id):
    department = Department.objects.filter(pk=department_id).first()
    if department is None:
        raise ApiError("부서를 찾을 수 없습니다.", status=404, code="not_found")
    if request.method == "DELETE":
        if department.members.filter(is_active=True).exists():
            raise ApiError(
                "소속 직원이 있는 부서는 삭제할 수 없습니다.",
                status=409,
                code="department_not_empty",
            )
        department.members.update(department=None)
        department.delete()
        return HttpResponse(status=204)
    data = parse_json(request)
    name = str(data.get("name") or "").strip()
    require_fields({"name": name}, ["name"])
    if Department.objects.exclude(pk=department.pk).filter(name=name).exists():
        raise ApiError("이미 사용 중인 부서명입니다.", code="department_conflict")
    old_name = department.name
    department.name = name
    department.save(update_fields=["name"])
    ApprovalDocument.objects.filter(department_name=old_name).update(department_name=name)
    return JsonResponse({"id": department.pk, "name": department.name})


@endpoint(["GET", "PATCH"], dev_fallback=True)
def portal_settings(request):
    setting = PortalSetting.load()
    if request.method == "PATCH":
        if not request.api_user.is_staff:
            raise ApiError("관리자 권한이 필요합니다.", status=403, code="permission_denied")
        data = parse_json(request)
        if len(str(data.get("customLogoBase64") or "")) > 7_000_000:
            raise ApiError(
                "로고 파일은 5MB 이하만 사용할 수 있습니다.",
                status=413,
                code="file_too_large",
            )
        field_map = {
            "portalName": "portal_name",
            "annualLeaveByYear": "annual_leave_by_year",
            "monthlyLeavePerMonth": "monthly_leave_per_month",
            "adminOtpEnabled": "admin_otp_enabled",
            "settingsPasswordEnabled": "settings_password_enabled",
            "adminDocumentAccessEnabled": "admin_document_access_enabled",
            "customLogoBase64": "custom_logo_base64",
            "customLogoFileName": "custom_logo_file_name",
            "enabledAppIds": "enabled_app_ids",
            "organizationWideDocumentCategories": "organization_wide_document_categories",
            "documentCategoryViewerIds": "document_category_viewer_ids",
        }
        updated = []
        for external, internal in field_map.items():
            if external in data:
                setattr(setting, internal, data[external])
                updated.append(internal)
        if updated:
            setting.save(update_fields=updated + ["updated_at"])
    return JsonResponse(settings_data(setting))
