
# 서버 설정

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
PDAM_SALES_QUERY=SELECT d.id AS source_id, COALESCE(NULLIF(c.location, ''), NULLIF(g.groupName, ''), NULLIF(c.name, ''), CONCAT('현장-', d.id)) AS project_name, COALESCE(g.groupName, '') AS contractor, COALESCE(c.name, '') AS partner, COALESCE(NULLIF(d.machineNumber, ''), d.lavelNo) AS elevator, d.startDate AS start_date, d.endDate AS end_date, CASE WHEN d.isDel = 1 OR d.conduct = 2 THEN '종료' ELSE '진행' END AS status, CASE WHEN COALESCE(c.fcIdx, 0) <> 0 THEN '가맹' ELSE '본사' END AS category, GREATEST(COALESCE(d.endDate, '1970-01-01'), COALESCE(g.lastModifiedDate, '1970-01-01')) AS updated_at FROM TB_DEVICE d LEFT JOIN TB_CONSTRUCTION c ON c.id = d.constructionIdx LEFT JOIN TB_GROUP g ON g.idx = c.groupIdx
```

ERP는 `source_id`, `project_name`, `contractor`, `partner`, `elevator`,
`start_date`, `end_date`, `status`, `category`를 PDAM에서 갱신하고, 청구·계산서·입금·공급가·회차·상태·비고는 ERP DB에 별도 저장합니다. PDAM 상태가 `종료`면 ERP 상태는 자동으로 `종료`가 되며 분류는 비워집니다.

모바일 푸시 알림 발송에는 `firebase-admin` 패키지와 서버 전용 Firebase 서비스 계정 JSON 파일이 필요합니다. 파일은 저장소 밖에 보관하고 `FIREBASE_SERVICE_ACCOUNT` 환경변수에 절대 경로를 지정합니다. 설정 전에도 결재와 휴가 처리는 정상 작동하며, 푸시 전송만 생략됩니다.
