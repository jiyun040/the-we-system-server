from django.http import JsonResponse

from .api import endpoint
from .models import (
    ApprovalFormTemplate,
    Department,
    LeaveRequest,
    Notice,
    PortalSetting,
    User,
)
from .serializers import (
    document_data,
    form_data,
    leave_data,
    notice_data,
    settings_data,
    user_data,
)
from .views_approvals import can_read, document_queryset, frequent_forms_for_user

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
    frequent_forms = frequent_forms_for_user(user)
    documents = [document for document in document_queryset() if can_read(user, document)]
    leaves = LeaveRequest.objects.select_related(
        "user", "user__department", "registered_by"
    )
    if not user.is_staff and user.username != "ceo":
        leaves = leaves.filter(user=user)
    setting = PortalSetting.load()
    departments = list(
        Department.objects.exclude(name="시스템관리")
        .order_by("sort_order", "name")
        .values_list("name", flat=True)
    )
    return JsonResponse(
        {
            "currentUser": user_data(user),
            "accounts": [user_data(account) for account in accounts],
            "departments": departments,
            "frequentForms": [
                form_data(form, recent_count=form.user_recent_count)
                for form in frequent_forms
            ],
            "formTemplates": [form_data(form) for form in forms],
            "disabledFormTemplateIds": [form.slug for form in forms if not form.is_enabled],
            "documents": [document_data(document) for document in documents],
            "restrictedDocumentIds": [
                document.public_id for document in documents if not document.department_visible
            ],
            "leaveRequests": [leave_data(leave) for leave in leaves],
            "notices": [
                notice_data(notice)
                for notice in Notice.objects.select_related("author").all()
            ],
            "acknowledgedLeaveRequestIds": [
                leave.public_id for leave in leaves if leave.acknowledged
            ],
            "settings": settings_data(setting),
        }
    )
