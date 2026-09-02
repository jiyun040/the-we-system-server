import re

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import HttpResponse, JsonResponse

from .admin_access import (
    can_change_admin_otp,
    ensure_designated_admin_access,
    matches_designated_admin_profile,
    verify_admin_otp_for_user,
)
from .api import ApiError, bearer_token, endpoint, parse_json, require_fields
from .models import ApiToken, Department
from .serializers import user_data

User = get_user_model()

SIGNUP_EMPLOYEE_PROFILES = {
    "조상훈": ("대표이사", "대표"),
    "조세훈": ("기술부", "전무"),
    "김현정": ("공무", "대리"),
    "김효민": ("경리부", "대리"),
    "정효정": ("관리부", "이사"),
    "송형숙": ("관리부", "부장"),
    "조용덕": ("연구소", "부장"),
}

@endpoint(["POST"], auth=False)
def login(request):
    data = parse_json(request)
    username = str(data.get("id") or data.get("username") or "").strip()
    password = str(data.get("password") or "")
    require_fields({"id": username, "password": password}, ["id", "password"])
    user = authenticate(request, username=username, password=password)
    if user is None:
        raise ApiError(
            "아이디 또는 비밀번호를 확인해 주세요.",
            status=401,
            code="invalid_credentials",
        )
    ensure_designated_admin_access(user)
    token = ApiToken.issue(user, settings.TOKEN_TTL_HOURS)
    return JsonResponse({"token": token, "tokenType": "Bearer", "user": user_data(user)})


@endpoint(["POST"], auth=False)
def register(request):
    data = parse_json(request)
    normalized = {
        "id": str(data.get("id") or data.get("username") or "").strip(),
        "password": str(data.get("password") or ""),
        "name": str(data.get("name") or "").strip(),
        "department": str(data.get("department") or "").strip(),
        "position": str(data.get("position") or "").strip(),
    }
    require_fields(normalized, normalized.keys())

    expected_profile = SIGNUP_EMPLOYEE_PROFILES.get(normalized["name"])
    if expected_profile != (normalized["department"], normalized["position"]):
        raise ApiError(
            "등록된 구성원 정보를 확인해 주세요.",
            status=403,
            code="registration_not_allowed",
        )
    if User.objects.filter(first_name=normalized["name"]).exists():
        raise ApiError(
            "이미 가입된 구성원입니다.",
            status=409,
            code="employee_already_registered",
        )
    if User.objects.filter(username=normalized["id"]).exists():
        raise ApiError(
            "이미 사용 중인 아이디입니다.",
            status=409,
            code="username_already_exists",
            fields={"id": "중복된 아이디입니다."},
        )
    try:
        validate_password(normalized["password"])
    except ValidationError as exc:
        raise ApiError(
            "비밀번호 보안 조건을 확인해 주세요.",
            fields={"password": " ".join(exc.messages)},
        ) from exc

    department, _ = Department.get_or_create_at_end(normalized["department"])
    try:
        user = User.objects.create_user(
            username=normalized["id"],
            password=normalized["password"],
            first_name=normalized["name"],
            department=department,
            position=normalized["position"],
            is_staff=matches_designated_admin_profile(
                normalized["id"],
                normalized["name"],
                normalized["department"],
                normalized["position"],
            ),
        )
    except IntegrityError as exc:
        raise ApiError("계정을 만들지 못했습니다.", code="account_conflict") from exc
    return JsonResponse({"user": user_data(user)}, status=201)


@endpoint(["POST"])
def logout(request):
    raw = bearer_token(request)
    token = ApiToken.resolve(raw)
    if token:
        token.delete()
    return HttpResponse(status=204)


@endpoint(["GET"])
def me(request):
    return JsonResponse({"user": user_data(request.api_user)})


@endpoint(["POST"])
def verify_password(request):
    data = parse_json(request)
    password = str(data.get("password") or "")
    require_fields({"password": password}, ["password"])
    return JsonResponse({"valid": request.api_user.check_password(password)})


@endpoint(["POST"], admin=True)
def verify_admin_otp(request):
    data = parse_json(request)
    otp = str(data.get("otp") or "").strip()
    valid = verify_admin_otp_for_user(request.api_user, otp)
    return JsonResponse({"valid": valid})


@endpoint(["POST"], admin=True)
def change_admin_otp(request):
    if not can_change_admin_otp(request.api_user):
        raise ApiError(
            "슈퍼어드민 OTP는 123456으로 고정됩니다.",
            status=403,
            code="admin_otp_change_not_allowed",
        )

    data = parse_json(request)
    current_otp = str(data.get("currentOtp") or "").strip()
    new_otp = str(data.get("newOtp") or "").strip()
    require_fields(
        {"currentOtp": current_otp, "newOtp": new_otp},
        ["currentOtp", "newOtp"],
    )
    if not re.fullmatch(r"\d{6}", current_otp) or not re.fullmatch(
        r"\d{6}",
        new_otp,
    ):
        raise ApiError(
            "OTP는 숫자 6자리로 입력해 주세요.",
            code="invalid_otp_format",
        )
    if not verify_admin_otp_for_user(request.api_user, current_otp):
        raise ApiError(
            "현재 OTP 번호가 올바르지 않습니다.",
            code="invalid_current_otp",
        )
    if current_otp == new_otp:
        raise ApiError(
            "현재 OTP와 다른 번호를 입력해 주세요.",
            code="otp_unchanged",
        )

    request.api_user.admin_otp_hash = make_password(new_otp)
    request.api_user.save(update_fields=["admin_otp_hash"])
    return JsonResponse({"changed": True})
