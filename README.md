
# 서버 설정

변경된 모델을 적용하려면 배포 시 `python3 manage.py migrate`를 실행합니다.

모바일 푸시 알림 발송에는 `firebase-admin` 패키지와 서버 전용 Firebase 서비스 계정 JSON 파일이 필요합니다. 파일은 저장소 밖에 보관하고 `FIREBASE_SERVICE_ACCOUNT` 환경변수에 절대 경로를 지정합니다. 설정 전에도 결재와 휴가 처리는 정상 작동하며, 푸시 전송만 생략됩니다.
