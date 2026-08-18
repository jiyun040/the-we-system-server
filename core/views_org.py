from datetime import date

from django.contrib.auth import get_user_model
from django.http import JsonResponse

from .api import ApiError, endpoint, parse_json, require_fields
from .models import Department, PortalSetting
from .serializers import user_data

User = get_user_model()


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
    queryset = Department.objects.prefetch_related("members").all()
    for department in queryset:
        rows.append(
            {
                "id": department.pk,
                "name": department.name,
                "description": department.description,
                "members": [user_data(user) for user in department.members.filter(is_active=True)],
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
    users = User.objects.select_related("department").filter(is_active=True).order_by("first_name", "username")
    return JsonResponse({"employees": [user_data(user) for user in users]})


@endpoint(["GET", "PATCH"], dev_fallback=True)
def portal_settings(request):
    setting = PortalSetting.load()
    if request.method == "PATCH":
        if not request.api_user.is_staff:
            raise ApiError("관리자 권한이 필요합니다.", status=403, code="permission_denied")
        data = parse_json(request)
        field_map = {
            "portalName": "portal_name",
            "annualLeaveByYear": "annual_leave_by_year",
            "monthlyLeavePerMonth": "monthly_leave_per_month",
            "adminOtpEnabled": "admin_otp_enabled",
            "settingsPasswordEnabled": "settings_password_enabled",
            "adminDocumentAccessEnabled": "admin_document_access_enabled",
        }
        updated = []
        for external, internal in field_map.items():
            if external in data:
                setattr(setting, internal, data[external])
                updated.append(internal)
        if updated:
            setting.save(update_fields=updated + ["updated_at"])
    return JsonResponse({
        "portalName": setting.portal_name,
        "annualLeaveByYear": setting.annual_leave_by_year,
        "monthlyLeavePerMonth": setting.monthly_leave_per_month,
        "adminOtpEnabled": setting.admin_otp_enabled,
        "settingsPasswordEnabled": setting.settings_password_enabled,
        "adminDocumentAccessEnabled": setting.admin_document_access_enabled,
    })
