from django.http import JsonResponse

from .api import endpoint
from .models import ApprovalFormTemplate, Department, LeaveRequest, PortalSetting, User
from .serializers import document_data, form_data, leave_data, settings_data, user_data
from .views_approvals import can_read, document_queryset

DEPARTMENT_ORDER = ["대표이사", "기술부", "연구소", "관리부", "공무", "경리부"]


def department_sort_key(name):
    try:
        return (0, DEPARTMENT_ORDER.index(name))
    except ValueError:
        return (1, name)


@endpoint(["GET"])
def bootstrap(request):
    user = request.api_user
    accounts = (
        User.objects.select_related("department")
        .filter(is_active=True)
        .exclude(username="admin")
        .order_by("first_name", "username")
    )
    forms = list(ApprovalFormTemplate.objects.all())
    documents = [document for document in document_queryset() if can_read(user, document)]
    leaves = LeaveRequest.objects.select_related(
        "user", "user__department", "registered_by"
    )
    if not user.is_staff and user.username != "ceo":
        leaves = leaves.filter(user=user)
    setting = PortalSetting.load()
    departments = sorted(
        Department.objects.exclude(name="시스템관리").values_list("name", flat=True),
        key=department_sort_key,
    )
    return JsonResponse(
        {
            "currentUser": user_data(user),
            "accounts": [user_data(account) for account in accounts],
            "departments": departments,
            "frequentForms": [
                form_data(form)
                for form in sorted(forms, key=lambda item: -item.recent_count)[:5]
            ],
            "formTemplates": [form_data(form) for form in forms],
            "disabledFormTemplateIds": [form.slug for form in forms if not form.is_enabled],
            "documents": [document_data(document) for document in documents],
            "restrictedDocumentIds": [
                document.public_id for document in documents if not document.department_visible
            ],
            "leaveRequests": [leave_data(leave) for leave in leaves],
            "acknowledgedLeaveRequestIds": [
                leave.public_id for leave in leaves if leave.acknowledged
            ],
            "settings": settings_data(setting),
        }
    )
