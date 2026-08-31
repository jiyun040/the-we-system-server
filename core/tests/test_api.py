import json
from importlib import import_module

from django.apps import apps
from django.core.management import call_command
from django.test import TestCase, override_settings

from core.models import (
    ApprovalDocument,
    ApprovalFormTemplate,
    Department,
    LeaveRequest,
    PortalSetting,
    User,
)


@override_settings(DEV_ALLOW_ANONYMOUS=True, DEV_DEFAULT_USERNAME="edu_manager")
class ApiFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", verbosity=0)

    def login(self, username="edu_manager", password="1234"):
        response = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"id": username, "password": password}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["token"]

    def headers(self, token):
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_health_and_current_flutter_compatibility_endpoint(self):
        self.assertEqual(self.client.get("/api/v1/health").json(), {"status": "ok"})
        response = self.client.get("/approvals/dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn("processingDocuments", response.json())
        self.assertGreaterEqual(response.json()["pendingCount"], 1)

    def test_flutter_web_origin_receives_cors_headers(self):
        response = self.client.options(
            "/api/v1/approvals/dashboard",
            HTTP_ORIGIN="http://localhost:8080",
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["Access-Control-Allow-Origin"], "http://localhost:8080")

    def test_login_and_me(self):
        token = self.login()
        response = self.client.get("/api/v1/auth/me", **self.headers(token))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["id"], "edu_manager")
        self.assertNotIn("password", response.json()["user"])

    def test_direct_registration_rejects_unregistered_employee(self):
        user_count = User.objects.count()
        department_count = Department.objects.count()
        payload = {
            "id": "direct_signup",
            "password": "safe-password-1234",
            "name": "직접가입",
            "department": "외부생성부서",
            "position": "사원",
            "email": "direct-signup@example.com",
        }

        response = self.client.post(
            "/api/v1/auth/register",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "registration_not_allowed")

        self.assertEqual(User.objects.count(), user_count)
        self.assertEqual(Department.objects.count(), department_count)
        self.assertFalse(User.objects.filter(username="direct_signup").exists())

    def test_registered_employee_can_sign_up_without_receiving_a_token(self):
        response = self.client.post(
            "/api/v1/auth/register",
            data=json.dumps({
                "id": "kim_hyeonjeong",
                "password": "safe-password-1234",
                "name": "김현정",
                "department": "공무",
                "position": "대리",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertNotIn("token", response.json())
        user = User.objects.get(username="kim_hyeonjeong")
        self.assertEqual(user.first_name, "김현정")
        self.assertEqual(user.department.name, "공무")
        self.assertTrue(user.check_password("safe-password-1234"))

    def test_bootstrap_restores_remote_application_state(self):
        token = self.login()
        response = self.client.get("/api/v1/bootstrap", **self.headers(token))
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["currentUser"]["id"], "edu_manager")
        self.assertGreaterEqual(len(body["accounts"]), 2)
        self.assertGreaterEqual(len(body["formTemplates"]), 1)
        self.assertGreaterEqual(len(body["documents"]), 1)
        self.assertIn("enabledAppIds", body["settings"])
        self.assertIn("departments", body)

    def test_default_form_restore_preserves_custom_forms_and_portal_settings(self):
        customized = ApprovalFormTemplate.objects.get(slug="business-draft")
        customized.name = "내가 수정한 업무기안"
        customized.default_title = "커스텀 제목"
        customized.save(update_fields=["name", "default_title"])
        custom_form = ApprovalFormTemplate.objects.create(
            slug="my-custom-form",
            category="사용자 정의",
            name="내 커스텀 양식",
            default_title="직접 만든 제목",
        )
        ApprovalFormTemplate.objects.filter(slug="payroll-draft").delete()

        settings = PortalSetting.load()
        settings.portal_name = "커스텀 포털명"
        settings.monthly_leave_per_month = 2
        settings.enabled_app_ids = ["approval"]
        settings.save(
            update_fields=[
                "portal_name",
                "monthly_leave_per_month",
                "enabled_app_ids",
            ]
        )

        migration = import_module(
            "core.migrations.0003_restore_default_approval_forms"
        )
        migration.restore_default_approval_forms(apps, None)

        customized.refresh_from_db()
        custom_form.refresh_from_db()
        settings.refresh_from_db()
        self.assertEqual(customized.name, "내가 수정한 업무기안")
        self.assertEqual(customized.default_title, "커스텀 제목")
        self.assertEqual(custom_form.name, "내 커스텀 양식")
        self.assertTrue(
            ApprovalFormTemplate.objects.filter(slug="payroll-draft").exists()
        )
        self.assertEqual(settings.portal_name, "커스텀 포털명")
        self.assertEqual(settings.monthly_leave_per_month, 2)
        self.assertEqual(settings.enabled_app_ids, ["approval"])

    def test_department_and_employee_crud(self):
        token = self.login()
        headers = self.headers(token)
        created_department = self.client.post(
            "/api/v1/organization/departments",
            data=json.dumps({"name": "신규부서"}),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(created_department.status_code, 201, created_department.content)
        department_id = created_department.json()["id"]

        created_employee = self.client.post(
            "/api/v1/organization/employees",
            data=json.dumps({
                "id": "new_member",
                "password": "safe-password-1234",
                "name": "신규직원",
                "department": "신규부서",
                "position": "사원",
                "email": "new-member@example.com",
                "hireDate": "2026-08-31",
            }),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(created_employee.status_code, 201, created_employee.content)

        updated_employee = self.client.patch(
            "/api/v1/organization/employees/new_member",
            data=json.dumps({"name": "수정직원", "email": "updated@example.com"}),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(updated_employee.status_code, 200, updated_employee.content)
        self.assertEqual(updated_employee.json()["user"]["name"], "수정직원")

        nonempty_delete = self.client.delete(
            f"/api/v1/organization/departments/{department_id}", **headers
        )
        self.assertEqual(nonempty_delete.status_code, 409)

        deleted_employee = self.client.delete(
            "/api/v1/organization/employees/new_member", **headers
        )
        self.assertEqual(deleted_employee.status_code, 204)
        self.assertFalse(User.objects.get(username="new_member").is_active)

        deleted_department = self.client.delete(
            f"/api/v1/organization/departments/{department_id}", **headers
        )
        self.assertEqual(deleted_department.status_code, 204)
        self.assertFalse(Department.objects.filter(pk=department_id).exists())

    def test_super_admin_is_hidden_from_employee_and_organization_data(self):
        department = Department.objects.create(name="시스템관리")
        User.objects.create_superuser(
            username="admin",
            password="admin0630",
            first_name="슈퍼어드민",
            email="admin@example.invalid",
            department=department,
            position="시스템 관리자",
        )
        token = self.login("admin", "admin0630")

        bootstrap = self.client.get(
            "/api/v1/bootstrap", **self.headers(token)
        ).json()
        self.assertEqual(bootstrap["currentUser"]["id"], "admin")
        self.assertNotIn("admin", [item["id"] for item in bootstrap["accounts"]])

        employees = self.client.get(
            "/api/v1/organization/employees", **self.headers(token)
        ).json()["employees"]
        self.assertNotIn("admin", [item["id"] for item in employees])

        departments = self.client.get(
            "/api/v1/organization/departments", **self.headers(token)
        ).json()["departments"]
        self.assertNotIn("시스템관리", [item["name"] for item in departments])

        detail = self.client.patch(
            "/api/v1/organization/employees/admin",
            data=json.dumps({"position": "노출되면 안 됨"}),
            content_type="application/json",
            **self.headers(token),
        )
        self.assertEqual(detail.status_code, 404)

    def test_password_otp_and_settings_round_trip(self):
        token = self.login()
        password = self.client.post(
            "/api/v1/auth/verify-password",
            data=json.dumps({"password": "1234"}),
            content_type="application/json",
            **self.headers(token),
        )
        self.assertTrue(password.json()["valid"])
        otp = self.client.post(
            "/api/v1/admin/verify-otp",
            data=json.dumps({"otp": "123456"}),
            content_type="application/json",
            **self.headers(token),
        )
        self.assertTrue(otp.json()["valid"])
        updated = self.client.patch(
            "/api/v1/settings",
            data=json.dumps({
                "portalName": "연동 테스트 포털",
                "enabledAppIds": ["approval", "leave"],
                "organizationWideDocumentCategories": ["지원"],
                "documentCategoryViewerIds": {"회계": ["edu_teacher"]},
            }),
            content_type="application/json",
            **self.headers(token),
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(updated.json()["portalName"], "연동 테스트 포털")
        bootstrap = self.client.get("/api/v1/bootstrap", **self.headers(token)).json()
        self.assertEqual(bootstrap["settings"]["enabledAppIds"], ["approval", "leave"])

    def test_approval_advances_to_next_step(self):
        token = self.login()
        response = self.client.post(
            "/api/v1/approvals/APR-2608-001/approve",
            data=json.dumps({"opinion": "확인했습니다."}),
            content_type="application/json",
            **self.headers(token),
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["steps"][1]["status"], "완료")
        self.assertEqual(body["steps"][2]["status"], "진행중")
        self.assertFalse(body["canCancel"])

    def test_create_and_submit_draft(self):
        token = self.login("edu_teacher")
        created = self.client.post(
            "/api/v1/approvals/documents",
            data=json.dumps({"formId": "business-draft", "title": "새 기안", "content": "본문"}),
            content_type="application/json",
            **self.headers(token),
        )
        self.assertEqual(created.status_code, 201, created.content)
        draft_id = created.json()["id"]
        submitted = self.client.post(
            f"/api/v1/approvals/documents/{draft_id}/submit",
            data="{}",
            content_type="application/json",
            **self.headers(token),
        )
        self.assertEqual(submitted.status_code, 200, submitted.content)
        self.assertTrue(submitted.json()["id"].startswith("APR-"))
        self.assertEqual(submitted.json()["status"], "결재대기")

    def test_leave_request_and_admin_approval(self):
        user_token = self.login("edu_teacher")
        response = self.client.post(
            "/api/v1/leave/requests",
            data=json.dumps({
                "type": "연차", "startDate": "2026-09-01", "endDate": "2026-09-01",
                "days": 1, "reason": "개인 일정",
            }),
            content_type="application/json",
            **self.headers(user_token),
        )
        self.assertEqual(response.status_code, 201, response.content)
        leave_id = response.json()["id"]
        admin_token = self.login()
        approved = self.client.post(
            f"/api/v1/leave/requests/{leave_id}/approve",
            data="{}",
            content_type="application/json",
            **self.headers(admin_token),
        )
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.json()["status"], "승인")
        self.assertEqual(LeaveRequest.objects.get(public_id=leave_id).status, "승인")

    def test_leave_request_creates_ceo_approval_document(self):
        user_token = self.login("edu_teacher")
        response = self.client.post(
            "/api/v1/leave/requests",
            data=json.dumps({
                "type": "반차", "startDate": "2026-09-02", "endDate": "2026-09-02",
                "days": 0.5, "reason": "병원 방문",
            }),
            content_type="application/json",
            **self.headers(user_token),
        )
        self.assertEqual(response.status_code, 201, response.content)
        leave_id = response.json()["id"]
        document_id = f"LEAVE-DOC-{leave_id}"
        self.assertTrue(ApprovalDocument.objects.filter(public_id=document_id).exists())

        ceo_token = self.login("ceo")
        bootstrap = self.client.get(
            "/api/v1/bootstrap", **self.headers(ceo_token)
        ).json()
        self.assertIn(document_id, {item["id"] for item in bootstrap["documents"]})
        approved = self.client.post(
            f"/api/v1/leave/requests/{leave_id}/approve",
            data="{}",
            content_type="application/json",
            **self.headers(ceo_token),
        )
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(
            ApprovalDocument.objects.get(public_id=document_id).status,
            ApprovalDocument.Status.APPROVED,
        )

    def test_regular_user_cannot_self_approve_direct_leave(self):
        token = self.login("edu_teacher")
        response = self.client.post(
            "/api/v1/leave/requests",
            data=json.dumps({
                "type": "연차", "startDate": "2026-09-03", "endDate": "2026-09-03",
                "days": 1, "reason": "개인 일정", "directEntry": True,
            }),
            content_type="application/json",
            **self.headers(token),
        )
        self.assertEqual(response.status_code, 403)

    @override_settings(DEV_ALLOW_ANONYMOUS=False)
    def test_protected_endpoint_rejects_anonymous_requests(self):
        response = self.client.get("/api/v1/organization/employees")
        self.assertEqual(response.status_code, 401)
