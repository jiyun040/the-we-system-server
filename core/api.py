import json
from functools import wraps

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import ApiToken

User = get_user_model()


class ApiError(Exception):
    def __init__(self, message, status=400, code="bad_request", fields=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.fields = fields or {}


def parse_json(request):
    if not request.body:
        return {}
    try:
        value = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ApiError("JSON 요청 본문을 확인해 주세요.", fields={"body": str(exc)}) from exc
    if not isinstance(value, dict):
        raise ApiError("요청 본문은 JSON 객체여야 합니다.")
    return value


def bearer_token(request):
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


def resolve_user(request, allow_dev_fallback=False):
    if getattr(request, "user", None) and request.user.is_authenticated:
        return request.user
    token = ApiToken.resolve(bearer_token(request))
    if token:
        return token.user
    if allow_dev_fallback and settings.DEV_ALLOW_ANONYMOUS:
        return User.objects.select_related("department").filter(
            username=settings.DEV_DEFAULT_USERNAME, is_active=True
        ).first()
    return None


def endpoint(methods, *, auth=True, admin=False, dev_fallback=False):
    allowed = {method.upper() for method in methods}

    def decorator(view):
        @csrf_exempt
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method not in allowed:
                response = JsonResponse(
                    {"error": {"code": "method_not_allowed", "message": "지원하지 않는 요청 방식입니다."}},
                    status=405,
                )
                response["Allow"] = ", ".join(sorted(allowed))
                return response
            try:
                request.api_user = resolve_user(request, allow_dev_fallback=dev_fallback)
                if auth and request.api_user is None:
                    raise ApiError("로그인이 필요합니다.", status=401, code="authentication_required")
                if admin and not request.api_user.is_staff:
                    raise ApiError("관리자 권한이 필요합니다.", status=403, code="permission_denied")
                return view(request, *args, **kwargs)
            except ApiError as exc:
                payload = {"error": {"code": exc.code, "message": exc.message}}
                if exc.fields:
                    payload["error"]["fields"] = exc.fields
                return JsonResponse(payload, status=exc.status)

        return wrapped

    return decorator


def require_fields(data, names):
    missing = [name for name in names if data.get(name) in (None, "")]
    if missing:
        raise ApiError("필수 입력값을 확인해 주세요.", fields={name: "필수 항목입니다." for name in missing})
