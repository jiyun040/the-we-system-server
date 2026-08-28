from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    ApprovalAttachment,
    ApprovalDocument,
    ApprovalFormTemplate,
    ApprovalHistory,
    ApprovalStep,
    Department,
    LeaveRequest,
    PortalSetting,
    User,
)


@admin.register(User)
class TheWeUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("조직 정보", {"fields": ("department", "position", "hire_date")}),
    )
    list_display = ("username", "display_name", "department", "position", "is_staff", "is_active")


class StepInline(admin.TabularInline):
    model = ApprovalStep
    extra = 0


class HistoryInline(admin.TabularInline):
    model = ApprovalHistory
    extra = 0
    readonly_fields = ("occurred_at",)


class AttachmentInline(admin.TabularInline):
    model = ApprovalAttachment
    extra = 0
    exclude = ("base64_data",)


@admin.register(ApprovalDocument)
class ApprovalDocumentAdmin(admin.ModelAdmin):
    list_display = ("public_id", "title", "drafter", "department_name", "status", "drafted_at")
    list_filter = ("status", "department_name", "urgent")
    search_fields = ("public_id", "title", "drafter__username", "drafter__first_name")
    inlines = (StepInline, HistoryInline, AttachmentInline)


admin.site.register(Department)
admin.site.register(ApprovalFormTemplate)
admin.site.register(LeaveRequest)
admin.site.register(PortalSetting)
