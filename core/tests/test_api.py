import json
from datetime import date
from importlib import import_module

from django.apps import apps
from django.core.management import call_command
from django.test import TestCase, override_settings

from core.admin_access import (
    DESIGNATED_ADMIN_DEPARTMENT,
    DESIGNATED_ADMIN_NAME,
    DESIGNATED_ADMIN_POSITION,
    DESIGNATED_ADMIN_USERNAME,
)
from core.models import (
    ApprovalDocument,
    ApprovalFormTemplate,
    Department,
    LeaveRequest,
    Notice,
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
        self.assertNotIn("email", response.json()["user"])

    def test_direct_registration_rejects_unregistered_employee(self):
        user_count = User.objects.count()
        department_count = Department.objects.count()
        payload = {
            "id": "direct_signup",
            "password": "safe-password-1234",
            "name": "직접가입",
            "department": "외부생성부서",
            "position": "사원",
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

    def test_designated_account_receives_server_admin_permission(self):
        response = self.client.post(
            "/api/v1/auth/register",
            data=json.dumps({
                "id": DESIGNATED_ADMIN_USERNAME,
                "password": "safe-password-1234",
                "name": DESIGNATED_ADMIN_NAME,
                "department": DESIGNATED_ADMIN_DEPARTMENT,
                "position": DESIGNATED_ADMIN_POSITION,
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(response.json()["user"]["isAdmin"])
        self.assertTrue(response.json()["user"]["canChangeAdminOtp"])
        user = User.objects.get(username=DESIGNATED_ADMIN_USERNAME)
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)

        token = self.login(DESIGNATED_ADMIN_USERNAME, "safe-password-1234")
        setting = PortalSetting.load()
        setting.admin_otp_enabled = False
        setting.save(update_fields=["admin_otp_enabled"])
        invalid_otp = self.client.post(
            "/api/v1/admin/verify-otp",
            data=json.dumps({"otp": "000000"}),
            content_type="application/json",
            **self.headers(token),
        )
        otp = self.client.post(
            "/api/v1/admin/verify-otp",
            data=json.dumps({"otp": "123456"}),
            content_type="application/json",
            **self.headers(token),
        )
        self.assertFalse(invalid_otp.json()["valid"])
        self.assertEqual(otp.status_code, 200, otp.content)
        self.assertTrue(otp.json()["valid"])

        wrong_current = self.client.post(
            "/api/v1/admin/change-otp",
            data=json.dumps({"currentOtp": "000000", "newOtp": "654321"}),
            content_type="application/json",
            **self.headers(token),
        )
        self.assertEqual(wrong_current.status_code, 400, wrong_current.content)
        self.assertEqual(
            wrong_current.json()["error"]["code"],
            "invalid_current_otp",
        )

        changed = self.client.post(
            "/api/v1/admin/change-otp",
            data=json.dumps({"currentOtp": "123456", "newOtp": "654321"}),
            content_type="application/json",
            **self.headers(token),
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        self.assertTrue(changed.json()["changed"])
        user.refresh_from_db()
        self.assertTrue(user.admin_otp_hash)
        self.assertNotEqual(user.admin_otp_hash, "654321")

        old_otp = self.client.post(
            "/api/v1/admin/verify-otp",
            data=json.dumps({"otp": "123456"}),
            content_type="application/json",
            **self.headers(token),
        )
        new_otp = self.client.post(
            "/api/v1/admin/verify-otp",
            data=json.dumps({"otp": "654321"}),
            content_type="application/json",
            **self.headers(token),
        )
        self.assertFalse(old_otp.json()["valid"])
        self.assertTrue(new_otp.json()["valid"])

    def test_super_admin_otp_remains_fixed(self):
        department, _ = Department.objects.get_or_create(name="시스템관리")
        User.objects.create_superuser(
            username="admin",
            password="admin-password",
            first_name="시스템 관리자",
            department=department,
            position="관리자",
        )
        token = self.login("admin", "admin-password")

        me = self.client.get("/api/v1/auth/me", **self.headers(token))
        self.assertFalse(me.json()["user"]["canChangeAdminOtp"])

        fixed_otp = self.client.post(
            "/api/v1/admin/verify-otp",
            data=json.dumps({"otp": "123456"}),
            content_type="application/json",
            **self.headers(token),
        )
        other_otp = self.client.post(
            "/api/v1/admin/verify-otp",
            data=json.dumps({"otp": "654321"}),
            content_type="application/json",
            **self.headers(token),
        )
        self.assertTrue(fixed_otp.json()["valid"])
        self.assertFalse(other_otp.json()["valid"])

        change = self.client.post(
            "/api/v1/admin/change-otp",
            data=json.dumps({"currentOtp": "123456", "newOtp": "654321"}),
            content_type="application/json",
            **self.headers(token),
        )
        self.assertEqual(change.status_code, 403, change.content)
        self.assertEqual(
            change.json()["error"]["code"],
            "admin_otp_change_not_allowed",
        )

    def test_designated_admin_and_super_admin_can_manage_notices(self):
        department, _ = Department.objects.get_or_create(
            name=DESIGNATED_ADMIN_DEPARTMENT
        )
        User.objects.create_user(
            username=DESIGNATED_ADMIN_USERNAME,
            password="safe-password-1234",
            first_name=DESIGNATED_ADMIN_NAME,
            department=department,
            position=DESIGNATED_ADMIN_POSITION,
            is_staff=True,
        )
        token = self.login(DESIGNATED_ADMIN_USERNAME, "safe-password-1234")

        created = self.client.post(
            "/api/v1/notices",
            data=json.dumps({
                "title": "테스트 공지",
                "content": "공지 내용입니다.",
                "isPinned": True,
            }),
            content_type="application/json",
            **self.headers(token),
        )
        self.assertEqual(created.status_code, 201, created.content)
        notice_id = created.json()["id"]
        self.assertTrue(created.json()["isPinned"])

        bootstrap = self.client.get(
            "/api/v1/bootstrap",
            **self.headers(self.login("edu_teacher")),
        )
        self.assertEqual(bootstrap.status_code, 200, bootstrap.content)
        self.assertEqual(bootstrap.json()["notices"][0]["title"], "테스트 공지")

        updated = self.client.patch(
            f"/api/v1/notices/{notice_id}",
            data=json.dumps({"title": "수정 공지", "isPinned": False}),
            content_type="application/json",
            **self.headers(token),
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(updated.json()["title"], "수정 공지")

        system_department, _ = Department.objects.get_or_create(name="시스템관리")
        User.objects.create_superuser(
            username="admin",
            password="admin-password",
            first_name="시스템 관리자",
            department=system_department,
            position="관리자",
        )
        super_created = self.client.post(
            "/api/v1/notices",
            data=json.dumps({"title": "슈퍼어드민 공지", "content": "관리 가능"}),
            content_type="application/json",
            **self.headers(self.login("admin", "admin-password")),
        )
        self.assertEqual(super_created.status_code, 201, super_created.content)
        self.assertEqual(super_created.json()["title"], "슈퍼어드민 공지")

        deleted = self.client.delete(
            f"/api/v1/notices/{notice_id}",
            **self.headers(token),
        )
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(Notice.objects.filter(pk=notice_id).exists())

    def test_designated_admin_migration_updates_matching_account_only(self):
        department, _ = Department.objects.get_or_create(
            name=DESIGNATED_ADMIN_DEPARTMENT
        )
        target = User.objects.create_user(
            username=DESIGNATED_ADMIN_USERNAME,
            password="safe-password-1234",
            first_name=DESIGNATED_ADMIN_NAME,
            department=department,
            position=DESIGNATED_ADMIN_POSITION,
            is_staff=False,
        )
        other = User.objects.create_user(
            username="non-designated-account",
            password="safe-password-1234",
            first_name=DESIGNATED_ADMIN_NAME,
            department=department,
            position=DESIGNATED_ADMIN_POSITION,
            is_staff=False,
        )
        migration = import_module(
            "core.migrations.0006_grant_designated_admin_access"
        )

        migration.grant_designated_admin_access(apps, None)

        target.refresh_from_db()
        other.refresh_from_db()
        self.assertTrue(target.is_staff)
        self.assertFalse(target.is_superuser)
        self.assertFalse(other.is_staff)

    def test_designated_admin_permission_is_restored_on_login(self):
        department, _ = Department.objects.get_or_create(
            name=DESIGNATED_ADMIN_DEPARTMENT
        )
        user = User.objects.create_user(
            username=DESIGNATED_ADMIN_USERNAME,
            password="safe-password-1234",
            first_name=DESIGNATED_ADMIN_NAME,
            department=department,
            position=DESIGNATED_ADMIN_POSITION,
            is_staff=False,
        )

        response = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({
                "id": DESIGNATED_ADMIN_USERNAME,
                "password": "safe-password-1234",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["user"]["isAdmin"])
        user.refresh_from_db()
        self.assertTrue(user.is_staff)

        bootstrap = self.client.get(
            "/api/v1/bootstrap",
            **self.headers(response.json()["token"]),
        )
        self.assertEqual(bootstrap.status_code, 200, bootstrap.content)
        self.assertTrue(bootstrap.json()["currentUser"]["isAdmin"])
        account = next(
            item
            for item in bootstrap.json()["accounts"]
            if item["id"] == DESIGNATED_ADMIN_USERNAME
        )
        self.assertTrue(account["isAdmin"])

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

    def test_frequent_forms_are_counted_per_actual_user_usage(self):
        ApprovalDocument.objects.all().delete()
        manager = User.objects.get(username="edu_manager")
        teacher = User.objects.get(username="edu_teacher")
        business = ApprovalFormTemplate.objects.get(slug="business-draft")
        expense = ApprovalFormTemplate.objects.get(slug="expense-slip")

        def create_document(public_id, drafter, form):
            return ApprovalDocument.objects.create(
                public_id=public_id,
                title=public_id,
                drafter=drafter,
                department_name=drafter.department.name,
                form_template=form,
                form_name=form.name,
            )

        create_document("FREQ-MANAGER-1", manager, business)
        create_document("FREQ-MANAGER-2", manager, business)
        create_document("FREQ-MANAGER-3", manager, expense)
        create_document("FREQ-TEACHER-1", teacher, expense)
        create_document("FREQ-TEACHER-2", teacher, expense)
        create_document("FREQ-TEACHER-3", teacher, expense)

        manager_response = self.client.get(
            "/api/v1/bootstrap",
            **self.headers(self.login("edu_manager")),
        )
        teacher_response = self.client.get(
            "/api/v1/bootstrap",
            **self.headers(self.login("edu_teacher")),
        )

        self.assertEqual(
            [
                (form["id"], form["recentCount"])
                for form in manager_response.json()["frequentForms"]
            ],
            [("business-draft", 2), ("expense-slip", 1)],
        )
        self.assertEqual(
            [
                (form["id"], form["recentCount"])
                for form in teacher_response.json()["frequentForms"]
            ],
            [("expense-slip", 3)],
        )

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

    def test_form_approval_lines_round_trip(self):
        token = self.login()
        response = self.client.patch(
            "/api/v1/approval-forms/business-draft",
            data=json.dumps({
                "approvalLines": [
                    {
                        "id": "standard-line",
                        "name": "기본 결재라인",
                        "userIds": ["edu_manager", "lee_jaeo"],
                    },
                    {
                        "id": "executive-line",
                        "name": "임원 결재라인",
                        "userIds": ["director", "ceo"],
                    },
                ],
            }),
            content_type="application/json",
            **self.headers(token),
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["approvalLines"][1]["name"], "임원 결재라인")

        bootstrap = self.client.get(
            "/api/v1/bootstrap",
            **self.headers(token),
        )
        business = next(
            form
            for form in bootstrap.json()["formTemplates"]
            if form["id"] == "business-draft"
        )
        self.assertEqual(
            business["approvalLines"][0]["userIds"],
            ["edu_manager", "lee_jaeo"],
        )

    def test_document_access_settings_persist_as_one_snapshot(self):
        token = self.login()
        payload = {
            "organizationWideDocumentCategories": ["회계"],
            "documentCategoryViewerIds": {
                "지원": ["edu_teacher"],
                "회계": [],
                "근태": ["lee_jaeo", "edu_teacher"],
            },
        }
        response = self.client.patch(
            "/api/v1/settings",
            data=json.dumps(payload),
            content_type="application/json",
            **self.headers(token),
        )
        self.assertEqual(response.status_code, 200, response.content)

        bootstrap = self.client.get(
            "/api/v1/bootstrap",
            **self.headers(token),
        ).json()["settings"]
        self.assertEqual(
            bootstrap["organizationWideDocumentCategories"],
            ["회계"],
        )
        self.assertEqual(
            bootstrap["documentCategoryViewerIds"],
            payload["documentCategoryViewerIds"],
        )

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
                "hireDate": "2026-08-31",
                "annualLeaveDays": 18,
                "monthlyLeaveDays": 4.5,
                "leaveBalanceAdjustment": -1.5,
            }),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(created_employee.status_code, 201, created_employee.content)
        self.assertNotIn("email", created_employee.json()["user"])
        self.assertEqual(created_employee.json()["user"]["annualLeaveDays"], 18.0)
        self.assertEqual(created_employee.json()["user"]["monthlyLeaveDays"], 4.5)
        self.assertEqual(
            created_employee.json()["user"]["leaveBalanceAdjustment"],
            -1.5,
        )
        original_user_pk = User.objects.get(username="new_member").pk
        setting = PortalSetting.load()
        setting.document_category_viewer_ids = {
            "지원": ["new_member", "edu_teacher"],
        }
        setting.leave_approval_lines = {
            "신규부서": ["new_member", "edu_teacher"],
        }
        setting.save(update_fields=[
            "document_category_viewer_ids",
            "leave_approval_lines",
        ])
        template = ApprovalFormTemplate.objects.first()
        template.viewers = ["new_member"]
        template.approval_lines = [
            {
                "id": "employee-line",
                "name": "직원 결재라인",
                "userIds": ["new_member", "edu_teacher"],
            },
        ]
        template.save(update_fields=["viewers", "approval_lines"])
        document = ApprovalDocument.objects.first()
        document.references = ["new_member"]
        document.save(update_fields=["references"])

        updated_employee = self.client.patch(
            "/api/v1/organization/employees/new_member",
            data=json.dumps({
                "id": "renamed_member",
                "name": "수정직원",
                "annualLeaveDays": 20,
                "monthlyLeaveDays": 6,
                "leaveBalanceAdjustment": 2.5,
            }),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(updated_employee.status_code, 200, updated_employee.content)
        self.assertEqual(updated_employee.json()["user"]["id"], "renamed_member")
        self.assertEqual(updated_employee.json()["user"]["name"], "수정직원")
        self.assertEqual(updated_employee.json()["user"]["annualLeaveDays"], 20.0)
        self.assertEqual(updated_employee.json()["user"]["monthlyLeaveDays"], 6.0)
        self.assertEqual(
            updated_employee.json()["user"]["leaveBalanceAdjustment"],
            2.5,
        )
        renamed_user = User.objects.get(username="renamed_member")
        self.assertEqual(renamed_user.pk, original_user_pk)
        self.assertFalse(User.objects.filter(username="new_member").exists())
        setting.refresh_from_db()
        template.refresh_from_db()
        document.refresh_from_db()
        self.assertEqual(
            setting.document_category_viewer_ids["지원"],
            ["renamed_member", "edu_teacher"],
        )
        self.assertEqual(
            setting.leave_approval_lines["신규부서"],
            ["renamed_member", "edu_teacher"],
        )
        self.assertEqual(template.viewers, ["renamed_member"])
        self.assertEqual(
            template.approval_lines[0]["userIds"],
            ["renamed_member", "edu_teacher"],
        )
        self.assertEqual(document.references, ["renamed_member"])

        duplicate_id = self.client.patch(
            "/api/v1/organization/employees/renamed_member",
            data=json.dumps({"id": "edu_teacher"}),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(duplicate_id.status_code, 400, duplicate_id.content)
        self.assertEqual(
            duplicate_id.json()["error"]["code"],
            "username_conflict",
        )

        nonempty_delete = self.client.delete(
            f"/api/v1/organization/departments/{department_id}", **headers
        )
        self.assertEqual(nonempty_delete.status_code, 409)

        deleted_employee = self.client.delete(
            "/api/v1/organization/employees/renamed_member", **headers
        )
        self.assertEqual(deleted_employee.status_code, 204)
        self.assertFalse(User.objects.get(username="renamed_member").is_active)

        deleted_department = self.client.delete(
            f"/api/v1/organization/departments/{department_id}", **headers
        )
        self.assertEqual(deleted_department.status_code, 204)
        self.assertFalse(Department.objects.filter(pk=department_id).exists())

    def test_department_order_is_saved_and_returned_by_bootstrap(self):
        token = self.login()
        headers = self.headers(token)
        denied = self.client.patch(
            "/api/v1/organization/departments/reorder",
            data=json.dumps({"departments": []}),
            content_type="application/json",
            **self.headers(self.login("edu_teacher")),
        )
        self.assertEqual(denied.status_code, 403)
        current = self.client.get(
            "/api/v1/organization/departments",
            **headers,
        ).json()["departments"]
        reordered = [item["name"] for item in reversed(current)]

        response = self.client.patch(
            "/api/v1/organization/departments/reorder",
            data=json.dumps({"departments": reordered}),
            content_type="application/json",
            **headers,
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["departments"], reordered)
        bootstrap = self.client.get(
            "/api/v1/bootstrap",
            **headers,
        ).json()
        self.assertEqual(bootstrap["departments"], reordered)

    def test_department_order_migration_uses_requested_default_order(self):
        requested = ["대표이사", "기술부", "연구소", "관리부", "공무", "경리부"]
        for name in reversed(requested):
            Department.objects.get_or_create(name=name)
        migration = import_module("core.migrations.0005_department_sort_order")

        migration.initialize_department_sort_order(apps, None)

        ordered = list(
            Department.objects.order_by("sort_order", "name").values_list(
                "name",
                flat=True,
            )
        )
        self.assertEqual(ordered[:6], requested)

    def test_super_admin_is_hidden_from_employee_and_organization_data(self):
        department = Department.objects.create(name="시스템관리")
        User.objects.create_superuser(
            username="admin",
            password="admin0630",
            first_name="슈퍼어드민",
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
                "leaveApprovalLines": {"교육관리팀": ["edu_manager", "ceo"]},
            }),
            content_type="application/json",
            **self.headers(token),
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(updated.json()["portalName"], "연동 테스트 포털")
        self.assertEqual(
            updated.json()["leaveApprovalLines"],
            {"교육관리팀": ["edu_manager", "ceo"]},
        )
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
        admin_token = self.login("ceo")
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

    def test_department_leave_approval_line_is_applied_in_order(self):
        teacher = User.objects.select_related("department").get(username="edu_teacher")
        setting = PortalSetting.load()
        setting.leave_approval_lines = {
            teacher.department.name: ["edu_manager", "ceo"],
        }
        setting.save(update_fields=["leave_approval_lines", "updated_at"])

        response = self.client.post(
            "/api/v1/leave/requests",
            data=json.dumps({
                "type": "연차",
                "startDate": "2026-09-04",
                "endDate": "2026-09-04",
                "days": 1,
                "reason": "부서별 결재 테스트",
            }),
            content_type="application/json",
            **self.headers(self.login("edu_teacher")),
        )
        self.assertEqual(response.status_code, 201, response.content)
        leave_id = response.json()["id"]
        self.assertEqual(
            [step["userId"] for step in response.json()["approvalLine"]],
            ["edu_manager", "ceo"],
        )

        early_final = self.client.post(
            f"/api/v1/leave/requests/{leave_id}/approve",
            data="{}",
            content_type="application/json",
            **self.headers(self.login("ceo")),
        )
        self.assertEqual(early_final.status_code, 403, early_final.content)

        first = self.client.post(
            f"/api/v1/leave/requests/{leave_id}/approve",
            data="{}",
            content_type="application/json",
            **self.headers(self.login("edu_manager")),
        )
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json()["status"], "승인대기")
        self.assertEqual(
            [step["status"] for step in first.json()["approvalLine"]],
            ["완료", "진행중"],
        )

        final = self.client.post(
            f"/api/v1/leave/requests/{leave_id}/approve",
            data="{}",
            content_type="application/json",
            **self.headers(self.login("ceo")),
        )
        self.assertEqual(final.status_code, 200, final.content)
        self.assertEqual(final.json()["status"], "승인")
        self.assertEqual(
            [step["status"] for step in final.json()["approvalLine"]],
            ["완료", "완료"],
        )

    def test_leave_summary_uses_completed_service_years(self):
        teacher = User.objects.get(username="edu_teacher")
        teacher.hire_date = date(date.today().year - 5, 1, 1)
        teacher.save(update_fields=["hire_date"])
        setting = PortalSetting.load()
        setting.annual_leave_by_year = {"1": 15, "5": 17, "6": 18, "10": 20}
        setting.save(update_fields=["annual_leave_by_year", "updated_at"])

        response = self.client.get(
            "/api/v1/leave/summary",
            **self.headers(self.login("edu_teacher")),
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["serviceYear"], 5)
        self.assertEqual(response.json()["entitlement"], 17)

    def test_leave_summary_resets_usage_on_january_first(self):
        teacher = User.objects.get(username="edu_teacher")
        teacher.leave_requests.all().delete()
        today = date.today()
        teacher.hire_date = date(today.year - 5, 1, 1)
        teacher.save(update_fields=["hire_date"])
        setting = PortalSetting.load()
        setting.annual_leave_by_year = {"1": 15, "5": 17}
        setting.save(update_fields=["annual_leave_by_year", "updated_at"])
        LeaveRequest.objects.create(
            public_id="LEAVE-LAST-YEAR",
            user=teacher,
            leave_type="연차",
            start_date=date(today.year - 1, 12, 31),
            end_date=date(today.year - 1, 12, 31),
            days=2,
            status=LeaveRequest.Status.APPROVED,
        )
        LeaveRequest.objects.create(
            public_id="LEAVE-THIS-YEAR",
            user=teacher,
            leave_type="연차",
            start_date=date(today.year, 1, 1),
            end_date=date(today.year, 1, 1),
            days=1,
            status=LeaveRequest.Status.PENDING,
        )

        response = self.client.get(
            "/api/v1/leave/summary",
            **self.headers(self.login("edu_teacher")),
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["used"], 0)
        self.assertEqual(response.json()["pending"], 1)
        self.assertEqual(response.json()["remaining"], 16)

    def test_leave_summary_uses_monthly_leave_before_first_anniversary(self):
        teacher = User.objects.get(username="edu_teacher")
        teacher.leave_requests.all().delete()
        today = date.today()
        teacher.hire_date = date(today.year, 1, 1)
        teacher.save(update_fields=["hire_date"])
        setting = PortalSetting.load()
        setting.monthly_leave_per_month = 2
        setting.save(update_fields=["monthly_leave_per_month", "updated_at"])

        response = self.client.get(
            "/api/v1/leave/summary",
            **self.headers(self.login("edu_teacher")),
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["serviceYear"], 1)
        self.assertEqual(response.json()["entitlement"], (today.month - 1) * 2)
        self.assertEqual(response.json()["remaining"], (today.month - 1) * 2)

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
