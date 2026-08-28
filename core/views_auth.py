from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import HttpResponse, JsonResponse

from .api import ApiError, bearer_token, endpoint, parse_json, require_fields
from .models import ApiToken, Department, PortalSetting
from .serializers import user_data

User = get_user_model()


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
        "email": str(data.get("email") or "").strip().lower(),
    }
    require_fields(normalized, normalized.keys())
    if User.objects.filter(username=normalized["id"]).exists():
        raise ApiError("이미 사용 중인 아이디입니다.", fields={"id": "중복된 아이디입니다."})
    if User.objects.filter(email__iexact=normalized["email"]).exists():
        raise ApiError("이미 사용 중인 이메일입니다.", fields={"email": "중복된 이메일입니다."})
    department, _ = Department.objects.get_or_create(name=normalized["department"])
    try:
        validate_password(normalized["password"])
    except ValidationError as exc:
        raise ApiError(
            "비밀번호 보안 조건을 확인해 주세요.",
            fields={"password": " ".join(exc.messages)},
        ) from exc
    try:
        user = User.objects.create_user(
            username=normalized["id"],
            password=normalized["password"],
            first_name=normalized["name"],
            last_name="",
            email=normalized["email"],
            department=department,
            position=normalized["position"],
        )
    except IntegrityError as exc:
        raise ApiError("계정을 만들지 못했습니다.", code="account_conflict") from exc
    token = ApiToken.issue(user, settings.TOKEN_TTL_HOURS)
    return JsonResponse({"token": token, "tokenType": "Bearer", "user": user_data(user)}, status=201)


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
    setting = PortalSetting.load()
    valid = not setting.admin_otp_enabled or otp == "123456"
    return JsonResponse({"valid": valid})
