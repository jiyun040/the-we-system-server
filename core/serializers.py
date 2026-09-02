from django.utils import timezone

from .admin_access import can_change_admin_otp


def iso_date(value):
    return value.isoformat() if value else ""


def user_data(user):
    return {
        "id": user.username,
        "name": user.display_name,
        "department": user.department.name if user.department else "",
        "position": user.position,
        "hireDate": iso_date(user.hire_date),
        "isAdmin": user.is_staff,
        "canChangeAdminOtp": can_change_admin_otp(user),
        "annualLeaveDays": (
            float(user.annual_leave_days)
            if user.annual_leave_days is not None
            else None
        ),
        "monthlyLeaveDays": (
            float(user.monthly_leave_days)
            if user.monthly_leave_days is not None
            else None
        ),
        "leaveBalanceAdjustment": float(user.leave_balance_adjustment),
    }


def form_data(form, recent_count=None):
    return {
        "id": form.slug,
        "category": form.category,
        "name": form.name,
        "description": form.description,
        "defaultTitle": form.default_title,
        "defaultContent": form.default_content,
        "receivers": form.receivers,
        "references": form.references,
        "viewers": form.viewers,
        "publicReceivers": form.public_receivers,
        "cooperationDepartment": form.cooperation_department,
        "agreement": form.agreement,
        "documentLayout": form.document_layout,
        "lineItemRows": form.line_item_rows,
        "approvalLines": form.approval_lines,
        "enabled": form.is_enabled,
        "recentCount": form.recent_count if recent_count is None else recent_count,
    }


def step_data(step):
    return {
        "name": step.name,
        "department": step.department,
        "type": step.step_type,
        "role": step.role,
        "status": "결재 예정" if step.status == "예정" else step.status,
        "approvedAt": timezone.localtime(step.approved_at).strftime("%m.%d %H:%M")
        if step.approved_at
        else None,
        "delegatedBy": step.delegated_by or None,
        "requiresOriginalApproval": step.requires_original_approval,
    }


def history_data(history):
    return {
        "id": history.public_id,
        "category": history.category,
        "date": timezone.localtime(history.occurred_at).strftime("%Y-%m-%d %H:%M"),
        "user": history.actor_label,
        "description": history.description,
        "snapshot": history.snapshot,
    }


def attachment_data(attachment):
    return {
        "name": attachment.name,
        "mimeType": attachment.mime_type,
        "base64Data": attachment.base64_data,
    }


def document_data(document):
    return {
        "id": document.public_id,
        "title": document.title,
        "drafter": document.drafter.display_name,
        "department": document.department_name,
        "form": document.form_name,
        "status": document.status,
        "draftedAt": iso_date(document.drafted_at),
        "dueDate": iso_date(document.due_date),
        "progress": document.progress,
        "documentNo": document.document_no,
        "effectiveDate": iso_date(document.effective_date),
        "cooperationDepartment": document.cooperation_department,
        "agreement": document.agreement,
        "content": document.content,
        "urgent": document.urgent,
        "receivedRequest": document.received_request,
        "canCancel": document.can_cancel,
        "canReuse": document.can_reuse,
        "canEdit": document.can_edit,
        "departmentVisible": document.department_visible,
        "receivers": document.receivers,
        "references": document.references,
        "viewers": document.viewers,
        "publicReceivers": document.public_receivers,
        "linkedDocuments": document.linked_documents,
        "attachments": [attachment_data(item) for item in document.attachments.all()],
        "documentLayout": document.document_layout,
        "formFields": document.form_fields,
        "lineItems": document.line_items,
        "steps": [step_data(item) for item in document.steps.all()],
        "histories": [history_data(item) for item in document.histories.all()],
    }


def leave_data(request):
    return {
        "id": request.public_id,
        "userId": request.user.username,
        "userName": request.user.display_name,
        "department": request.user.department.name if request.user.department else "",
        "type": request.leave_type,
        "startDate": iso_date(request.start_date),
        "endDate": iso_date(request.end_date),
        "days": float(request.days),
        "reason": request.reason,
        "status": request.status,
        "ceoStatus": request.ceo_status,
        "rejectedBy": request.rejected_by,
        "directEntry": request.direct_entry,
        "registeredBy": request.registered_by.display_name if request.registered_by else "",
        "acknowledged": request.acknowledged,
    }


def notice_data(notice):
    return {
        "id": str(notice.pk),
        "title": notice.title,
        "content": notice.content,
        "authorName": notice.author.display_name,
        "isPinned": notice.is_pinned,
        "createdAt": notice.created_at.isoformat(),
        "updatedAt": notice.updated_at.isoformat(),
    }


def settings_data(setting):
    return {
        "portalName": setting.portal_name,
        "annualLeaveByYear": setting.annual_leave_by_year,
        "monthlyLeavePerMonth": setting.monthly_leave_per_month,
        "adminOtpEnabled": setting.admin_otp_enabled,
        "settingsPasswordEnabled": setting.settings_password_enabled,
        "adminDocumentAccessEnabled": setting.admin_document_access_enabled,
        "customLogoBase64": setting.custom_logo_base64,
        "customLogoFileName": setting.custom_logo_file_name,
        "enabledAppIds": setting.enabled_app_ids,
        "organizationWideDocumentCategories": setting.organization_wide_document_categories,
        "documentCategoryViewerIds": setting.document_category_viewer_ids,
    }
