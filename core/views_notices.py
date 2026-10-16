import base64
import binascii
from datetime import timedelta
from urllib.parse import quote

from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.utils import timezone

from .admin_access import can_change_admin_otp, is_super_admin_account
from .api import ApiError, endpoint, parse_json
from .models import Notice, NoticeAttachment
from .serializers import notice_data


DRAFT_LIFETIME = timedelta(days=7)
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 14 * 1024 * 1024
MAX_ATTACHMENTS = 10


def purge_expired_drafts():
    Notice.objects.filter(is_draft=True, updated_at__lte=timezone.now() - DRAFT_LIFETIME).delete()


def visible_notices(user):
    rows = Notice.objects.select_related("author").prefetch_related("attachments")
    if can_change_admin_otp(user) or is_super_admin_account(user):
        return rows.filter(Q(is_draft=False) | Q(author=user))
    return rows.filter(is_draft=False)


def require_notice_manager(user):
    if not (can_change_admin_otp(user) or is_super_admin_account(user)):
        raise ApiError(
            "관리자 계정만 공지사항을 관리할 수 있습니다.",
            status=403,
            code="notice_management_not_allowed",
        )


def notice_fields(data, *, notice=None):
    title = str(data.get("title", notice.title if notice else "") or "").strip()
    content = str(data.get("content", notice.content if notice else "") or "").strip()
    is_draft = data.get("isDraft", notice.is_draft if notice else False) is True
    if len(title) > 200:
        raise ApiError(
            "공지 제목은 200자 이하로 입력해 주세요.",
            fields={"title": "200자를 초과했습니다."},
        )
    if not is_draft and (not title or not content):
        raise ApiError("공지 제목과 내용을 모두 입력해 주세요.")
    return {
        "title": title,
        "content": content,
        "is_pinned": data.get("isPinned", notice.is_pinned if notice else False) is True,
        "is_draft": is_draft,
    }


def replace_attachments(notice, items):
    if not isinstance(items, list) or len(items) > MAX_ATTACHMENTS:
        raise ApiError("첨부파일은 최대 10개까지 등록할 수 있습니다.")
    existing = {str(row.pk): row for row in notice.attachments.all()}
    retained = set()
    incoming = []
    total = 0
    for item in items:
        if not isinstance(item, dict):
            raise ApiError("첨부파일 형식을 확인해 주세요.")
        attachment_id = str(item.get("id") or "")
        if attachment_id:
            row = existing.get(attachment_id)
            if row is None or attachment_id in retained:
                raise ApiError("첨부파일을 다시 선택해 주세요.")
            retained.add(attachment_id)
            total += row.size
            continue
        name = str(item.get("name") or "").strip()
        encoded = str(item.get("base64Data") or "")
        if not name or len(name) > 255:
            raise ApiError("첨부파일 이름을 확인해 주세요.")
        if len(encoded) > MAX_ATTACHMENT_BYTES * 4 // 3 + 8:
            raise ApiError("첨부파일은 개별 10MB 이하만 등록할 수 있습니다.")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ApiError("첨부파일 데이터를 확인해 주세요.") from exc
        if not raw or len(raw) > MAX_ATTACHMENT_BYTES:
            raise ApiError("첨부파일은 개별 10MB 이하만 등록할 수 있습니다.")
        total += len(raw)
        incoming.append(NoticeAttachment(
            notice=notice,
            name=name,
            mime_type=str(item.get("mimeType") or "application/octet-stream")[:150],
            size=len(raw),
            base64_data=encoded,
        ))
    if total > MAX_TOTAL_BYTES:
        raise ApiError("첨부파일 전체 크기는 14MB 이하여야 합니다.")
    notice.attachments.exclude(pk__in=retained).delete()
    NoticeAttachment.objects.bulk_create(incoming)


@endpoint(["GET", "POST"])
@transaction.atomic
def notices(request):
    purge_expired_drafts()
    if request.method == "GET":
        return JsonResponse({"notices": [notice_data(row) for row in visible_notices(request.api_user)]})

    require_notice_manager(request.api_user)
    data = parse_json(request)
    fields = notice_fields(data)
    notice = Notice.objects.create(author=request.api_user, **fields)
    if "attachments" in data:
        replace_attachments(notice, data["attachments"])
    return JsonResponse(notice_data(Notice.objects.prefetch_related("attachments").get(pk=notice.pk)), status=201)


@endpoint(["PATCH", "DELETE"])
@transaction.atomic
def notice_detail(request, notice_id):
    require_notice_manager(request.api_user)
    purge_expired_drafts()
    notice = Notice.objects.select_related("author").prefetch_related("attachments").filter(pk=notice_id).first()
    if notice is None:
        raise ApiError("공지사항을 찾을 수 없습니다.", status=404, code="not_found")
    if notice.is_draft and notice.author_id != request.api_user.id:
        raise ApiError("다른 관리자의 임시저장본은 수정할 수 없습니다.", status=403, code="permission_denied")
    if request.method == "DELETE":
        notice.delete()
        return HttpResponse(status=204)

    data = parse_json(request)
    fields = notice_fields(data, notice=notice)
    for field, value in fields.items():
        setattr(notice, field, value)
    notice.save(update_fields=[*fields.keys(), "updated_at"])
    if "attachments" in data:
        replace_attachments(notice, data["attachments"])
    return JsonResponse(notice_data(Notice.objects.prefetch_related("attachments").get(pk=notice.pk)))


@endpoint(["GET"])
def notice_attachment(request, notice_id, attachment_id):
    purge_expired_drafts()
    notice = Notice.objects.filter(pk=notice_id).first()
    if notice is None or (notice.is_draft and notice.author_id != request.api_user.id):
        raise ApiError("첨부파일을 찾을 수 없습니다.", status=404, code="not_found")
    attachment = NoticeAttachment.objects.filter(pk=attachment_id, notice=notice).first()
    if attachment is None:
        raise ApiError("첨부파일을 찾을 수 없습니다.", status=404, code="not_found")
    response = HttpResponse(base64.b64decode(attachment.base64_data), content_type=attachment.mime_type)
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(attachment.name)}"
    response["X-Content-Type-Options"] = "nosniff"
    return response
