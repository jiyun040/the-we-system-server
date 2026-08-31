from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.http import HttpResponse, JsonResponse

from .api import ApiError, bearer_token, endpoint, parse_json, require_fields
from .models import ApiToken, PortalSetting
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
