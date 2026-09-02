from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import (
    ApprovalDocument,
    ApprovalFormTemplate,
    ApprovalHistory,
    ApprovalStep,
    Department,
    LeaveRequest,
    PortalSetting,
    User,
)


USERS = [
    ("edu_teacher", "교육강사", "교육관리팀", "대리", False),
    ("edu_manager", "교육관리자", "교육관리팀", "과장", True),
    ("lee_jaeo", "이재오", "교육관리팀", "차장", False),
    ("kim_kyunyoung", "김경영", "경영관리팀", "상무", False),
    ("jiyun", "정지윤", "마케팅팀", "대리", False),
    ("han_dev", "한유진", "개발팀", "과장", False),
    ("director", "정효정", "경영관리팀", "이사", False),
    ("ceo", "조상훈", "경영관리팀", "대표", False),
]

FORMS = [
    {
        "slug": "business-draft", "category": "지원", "name": "업무기안[기본양식]",
        "description": "일반 기안 작성", "default_title": "정산을 위한 운영인력 충원의 건",
        "default_content": "신규 업무 진행을 위한 운영 인력 배정을 요청드립니다.",
        "receivers": ["경영관리팀"], "references": ["부서장"], "viewers": ["운영지원 담당자"],
        "public_receivers": ["다우기술"], "cooperation_department": "경영관리팀",
        "agreement": "순차합의", "recent_count": 15,
    },
    {
        "slug": "expense-slip", "category": "회계", "name": "지출 결의서(지급품의)",
        "description": "비용 지급 승인", "default_title": "교육장 기자재 대여 비용 집행 요청",
        "default_content": "교육장 실습 장비 대여 비용 집행 승인을 요청드립니다.",
        "receivers": ["재경팀"], "references": ["교육관리팀 부장"], "viewers": ["교육 대상자"],
        "public_receivers": ["다우기술"], "cooperation_department": "재경팀",
        "agreement": "예산 확인 후 지급", "document_layout": "expense", "line_item_rows": 32,
        "recent_count": 9,
    },
    {
        "slug": "purchase-request", "category": "지원", "name": "비품/소모품 구입신청서",
        "description": "비품 및 소모품 구매 요청", "default_title": "업무용 PC 구매 예산 할당 요청",
        "default_content": "업무용 PC 구매 예산 할당 요청 재가 바랍니다.",
        "receivers": ["재경팀"], "references": ["구매 담당자"], "viewers": ["교육관리팀 구성원"],
        "public_receivers": ["다우기술"], "cooperation_department": "재경팀",
        "agreement": "합의 후 구매 진행", "document_layout": "purchase", "line_item_rows": 16,
        "recent_count": 5,
    },
    {
        "slug": "hospitality-expense", "category": "회계", "name": "지출결의서(기업업무추진비)",
        "description": "접대비 및 기업업무추진비 결재", "default_title": "기업업무추진비 집행 요청",
        "default_content": "업무 관련 접대비 집행 내역을 아래와 같이 상신합니다.",
        "receivers": ["재경팀"], "references": ["경영관리팀"], "viewers": ["회계 담당자"],
        "cooperation_department": "재경팀", "agreement": "증빙 확인 후 지급",
        "document_layout": "hospitality", "line_item_rows": 24,
    },
    {
        "slug": "team-vacation", "category": "근태", "name": "팀 휴가 결재서",
        "description": "팀 휴가 일정 승인", "default_title": "교육관리팀 팀 휴가 일정 승인",
        "default_content": "팀 휴가 일정 승인을 요청드립니다.",
        "receivers": ["인사관리팀"], "references": ["교육관리팀 부장"],
        "viewers": ["교육관리팀 구성원"], "cooperation_department": "인사관리팀",
        "agreement": "팀 운영 일정 확인", "recent_count": 12,
    },
]


class Command(BaseCommand):
    help = "로컬 개발용 조직, 계정, 양식, 결재 및 휴가 예시 데이터를 안전하게 생성합니다."

    @transaction.atomic
    def handle(self, *args, **options):
        accounts = {}
        for username, name, department_name, position, is_admin in USERS:
            department, _ = Department.get_or_create_at_end(department_name)
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": name,
                    "department": department,
                    "position": position,
                    "hire_date": date(2024, 1, 15),
                    "is_staff": is_admin,
                    "is_superuser": is_admin,
                },
            )
            if created:
                user.set_password("1234")
                user.save(update_fields=["password"])
            accounts[username] = user

        templates = {}
        for values in FORMS:
            slug = values["slug"]
            defaults = {key: value for key, value in values.items() if key != "slug"}
            form, _ = ApprovalFormTemplate.objects.get_or_create(slug=slug, defaults=defaults)
            templates[slug] = form

        today = timezone.localdate()
        documents = [
            ("APR-2608-001", "6월 마케팅 캠페인 예산 승인", "jiyun", "expense-slip", "4,800,000원 규모의 캠페인 광고비와 운영비 집행 승인을 요청드립니다."),
            ("APR-2608-002", "신규 노트북 구매 요청", "han_dev", "purchase-request", "개발 장비 노후화에 따라 신규 노트북 구매를 요청드립니다."),
            ("APR-2608-003", "사용자 교육 기안입니다.", "edu_teacher", "business-draft", "신규 사용자 교육 일정과 자료 준비 승인을 요청드립니다."),
        ]
        for offset, (public_id, title, drafter_id, form_id, content) in enumerate(documents):
            drafter = accounts[drafter_id]
            form = templates[form_id]
            document, created = ApprovalDocument.objects.get_or_create(
                public_id=public_id,
                defaults={
                    "title": title,
                    "drafter": drafter,
                    "department_name": drafter.department.name,
                    "form_template": form,
                    "form_name": form.name,
                    "status": ApprovalDocument.Status.PENDING,
                    "drafted_at": today - timedelta(days=offset + 1),
                    "due_date": today + timedelta(days=3 + offset),
                    "progress": 33,
                    "document_no": public_id,
                    "effective_date": today + timedelta(days=3 + offset),
                    "cooperation_department": form.cooperation_department,
                    "agreement": form.agreement,
                    "content": content,
                    "received_request": True,
                    "can_cancel": True,
                    "can_edit": False,
                    "receivers": form.receivers,
                    "references": form.references,
                    "viewers": form.viewers,
                    "public_receivers": form.public_receivers,
                    "document_layout": form.document_layout,
                },
            )
            if created:
                steps = [
                    (drafter, "신청", "완료"),
                    (accounts["edu_manager"], "승인", "진행중"),
                    (accounts["ceo"], "승인", "예정"),
                ]
                ApprovalStep.objects.bulk_create([
                    ApprovalStep(
                        document=document, order=index, approver=approver,
                        name=approver.display_name, department=approver.department.name,
                        step_type=step_type, role=approver.position, status=status,
                        approved_at=timezone.now() if status == "완료" else None,
                    )
                    for index, (approver, step_type, status) in enumerate(steps)
                ])
                ApprovalHistory.objects.create(
                    public_id=f"HIS-SEED-{offset + 1}", document=document,
                    category="결재문서 변경", actor=drafter,
                    actor_label=f"{drafter.display_name} {drafter.position}",
                    description="결재 요청 상신", snapshot=title,
                )

        teacher = accounts["edu_teacher"]
        LeaveRequest.objects.get_or_create(
            public_id="LEAVE-SEED-1",
            defaults={
                "user": teacher, "leave_type": "연차", "start_date": date(2026, 5, 4),
                "end_date": date(2026, 5, 4), "days": 1, "reason": "개인 일정",
                "status": LeaveRequest.Status.APPROVED, "ceo_status": "완료", "acknowledged": True,
            },
        )
        PortalSetting.load()
        self.stdout.write(self.style.SUCCESS("로컬 데모 데이터 준비가 완료되었습니다."))
        self.stdout.write("로그인: edu_manager / 1234 (관리자), edu_teacher / 1234 (일반 사용자)")
