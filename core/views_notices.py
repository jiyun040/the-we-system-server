from django.http import HttpResponse, JsonResponse

from .admin_access import can_change_admin_otp
from .api import ApiError, endpoint, parse_json, require_fields
from .models import Notice
from .serializers import notice_data


def require_notice_manager(user):
    if not can_change_admin_otp(user):
        raise ApiError(
            "OTP 관리자 계정만 공지사항을 관리할 수 있습니다.",
            status=403,
            code="notice_management_not_allowed",
        )


def notice_fields(data, *, partial=False):
    fields = {}
    if not partial or "title" in data:
        fields["title"] = str(data.get("title") or "").strip()
    if not partial or "content" in data:
        fields["content"] = str(data.get("content") or "").strip()
    if not partial:
        require_fields(fields, ["title", "content"])
    elif any(value == "" for value in fields.values()):
        require_fields(fields, fields.keys())
    if len(fields.get("title", "")) > 200:
        raise ApiError(
            "공지 제목은 200자 이하로 입력해 주세요.",
            fields={"title": "200자를 초과했습니다."},
        )
    if "isPinned" in data:
        fields["is_pinned"] = data["isPinned"] is True
    return fields


@endpoint(["GET", "POST"])
def notices(request):
    if request.method == "GET":
        rows = Notice.objects.select_related("author").all()
        return JsonResponse({"notices": [notice_data(row) for row in rows]})

    require_notice_manager(request.api_user)
    fields = notice_fields(parse_json(request))
    notice = Notice.objects.create(author=request.api_user, **fields)
    return JsonResponse(notice_data(notice), status=201)


@endpoint(["PATCH", "DELETE"])
def notice_detail(request, notice_id):
    require_notice_manager(request.api_user)
    notice = Notice.objects.select_related("author").filter(pk=notice_id).first()
    if notice is None:
        raise ApiError("공지사항을 찾을 수 없습니다.", status=404, code="not_found")
    if request.method == "DELETE":
        notice.delete()
        return HttpResponse(status=204)

    fields = notice_fields(parse_json(request), partial=True)
    for field, value in fields.items():
        setattr(notice, field, value)
    if fields:
        notice.save(update_fields=[*fields.keys(), "updated_at"])
    return JsonResponse(notice_data(notice))
