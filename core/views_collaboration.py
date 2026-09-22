import base64

from django.http import HttpResponse, JsonResponse

from .api import ApiError, endpoint, parse_json, require_fields
from .models import BoardPost, Department, LeaveRequest, SharedCalendarEvent
from .parsing import parse_iso_date


def calendar_data(event):
    return {
        "id": str(event.pk),
        "date": event.event_date.isoformat(),
        "title": event.title,
        "time": event.time,
        "place": event.place,
        "colorKey": event.color_key,
        "authorId": event.author.username,
        "authorName": event.author.display_name,
        "kind": "schedule",
    }


@endpoint(["GET", "POST"])
def calendar_events(request):
    if request.method == "GET":
        events = [calendar_data(event) for event in SharedCalendarEvent.objects.select_related("author")]
        for leave in LeaveRequest.objects.select_related("user").filter(status=LeaveRequest.Status.APPROVED):
            events.append({
                "id": f"leave-{leave.public_id}",
                "date": leave.start_date.isoformat(),
                "endDate": leave.end_date.isoformat(),
                "title": f"{leave.user.display_name} {leave.leave_type}",
                "time": "",
                "place": "",
                "colorKey": "pink",
                "authorId": leave.user.username,
                "authorName": leave.user.display_name,
                "kind": "leave",
            })
        return JsonResponse({"events": events})
    data = parse_json(request)
    require_fields(data, ["title", "date"])
    title = str(data["title"]).strip()
    if len(title) > 200:
        raise ApiError("일정 이름은 200자 이하로 입력해 주세요.")
    event = SharedCalendarEvent.objects.create(
        title=title,
        event_date=parse_iso_date(data["date"], "date"),
        time=str(data.get("time") or "09:00")[:5],
        place=str(data.get("place") or "")[:200],
        color_key=str(data.get("colorKey") or "blue")[:20],
        author=request.api_user,
    )
    return JsonResponse(calendar_data(event), status=201)


@endpoint(["PATCH", "DELETE"])
def calendar_event_detail(request, event_id):
    event = SharedCalendarEvent.objects.filter(pk=event_id).first()
    if event is None:
        raise ApiError("일정을 찾을 수 없습니다.", status=404, code="not_found")
    if event.author_id != request.api_user.pk and not request.api_user.is_staff:
        raise ApiError("작성자만 일정을 수정할 수 있습니다.", status=403, code="permission_denied")
    if request.method == "DELETE":
        event.delete()
        return HttpResponse(status=204)
    data = parse_json(request)
    if "title" in data:
        event.title = str(data["title"]).strip()[:200]
        if not event.title:
            raise ApiError("일정 이름을 입력해 주세요.")
    if "date" in data:
        event.event_date = parse_iso_date(data["date"], "date")
    if "time" in data:
        event.time = str(data["time"])[:5]
    if "place" in data:
        event.place = str(data["place"])[:200]
    if "colorKey" in data:
        event.color_key = str(data["colorKey"])[:20]
    event.save()
    return JsonResponse(calendar_data(event))


def board_data(post):
    return {
        "id": str(post.pk),
        "title": post.title,
        "content": post.content,
        "department": post.department.name if post.department else "",
        "authorId": post.author.username,
        "authorName": post.author.display_name,
        "attachments": post.attachments,
        "createdAt": post.created_at.isoformat(),
        "updatedAt": post.updated_at.isoformat(),
    }


def board_fields(data):
    require_fields(data, ["title", "content"])
    title = str(data["title"]).strip()
    content = str(data["content"]).strip()
    if len(title) > 200:
        raise ApiError("제목은 200자 이하로 입력해 주세요.")
    department_name = str(data.get("department") or "").strip()
    department = Department.objects.filter(name=department_name).first() if department_name else None
    if department_name and department is None:
        raise ApiError("부서를 찾을 수 없습니다.")
    raw_attachments = data.get("attachments") or []
    if not isinstance(raw_attachments, list) or len(raw_attachments) > 5:
        raise ApiError("첨부파일은 5개까지 등록할 수 있습니다.")
    attachments = []
    for item in raw_attachments:
        if not isinstance(item, dict):
            raise ApiError("첨부파일 형식을 확인해 주세요.")
        name = str(item.get("name") or "").strip()[:255]
        encoded = str(item.get("base64Data") or "")
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise ApiError("첨부파일을 읽을 수 없습니다.") from exc
        if not name or not decoded or len(decoded) > 10 * 1024 * 1024:
            raise ApiError("첨부파일은 각 10MB 이하로 등록해 주세요.")
        attachments.append({"name": name, "base64Data": encoded, "mimeType": str(item.get("mimeType") or "application/octet-stream")[:120]})
    return {"title": title, "content": content, "department": department, "attachments": attachments}


@endpoint(["GET", "POST"])
def board_posts(request):
    if request.method == "GET":
        rows = BoardPost.objects.select_related("author", "department")
        department_name = str(request.GET.get("department") or "").strip()
        if department_name == "전체":
            rows = rows.filter(department__isnull=True)
        elif department_name:
            rows = rows.filter(department__name=department_name)
        return JsonResponse({"posts": [board_data(post) for post in rows]})
    post = BoardPost.objects.create(author=request.api_user, **board_fields(parse_json(request)))
    return JsonResponse(board_data(post), status=201)


@endpoint(["GET", "PATCH", "DELETE"])
def board_post_detail(request, post_id):
    post = BoardPost.objects.select_related("author", "department").filter(pk=post_id).first()
    if post is None:
        raise ApiError("게시글을 찾을 수 없습니다.", status=404, code="not_found")
    if request.method == "GET":
        return JsonResponse(board_data(post))
    if post.author_id != request.api_user.pk and not request.api_user.is_staff:
        raise ApiError("작성자만 게시글을 변경할 수 있습니다.", status=403, code="permission_denied")
    if request.method == "DELETE":
        post.delete()
        return HttpResponse(status=204)
    fields = board_fields(parse_json(request))
    for key, value in fields.items():
        setattr(post, key, value)
    post.save()
    return JsonResponse(board_data(post))
