# the-we-system API v1

기본 URL은 `http://127.0.0.1:8000/api/v1`입니다. JSON 요청에는 `Content-Type: application/json`, 인증 요청에는 `Authorization: Bearer <token>`을 사용합니다. 모든 경로는 끝 슬래시 없이 호출합니다.

오류 응답 형식:

```json
{
  "error": {
    "code": "invalid_state",
    "message": "작성 중인 문서만 상신할 수 있습니다.",
    "fields": {}
  }
}
```

## 상태와 인증

| Method | Path | 설명 |
|---|---|---|
| GET | `/health` | 서버 상태 |
| POST | `/auth/register` | 회원가입 |
| POST | `/auth/login` | 토큰 발급 |
| POST | `/auth/logout` | 현재 토큰 폐기 |
| GET | `/auth/me` | 로그인 사용자 조회 |

로그인 요청:

```json
{"id": "edu_manager", "password": "1234"}
```

회원가입 요청:

```json
{
  "id": "new_user",
  "password": "safe-password",
  "name": "홍길동",
  "department": "개발팀",
  "position": "대리",
  "email": "hong@example.com"
}
```

## 조직과 설정

| Method | Path | 권한 | 설명 |
|---|---|---|---|
| GET | `/organization/departments` | 사용자 | 부서와 구성원 |
| POST | `/organization/departments` | 관리자 | 부서 생성 |
| GET | `/organization/employees` | 사용자 | 직원 목록 |
| POST | `/organization/employees` | 관리자 | 직원 생성 |
| GET | `/settings` | 사용자 | 포털·연차·보안 설정 |
| PATCH | `/settings` | 관리자 | 설정 변경 |

## 결재 양식

| Method | Path | 권한 | 설명 |
|---|---|---|---|
| GET | `/approval-forms` | 사용자 | 활성 양식 목록 |
| POST | `/approval-forms` | 관리자 | 양식 생성 |
| GET | `/approval-forms/{formId}` | 사용자 | 양식 상세 |
| PATCH | `/approval-forms/{formId}` | 관리자 | 양식 수정 |
| DELETE | `/approval-forms/{formId}` | 관리자 | 양식 삭제 |

## 결재 문서

| Method | Path | 설명 |
|---|---|---|
| GET | `/approvals/dashboard` | 결재 대시보드 |
| GET | `/approvals/documents?status=작성중` | 접근 가능한 문서 목록 |
| POST | `/approvals/documents` | 임시 문서 생성 |
| GET | `/approvals/documents/{documentId}` | 문서 상세 |
| PATCH | `/approvals/documents/{documentId}` | 수정 가능한 문서 변경 |
| DELETE | `/approvals/documents/{documentId}` | 임시 문서 삭제 |
| POST | `/approvals/documents/{documentId}/submit` | 상신 |
| POST | `/approvals/{documentId}/approve` | 승인 |
| POST | `/approvals/{documentId}/reject` | 반려 |
| POST | `/approvals/{documentId}/cancel` | 상신 취소 |

문서 생성 최소 요청:

```json
{
  "formId": "business-draft",
  "title": "신규 업무 기안",
  "content": "승인을 요청드립니다.",
  "urgent": false,
  "departmentVisible": true,
  "linkedDocuments": [],
  "attachments": []
}
```

승인 또는 반려 요청:

```json
{"opinion": "내용 확인했습니다."}
```

첨부파일은 `{name, mimeType, base64Data}` 구조이며 개별 10MB 이하로 제한됩니다.

## 휴가

| Method | Path | 권한 | 설명 |
|---|---|---|---|
| GET | `/leave/requests` | 사용자 | 본인 신청 목록. 관리자는 전체 목록 |
| POST | `/leave/requests` | 사용자 | 휴가 신청 |
| GET | `/leave/summary` | 사용자 | 연차 부여·사용·대기·잔여 요약 |
| POST | `/leave/requests/{leaveId}/approve` | 관리자 | 승인 |
| POST | `/leave/requests/{leaveId}/reject` | 관리자 | 반려 |
| POST | `/leave/requests/{leaveId}/cancel` | 신청자/관리자 | 신청 취소 |
| POST | `/leave/requests/{leaveId}/acknowledge` | 신청자 | 승인 확인 처리 |

휴가 신청 요청:

```json
{
  "type": "연차",
  "startDate": "2026-09-01",
  "endDate": "2026-09-01",
  "days": 1,
  "reason": "개인 일정"
}
```

관리자는 동일한 요청에 `userId`와 `directEntry: true`를 넣어 직원 휴가를 직권 등록할 수 있습니다.

## 현재 Flutter 호환 경로

기존 앱이 이미 사용하는 다음 절대 경로도 제공합니다.

- `GET /approvals/dashboard`
- `POST /approvals/{documentId}/approve`

이 호환 경로의 익명 접근은 `.env`의 `DEV_ALLOW_ANONYMOUS=true`이면서 디버그 모드일 때만 허용됩니다.
