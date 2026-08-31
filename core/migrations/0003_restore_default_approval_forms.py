from django.db import migrations


DEFAULT_APPROVAL_FORMS = [
    {
        "slug": "business-draft",
        "category": "지원",
        "name": "업무기안[기본양식]",
        "description": "일반 기안 작성",
        "default_title": "정산을 위한 운영인력 충원의 건",
        "default_content": (
            "신규 콘텐츠 마케팅 진행에 따라 원활한 정산을 위한 운영 인력 채용 또는 "
            "내부 인력 배정을 요청드립니다.\n\n"
            "1. 요청 인원: 1명\n"
            "2. 필요 업무: 실시간 업무지원, 회계 처리, 세금계산서 대응\n"
            "3. 요청 사유: 캠페인 집행 증가에 따른 운영 부담 완화"
        ),
        "receivers": ["경영관리팀"],
        "references": ["부서장"],
        "viewers": ["운영지원 담당자"],
        "public_receivers": ["다우기술"],
        "cooperation_department": "경영관리팀",
        "agreement": "순차합의",
        "document_layout": "basic",
        "line_item_rows": 8,
        "recent_count": 15,
    },
    {
        "slug": "expense-slip",
        "category": "회계",
        "name": "지출 결의서(지급품의)",
        "description": "비용 지급 승인",
        "default_title": "교육장 기자재 대여 비용 집행 요청",
        "default_content": (
            "교육장 실습 장비 대여 비용 집행 승인을 요청드립니다.\n\n"
            "1. 대여 장비: 노트북 12대, 프로젝터 2대\n"
            "2. 사용 일정: 2026-07-03 ~ 2026-07-05\n"
            "3. 요청 금액: 2,850,000원"
        ),
        "receivers": ["재경팀"],
        "references": ["교육관리팀 부장"],
        "viewers": ["교육 대상자"],
        "public_receivers": ["다우기술"],
        "cooperation_department": "재경팀",
        "agreement": "예산 확인 후 지급",
        "document_layout": "expense",
        "line_item_rows": 32,
        "recent_count": 9,
    },
    {
        "slug": "purchase-request",
        "category": "지원",
        "name": "비품/소모품 구입신청서",
        "description": "비품 및 소모품 구매 요청",
        "default_title": "업무용 PC 구매 예산 할당 요청",
        "default_content": (
            "업무용 PC 구매 예산 할당 요청 재가 바랍니다.\n\n"
            "1. 구매 목적: 노후 PC 교체 및 교육 실습 장비 확보\n"
            "2. 구매 품목: 데스크톱 PC 6대, 모니터 6대\n"
            "3. 예산 요청: 9,600,000원"
        ),
        "receivers": ["재경팀"],
        "references": ["교육관리팀 부장", "구매 담당자"],
        "viewers": ["교육관리팀 구성원"],
        "public_receivers": ["다우기술"],
        "cooperation_department": "재경팀",
        "agreement": "합의 후 구매 진행",
        "document_layout": "purchase",
        "line_item_rows": 16,
        "recent_count": 5,
    },
    {
        "slug": "hospitality-expense",
        "category": "회계",
        "name": "지출결의서(기업업무추진비)",
        "description": "접대비 및 기업업무추진비 결재",
        "default_title": "기업업무추진비 집행 요청",
        "default_content": "업무 관련 접대비 집행 내역을 아래와 같이 상신합니다.",
        "receivers": ["재경팀"],
        "references": ["경영관리팀"],
        "viewers": ["회계 담당자"],
        "public_receivers": ["다우기술"],
        "cooperation_department": "재경팀",
        "agreement": "증빙 확인 후 지급",
        "document_layout": "hospitality",
        "line_item_rows": 24,
        "recent_count": 0,
    },
    {
        "slug": "payroll-draft",
        "category": "회계",
        "name": "급여대장 기안서",
        "description": "급여대장 인가 및 지급 기안",
        "default_title": "급여대장 지급 승인 요청",
        "default_content": "급여대장 지급 승인을 요청드립니다.",
        "receivers": ["경영관리팀"],
        "references": ["인사 담당자"],
        "viewers": ["급여 담당자"],
        "public_receivers": [],
        "cooperation_department": "경영관리팀",
        "agreement": "급여대장 확인",
        "document_layout": "payroll",
        "line_item_rows": 1,
        "recent_count": 0,
    },
    {
        "slug": "team-vacation",
        "category": "근태",
        "name": "팀 휴가 결재서",
        "description": "팀 휴가 일정 승인",
        "default_title": "7월 교육관리팀 팀 휴가 일정 승인",
        "default_content": (
            "교육관리팀 7월 휴가 일정을 아래와 같이 상신합니다.\n\n"
            "1. 휴가 기간: 2026-07-08 ~ 2026-07-12\n"
            "2. 대상자: 교육강사, 교육관리자, 운영지원 담당자\n"
            "3. 업무 인수인계: 이재오 차장이 교육 문의 1차 대응\n"
            "4. 요청사항: 팀 휴가 일정 승인 및 인사관리팀 공유"
        ),
        "receivers": ["인사관리팀"],
        "references": ["교육관리팀 부장", "운영지원 담당자"],
        "viewers": ["교육관리팀 구성원"],
        "public_receivers": ["다우기술"],
        "cooperation_department": "인사관리팀",
        "agreement": "팀 운영 일정 확인",
        "document_layout": "basic",
        "line_item_rows": 8,
        "recent_count": 12,
    },
    {
        "slug": "cooperation-request",
        "category": "협조",
        "name": "업무협조[기본양식]",
        "description": "타 부서 협조 요청",
        "default_title": "신규 교육 과정 운영 협조 요청",
        "default_content": (
            "신규 교육 과정 운영을 위한 부서 협조를 요청드립니다.\n\n"
            "1. 운영 일정: 2026-07-15 ~ 2026-07-30\n"
            "2. 협조 요청 부서: 운영팀, 재경팀\n"
            "3. 요청사항: 일정 공유 및 예산 집행 검토"
        ),
        "receivers": ["운영팀"],
        "references": ["교육관리팀 부장"],
        "viewers": ["경영지원팀"],
        "public_receivers": ["다우기술"],
        "cooperation_department": "운영팀",
        "agreement": "협조 승인",
        "document_layout": "basic",
        "line_item_rows": 8,
        "recent_count": 0,
    },
]


def restore_default_approval_forms(apps, schema_editor):
    approval_form = apps.get_model("core", "ApprovalFormTemplate")
    for values in DEFAULT_APPROVAL_FORMS:
        defaults = {key: value for key, value in values.items() if key != "slug"}
        approval_form.objects.get_or_create(slug=values["slug"], defaults=defaults)


class Migration(migrations.Migration):
    dependencies = [("core", "0002_portalsetting_custom_logo_base64_and_more")]

    operations = [
        migrations.RunPython(restore_default_approval_forms, migrations.RunPython.noop),
    ]
