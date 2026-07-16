# AKFES v2 Server

AKFES v2의 FastAPI 서버 기본 구조입니다. 기존 `AKFES-Server`의 라이선스, 세션, 장치 바인딩, 챌린지, 파일 암호화 로직은 검증하면서 단계적으로 이 디렉터리로 이전합니다.

## 현재 제공 기능

- `GET /api/v2/health`: v2 상태 확인 API
- `GET /health`: 기존 클라이언트 호환용 상태 확인 API
- 환경변수 기반 호스트, 포트, CORS, Trusted Host, 업로드 한도 설정
- 개발 환경에서만 기본 활성화되는 Swagger 문서
- API 응답의 캐시 방지, Referrer 제한, MIME 스니핑 방지, 요청 ID 헤더
- pytest 상태 확인 테스트

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

## 검사

```powershell
python -m pytest
python -m ruff check .
```

## 환경변수

`.env.example`을 참고해 로컬 `.env`를 만듭니다. 실제 운영 비밀키나 라이선스 서명 키는 저장소에 커밋하지 않습니다.

운영 환경에서는 최소한 다음 값을 명시해야 합니다.

- `AKFES_ENVIRONMENT=production`
- `AKFES_DOCS_ENABLED=false`
- `AKFES_CORS_ORIGINS`: 실제 클라이언트 Origin만 지정
- `AKFES_ALLOWED_HOSTS`: 실제 API 도메인만 지정
- `AKFES_MAX_UPLOAD_BYTES`: 서버가 허용할 최대 파일 크기

## 다음 이전 단계

1. 기존 라이선스 발급·검증 저장소를 분리된 서비스로 이전
2. 만료 시간이 있는 세션 토큰과 장치 바인딩 이전
3. 일회용 챌린지와 요청 서명 검증 이전
4. 스트리밍 방식 AES-256-GCM 파일 처리 API 구현
5. Tauri 클라이언트의 라이선스·파일 작업 화면 연결
