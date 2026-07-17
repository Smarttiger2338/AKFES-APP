# AKFES v2 Server

AKFES v2의 FastAPI 서버입니다. 기존 `AKFES-Server`의 기능을 검증하면서 단계적으로 이 디렉터리로 이전합니다.

## 현재 제공 기능

- `GET /api/v2/health`: v2 상태 확인 API
- `GET /health`: 기존 클라이언트 호환용 상태 확인 API
- `POST /api/v2/admin/licenses`: 관리자 토큰으로 라이선스 발급
- `POST /api/v2/auth/login`: 라이선스 검증 및 세션 발급
- `GET /api/v2/auth/session`: Bearer 세션 검증
- SQLite 기반 라이선스·세션 저장
- HMAC-SHA256 기반 키·토큰 다이제스트 저장
- 선택적 장치 ID 세션 바인딩
- 환경변수 기반 호스트, 포트, CORS, Trusted Host, 업로드 한도 설정
- 개발 환경에서만 기본 활성화되는 Swagger 문서
- 캐시 방지, Referrer 제한, MIME 스니핑 방지, 요청 ID 응답 헤더
- pytest 상태 확인 및 인증 흐름 테스트

라이선스 키와 세션 토큰 원문은 데이터베이스에 저장하지 않습니다. 원문은 발급 또는 로그인 응답에서 한 번만 클라이언트에 전달됩니다.

## Windows 개발 환경 실행

```powershell
cd server
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

상태 확인:

```text
http://127.0.0.1:8000/api/v2/health
```

개발 문서:

```text
http://127.0.0.1:8000/docs
```

## 라이선스 발급 예시

PowerShell에서 관리자 토큰을 헤더로 전달합니다.

```powershell
$headers = @{
  "X-AKFES-Admin-Token" = $env:AKFES_ADMIN_TOKEN
}

$body = @{
  duration_seconds = 2592000
  label = "development-device"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v2/admin/licenses" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $body
```

## 로그인 예시

```powershell
$body = @{
  license_key = "AKFES-XXXXX-XXXXX-XXXXX-XXXXX"
  device_id = "desktop-device-id"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/api/v2/auth/login" `
  -ContentType "application/json" `
  -Body $body
```

로그인 응답의 `session_token`은 이후 요청에서 `Authorization: Bearer ...` 헤더로 사용합니다. 장치 ID가 설정된 세션은 `X-AKFES-Device-ID` 헤더도 동일하게 전달해야 합니다.

## 검사

```powershell
python -m pytest
python -m ruff check .
```

현재 테스트 범위:

- 상태 확인 API와 보안 응답 헤더
- API 문서 비활성화 설정
- 관리자 토큰 없는 라이선스 발급 거부
- 라이선스 발급 → 로그인 → 세션 확인
- 다른 장치 ID로 세션 재사용 거부
- 잘못된 라이선스 키 거부
- DB에 라이선스 원문이 저장되지 않는지 확인

## 환경변수

`.env.example`을 참고해 로컬 `.env`를 만듭니다. 실제 운영 비밀키나 관리자 토큰은 저장소에 커밋하지 않습니다.

운영 환경에서는 최소한 다음 값을 명시해야 합니다.

- `AKFES_ENVIRONMENT=production`
- `AKFES_DOCS_ENABLED=false`
- `AKFES_LICENSE_HMAC_SECRET`: 32자 이상의 무작위 비밀값
- `AKFES_ADMIN_TOKEN`: 32자 이상의 별도 무작위 관리자 토큰
- `AKFES_DATABASE_PATH`: 라이선스 DB 경로
- `AKFES_SESSION_TTL_SECONDS`: 세션 만료 시간
- `AKFES_CORS_ORIGINS`: 실제 클라이언트 Origin만 지정
- `AKFES_ALLOWED_HOSTS`: 실제 API 도메인만 지정
- `AKFES_MAX_UPLOAD_BYTES`: 서버가 허용할 최대 파일 크기

운영 환경에서 개발용 기본 비밀값이 남아 있으면 서버 시작이 거부됩니다.

## 다음 이전 단계

1. 라이선스 취소·목록 관리와 관리자 감사 로그
2. 일회용 챌린지와 요청 서명 검증
3. 장치 바인딩 정책 강화
4. 스트리밍 방식 AES-256-GCM 파일 처리 API 구현
5. Tauri 클라이언트의 라이선스·파일 작업 화면 연결
