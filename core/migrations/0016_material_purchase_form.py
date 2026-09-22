from django.db import migrations


def add_material_purchase_form(apps, schema_editor):
    form = apps.get_model("core", "ApprovalFormTemplate")
    form.objects.get_or_create(
        slug="material-purchase-request",
        defaults={
            "category": "지원",
            "name": "자재구매신청서",
            "description": "자재 구매 및 반입 사진 기록",
            "default_title": "자재 구매 및 반입 신청",
            "default_content": "",
            "receivers": ["재경팀"],
            "references": ["구매 담당자"],
            "viewers": [],
            "public_receivers": [],
            "cooperation_department": "공무팀",
            "agreement": "합의 후 구매 진행",
            "document_layout": "purchase",
            "line_item_rows": 16,
            "approval_lines": [
                {
                    "id": "material-purchase-public-works-line",
                    "name": "김현정 대리 결재라인",
                    "userIds": ["김현정"],
                }
            ],
        },
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0015_device_push_token")]

    operations = [migrations.RunPython(add_material_purchase_form, migrations.RunPython.noop)]
