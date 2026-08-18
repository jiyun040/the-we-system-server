import json

from django.core.management import call_command
from django.test import TestCase, override_settings

from core.models import ApprovalDocument, LeaveRequest


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

    @override_settings(DEV_ALLOW_ANONYMOUS=False)
    def test_protected_endpoint_rejects_anonymous_requests(self):
        response = self.client.get("/api/v1/organization/employees")
        self.assertEqual(response.status_code, 401)
