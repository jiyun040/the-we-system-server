
# 서버 설정

## 운영 도메인 및 클라이언트 자동 배포 전제 조건

현재 서버 배포 설정은 `the-we-erp.cloud`와 `www.the-we-erp.cloud`를
Nginx의 `server_name`으로 사용하고, `/api/`만 Django로 전달하도록 되어
있습니다. 운영 적용 전 아래 항목을 확인합니다.

1. Route 53(또는 사용 중인 DNS)에 `the-we-erp.cloud`와 `www`의 A/AAAA 레코드가
   실제 EC2 주소를 가리키는지 확인합니다.
2. 80/443 보안 그룹과 Nginx 인증서 설정을 적용하고, `DJANGO_ALLOWED_HOSTS`,
   `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS`에 실제 HTTPS 도메인만 둡니다.
3. 클라이언트 저장소에 Flutter `pubspec.yaml`, `lib/`, `web/`가 존재해야 합니다.
   현재 이 저장소에는 해당 클라이언트 소스와 GitHub Actions 워크플로가 없습니다.
4. 클라이언트 저장소의 Actions에 Flutter web 빌드 후 서버의
   `/var/www/the-we-erp`로 업로드하는 배포 작업을 추가하고, 다음 GitHub Secrets를
   등록합니다: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`.
5. 서버에서는 배포 계정의 공개키를 `authorized_keys`에 등록하고,
   `/var/www/the-we-erp`에 해당 계정의 쓰기 권한을 부여합니다.

클라이언트 소스가 이 저장소로 이동되거나 별도 저장소 경로가 확정되면 그 위치에
빌드·업로드 워크플로를 추가할 수 있습니다.

변경된 모델을 적용하려면 배포 시 `python3 manage.py migrate`를 실행합니다.

## PDAM DB 연동

매출관리대장은 PDAM HTTP API를 호출하지 않고 별도 MySQL 연결을 사용합니다. 운영
환경의 `.env`에 PDAM 접속 정보와 읽기 전용 조회문을 설정합니다. 조회문은 반드시
`SELECT` 문이어야 하며 아래 별칭을 반환해야 합니다.

```env
PDAM_DB_NAME=pdam
PDAM_DB_USER=readonly_user
PDAM_DB_PASSWORD=...
PDAM_DB_HOST=...
PDAM_DB_PORT=3306
PDAM_SALES_QUERY=SELECT d.id AS source_id, COALESCE(NULLIF(c.location, ''), NULLIF(g.groupName, ''), NULLIF(c.name, ''), CONCAT('현장-', d.id)) AS project_name, COALESCE(g.groupName, '') AS contractor, COALESCE(c.name, '') AS partner, COALESCE(NULLIF(d.machineNumber, ''), d.lavelNo) AS elevator, d.startDate AS start_date, d.createdDate AS record_date, d.endDate AS end_date, CASE WHEN d.conduct = 1 THEN '종료' ELSE '진행' END AS status, CASE WHEN d.conduct = 2 THEN '가맹' WHEN d.conduct = 0 THEN '본사' ELSE '' END AS category, COALESCE(d.isDel, 0) AS is_deleted FROM TB_DEVICE d LEFT JOIN TB_CONSTRUCTION c ON c.id = d.constructionIdx LEFT JOIN TB_GROUP g ON g.idx = c.groupIdx
```

ERP는 `source_id`, `project_name`, `contractor`, `partner`, `elevator`,
`start_date`, `end_date`, `status`, `category`를 PDAM에서 갱신하고, 청구·계산서·입금·공급가·회차·상태·비고는 ERP DB에 별도 저장합니다. PDAM 상태가 `종료`면 ERP 상태는 자동으로 `종료`가 됩니다. 이전에 확인된 호기 분류는 유지하고, 종료 상태로 처음 들어온 호기는 분류를 비웁니다.

모바일 푸시 알림 발송에는 `firebase-admin` 패키지와 서버 전용 Firebase 서비스 계정 JSON 파일이 필요합니다. 파일은 저장소 밖에 보관하고 `FIREBASE_SERVICE_ACCOUNT` 환경변수에 절대 경로를 지정합니다. 설정 전에도 결재와 휴가 처리는 정상 작동하며, 푸시 전송만 생략됩니다.

### 매출관리대장 월별 청구 적용 (2026-10)

- PDAM `TB_DEVICE.conduct`: `0=본사 사용`, `1=종료`, `2=가맹 사용`.
  현장의 `TB_CONSTRUCTION.fcIdx`는 호기별 매출 분류에 사용하지 않습니다.
- 기존 예제의 `fcIdx` 분류 SQL이 환경변수에 남아 있어도 서버에서 수정된 기본 SQL로 전환합니다.
  사용자 정의 SQL은 `status`, `category`, `is_deleted`를 같은 의미로 반환해야 합니다.
- 삭제된 호기는 원본 청구를 삭제하지 않고 조회에서 제외합니다.
- 조회 월과 계약기간이 겹치는 호기를 포함합니다. 화면·엑셀·내역서는 해당 월의 사용기간을 사용하며,
  미종료 호기의 사용 종료일은 월말, 종료 호기는 실제 종료일과 월말 중 빠른 날짜입니다.
- 원본 계약기간과 월별 청구값은 별도로 저장됩니다. PATCH의 `month`는 `YYYY-MM`입니다.
  새 월은 청구일·계산서·입금일·금액을 이전 월에서 복사하지 않습니다.
- 기존 단일 청구 데이터는 0023 마이그레이션에서 청구일의 월로 보존합니다.
  청구일이 계약기간 밖이면 가장 가까운 계약 월로 배정하며 원본 데이터도 유지합니다.
  이전 시스템이 이미 덮어쓴 과거 월별 청구나 과거 가맹 변경 이력은 자동 복원할 수 없습니다.
- 현재 PDAM 스냅샷과 과거 수기 엑셀은 시점과 현장명이 다르므로, 과거 엑셀의 건수를 강제로 맞추지 않습니다.

운영 적용 순서:

1. ERP 데이터베이스 백업 후 `python manage.py migrate` 실행 (0023 적용).
2. 서버 코드 배포·재시작.
3. `python manage.py shell -c "from core.views_sales import sync_pdam_sales_records; sync_pdam_sales_records()"`로 기존 오분류 재동기화.
4. 프런트엔드 배포 후 매출관리대장의 월을 다시 조회하고 엑셀 재다운로드.

PDAM에서는 SELECT만 수행하며 ERP의 동기화 데이터 및 월별 청구만 저장합니다.
