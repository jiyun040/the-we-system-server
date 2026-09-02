import hashlib
import secrets
from datetime import date, timedelta

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.utils import timezone


def default_annual_leave_policy():
    return {"1": 15, "2": 15, "3": 16, "4": 16, "5": 17, "10": 19}


def default_enabled_apps():
    return ["approval", "attendance", "leave"]


def default_wide_document_categories():
    return ["지원", "회계", "근태", "협조"]


class EmailFreeUserManager(UserManager):
    use_in_migrations = False

    def _create_user_object(self, username, email, password, **extra_fields):
        if not username:
            raise ValueError("아이디는 필수입니다.")
        username = self.model.normalize_username(username)
        user = self.model(username=username, **extra_fields)
        user.password = make_password(password)
        return user


class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "name"]

    @classmethod
    def get_or_create_at_end(cls, name):
        existing = cls.objects.filter(name=name).first()
        if existing is not None:
            return existing, False
        current_max = cls.objects.aggregate(value=models.Max("sort_order"))["value"]
        return cls.objects.get_or_create(
            name=name,
            defaults={"sort_order": (current_max if current_max is not None else -1) + 1},
        )

    def __str__(self):
        return self.name


class User(AbstractUser):
    email = None
    objects = EmailFreeUserManager()
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.PROTECT, related_name="members"
    )
    position = models.CharField(max_length=50, blank=True)
    hire_date = models.DateField(default=date.today)
    admin_otp_hash = models.CharField(max_length=128, blank=True)
    annual_leave_days = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
    )
    monthly_leave_days = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
    )
    leave_balance_adjustment = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        default=0,
    )

    @property
    def display_name(self):
        return self.get_full_name().strip() or self.username


class ApiToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="api_tokens")
    key_hash = models.CharField(max_length=64, unique=True)
    prefix = models.CharField(max_length=12, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    last_used_at = models.DateTimeField(null=True, blank=True)

    @classmethod
    def issue(cls, user, ttl_hours=168):
        raw = secrets.token_urlsafe(40)
        cls.objects.create(
            user=user,
            key_hash=hashlib.sha256(raw.encode()).hexdigest(),
            prefix=raw[:12],
            expires_at=timezone.now() + timedelta(hours=ttl_hours),
        )
        return raw

    @classmethod
    def resolve(cls, raw):
        if not raw:
            return None
        key_hash = hashlib.sha256(raw.encode()).hexdigest()
        token = cls.objects.select_related("user", "user__department").filter(
            key_hash=key_hash, expires_at__gt=timezone.now(), user__is_active=True
        ).first()
        if token:
            cls.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
        return token


class ApprovalFormTemplate(models.Model):
    slug = models.SlugField(max_length=80, unique=True)
    category = models.CharField(max_length=80)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True)
    default_title = models.CharField(max_length=255)
    default_content = models.TextField(blank=True)
    receivers = models.JSONField(default=list, blank=True)
    references = models.JSONField(default=list, blank=True)
    viewers = models.JSONField(default=list, blank=True)
    public_receivers = models.JSONField(default=list, blank=True)
    cooperation_department = models.CharField(max_length=100, blank=True)
    agreement = models.CharField(max_length=255, blank=True)
    document_layout = models.CharField(max_length=30, default="basic")
    line_item_rows = models.PositiveSmallIntegerField(default=8)
    approval_lines = models.JSONField(default=list, blank=True)
    is_enabled = models.BooleanField(default=True)
    recent_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "name"]


class ApprovalDocument(models.Model):
    class Status(models.TextChoices):
        DRAFT = "작성중", "작성중"
        PENDING = "결재대기", "결재대기"
        REVIEW = "검토중", "검토중"
        PROCESSING = "진행중", "진행중"
        APPROVED = "완료", "완료"
        REJECTED = "반려", "반려"
        CANCELED = "취소", "취소"

    public_id = models.CharField(max_length=40, unique=True, db_index=True)
    title = models.CharField(max_length=255)
    drafter = models.ForeignKey(User, on_delete=models.PROTECT, related_name="drafted_documents")
    department_name = models.CharField(max_length=100)
    form_template = models.ForeignKey(
        ApprovalFormTemplate, null=True, blank=True, on_delete=models.SET_NULL, related_name="documents"
    )
    form_name = models.CharField(max_length=120)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    drafted_at = models.DateField(default=date.today)
    due_date = models.DateField(default=date.today)
    progress = models.PositiveSmallIntegerField(default=0)
    document_no = models.CharField(max_length=60, blank=True)
    effective_date = models.DateField(default=date.today)
    cooperation_department = models.CharField(max_length=100, blank=True)
    agreement = models.CharField(max_length=255, blank=True)
    content = models.TextField(blank=True)
    urgent = models.BooleanField(default=False)
    received_request = models.BooleanField(default=False)
    can_cancel = models.BooleanField(default=False)
    can_reuse = models.BooleanField(default=True)
    can_edit = models.BooleanField(default=True)
    department_visible = models.BooleanField(default=True)
    receivers = models.JSONField(default=list, blank=True)
    references = models.JSONField(default=list, blank=True)
    viewers = models.JSONField(default=list, blank=True)
    public_receivers = models.JSONField(default=list, blank=True)
    linked_documents = models.JSONField(default=list, blank=True)
    document_layout = models.CharField(max_length=30, default="basic")
    form_fields = models.JSONField(default=dict, blank=True)
    line_items = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-drafted_at", "-created_at"]


class ApprovalStep(models.Model):
    document = models.ForeignKey(ApprovalDocument, on_delete=models.CASCADE, related_name="steps")
    order = models.PositiveSmallIntegerField()
    approver = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    name = models.CharField(max_length=100)
    department = models.CharField(max_length=100, blank=True)
    step_type = models.CharField(max_length=30, default="결재")
    role = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, default="예정")
    approved_at = models.DateTimeField(null=True, blank=True)
    delegated_by = models.CharField(max_length=100, blank=True)
    requires_original_approval = models.BooleanField(default=False)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["document", "order"], name="unique_document_step_order")
        ]


class ApprovalHistory(models.Model):
    public_id = models.CharField(max_length=60, unique=True)
    document = models.ForeignKey(ApprovalDocument, on_delete=models.CASCADE, related_name="histories")
    category = models.CharField(max_length=80)
    occurred_at = models.DateTimeField(default=timezone.now)
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    actor_label = models.CharField(max_length=120)
    description = models.CharField(max_length=500)
    snapshot = models.TextField(blank=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]


class ApprovalAttachment(models.Model):
    document = models.ForeignKey(ApprovalDocument, on_delete=models.CASCADE, related_name="attachments")
    name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=120, default="application/octet-stream")
    base64_data = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class LeaveRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "승인대기", "승인대기"
        APPROVED = "승인", "승인"
        REJECTED = "반려", "반려"
        CANCELED = "취소", "취소"

    public_id = models.CharField(max_length=40, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="leave_requests")
    leave_type = models.CharField(max_length=50)
    start_date = models.DateField()
    end_date = models.DateField()
    days = models.DecimalField(max_digits=5, decimal_places=1)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    ceo_status = models.CharField(max_length=20, default="진행중")
    rejected_by = models.CharField(max_length=100, blank=True)
    direct_entry = models.BooleanField(default=False)
    registered_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="registered_leave_requests"
    )
    acknowledged = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_date", "-created_at"]


class Notice(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField()
    author = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="notices",
    )
    is_pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_pinned", "-created_at", "-id"]


class PortalSetting(models.Model):
    singleton_key = models.PositiveSmallIntegerField(default=1, unique=True, editable=False)
    portal_name = models.CharField(max_length=100, default="더우리기술 전자결재")
    annual_leave_by_year = models.JSONField(default=default_annual_leave_policy)
    monthly_leave_per_month = models.PositiveSmallIntegerField(default=1)
    admin_otp_enabled = models.BooleanField(default=True)
    settings_password_enabled = models.BooleanField(default=True)
    admin_document_access_enabled = models.BooleanField(default=True)
    custom_logo_base64 = models.TextField(blank=True)
    custom_logo_file_name = models.CharField(max_length=255, blank=True)
    enabled_app_ids = models.JSONField(default=default_enabled_apps)
    organization_wide_document_categories = models.JSONField(
        default=default_wide_document_categories
    )
    document_category_viewer_ids = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(singleton_key=1)
        return obj
