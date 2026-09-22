import hashlib
import logging
import os

from django.db import transaction
from django.http import JsonResponse

from .api import ApiError, endpoint, parse_json
from .models import DevicePushToken


logger = logging.getLogger(__name__)


@endpoint(["POST", "DELETE"])
def device_tokens(request):
    data = parse_json(request)
    token = str(data.get("token") or "").strip()
    if not token or len(token) > 4096:
        raise ApiError("알림 기기 토큰을 확인해 주세요.")
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    if request.method == "DELETE":
        DevicePushToken.objects.filter(user=request.api_user, token_hash=token_hash).delete()
        return JsonResponse({"deleted": True})
    DevicePushToken.objects.update_or_create(
        token_hash=token_hash,
        defaults={"token": token, "user": request.api_user, "platform": str(data.get("platform") or "")[:20]},
    )
    return JsonResponse({"registered": True})


def notify_users(user_ids, title, body, *, route="/"):
    user_ids = {user_id for user_id in user_ids if user_id}
    if not user_ids:
        return

    def send():
        credentials_path = os.getenv("FIREBASE_SERVICE_ACCOUNT", "").strip()
        if not credentials_path:
            return
        try:
            import firebase_admin
            from firebase_admin import credentials, messaging

            if not firebase_admin._apps:
                firebase_admin.initialize_app(credentials.Certificate(credentials_path))
            tokens = list(DevicePushToken.objects.filter(user_id__in=user_ids).values_list("token", flat=True))
            if not tokens:
                return
            response = messaging.send_each_for_multicast(messaging.MulticastMessage(
                notification=messaging.Notification(title=title, body=body),
                data={"route": route},
                tokens=tokens,
            ))
            for token, result in zip(tokens, response.responses):
                if not result.success and isinstance(result.exception, messaging.UnregisteredError):
                    DevicePushToken.objects.filter(token=token).delete()
        except Exception:
            logger.exception("푸시 알림을 전송하지 못했습니다")

    transaction.on_commit(send)
