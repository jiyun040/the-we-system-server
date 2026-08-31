# the-we-system-server

`the-we-system` Flutter 클라이언트를 위한 Django REST 서버입니다. 로컬 개발은 SQLite로 바로 실행되며, 별도 REST 프레임워크 없이 Django 자체 기능만 사용합니다.

## 제공 기능

- Bearer 토큰 기반 로그인·로그아웃·내 정보 조회
- 부서와 직원 조직도, Django 관리자 화면
- 결재 양식 조회·관리
- 기안 임시 저장, 수정, 상신, 승인, 반려, 상신 취소
- 결재선, 변경 이력, 첨부파일(Base64), 문서 접근 권한
- 휴가 신청, 관리자 직권 등록, 승인·반려·취소, 연차 요약
- 로컬 Flutter Web 연동을 위한 CORS와 기존 API 경로 호환

## 로컬 실행

Python 3.10 이상을 권장합니다. Django 6을 사용하려면 Python 3.12 이상이 필요하며, Python 3.10~3.11에서는 requirements 범위에 따라 Django 5.2가 설치됩니다.

```bash
cd /Users/jeongjiyun/Documents/the_we/the-we-system-server
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

정상 실행 여부는 `http://127.0.0.1:8000/api/v1/health`에서 확인할 수 있습니다. Django 관리 화면은 `http://127.0.0.1:8000/admin/`입니다.

실제 서비스와 운영 서버에서는 `seed_demo`를 실행하지 않습니다. 필요한 계정과 조직 정보는 관리자 기능 또는 명시적인 운영 계정 생성 절차로만 등록합니다.

## Flutter 로컬 실행

현재 Flutter 프로젝트 위치가 `/Users/jeongjiyun/Documents/the_we/the-we-system`이라면 다음처럼 실행할 수 있습니다.

```bash
cd /Users/jeongjiyun/Documents/the_we/the-we-system
flutter run -d chrome --web-port=8080 \
  --dart-define=API_BASE_URL=http://127.0.0.1:8000/api/v1
```

`API_BASE_URL`을 지정하면 Flutter 앱은 서버 모드로 동작합니다. 로그인 토큰은 플랫폼 보안 저장소에 보관되고 Dio 인터셉터가 모든 요청에 Bearer 토큰을 추가합니다. 앱을 새로고침해도 `/bootstrap` API를 통해 사용자, 조직, 양식, 결재 문서, 휴가와 포털 설정이 복원됩니다.

`API_BASE_URL`을 지정하지 않으면 기존 Flutter 위젯 테스트와 UI 개발을 위한 목업 모드로 동작합니다.

Android 에뮬레이터에서는 `127.0.0.1` 대신 다음 주소를 사용합니다.

```bash
flutter run -d emulator-5554 \
  --dart-define=API_BASE_URL=http://10.0.2.2:8000/api/v1
```

## 인증 예시

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"id":"edu_manager","password":"1234"}'
```

응답의 `token`을 이후 요청에 사용합니다.

회원가입은 서버에 미리 등록된 구성원의 이름·부서·직책이 모두 일치할 때만 허용됩니다. 가입 응답에서 로그인 토큰을 발급하지 않으므로, 완료 후 로그인이 필요합니다.

```bash
curl http://127.0.0.1:8000/api/v1/approvals/dashboard \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

전체 엔드포인트와 요청 형식은 [API 문서](docs/api.md)를 참고하세요.

## 테스트

```bash
python manage.py check
python manage.py test
```

## 환경변수

- `DJANGO_DEBUG`: 로컬 디버그 모드. 기본값 `true`
- `DJANGO_SECRET_KEY`: 운영에서는 반드시 긴 임의 값으로 변경
- `DJANGO_ALLOWED_HOSTS`: 쉼표로 구분한 허용 호스트
- `CORS_ALLOWED_ORIGINS`: 쉼표로 구분한 Flutter Web 출처
- `CSRF_TRUSTED_ORIGINS`: 쉼표로 구분한 신뢰할 수 있는 HTTPS 출처
- `DEV_ALLOW_ANONYMOUS`: 기존 Flutter 목업 연동을 위한 개발 전용 익명 접근
- `DEV_DEFAULT_USERNAME`: 익명 접근 시 사용할 로컬 계정
- `TOKEN_TTL_HOURS`: 로그인 토큰 유효 시간
- `DATABASE_PATH`: 선택 사항. SQLite 파일 위치
- `DB_ENGINE`: `sqlite` 또는 `mysql`
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`: MySQL 연결 정보
- `DB_CONN_MAX_AGE`: MySQL 연결 재사용 시간(초)
- `DB_SSL_CA`: RDS TLS 인증서 번들 경로
- `DATA_UPLOAD_MAX_MEMORY_SIZE`: Base64 첨부파일 요청 최대 크기

운영 환경에서는 `DJANGO_DEBUG=false`, `DEV_ALLOW_ANONYMOUS=false`로 설정해야 합니다.
