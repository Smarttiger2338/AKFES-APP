# AKFES v2

Arduino 키패드와 Tauri 데스크톱 앱을 이용해 파일을 AES-256-GCM으로 암호화·복호화하는 프로젝트입니다.

## 구성

```text
AKFES-APP/
├─ apps/desktop/             Tauri v2 + Rust + React + TypeScript
├─ server/                   FastAPI 인증·암호화 서버
├─ firmware/arduino/         Arduino UNO 펌웨어
├─ scripts/                  Windows 실행 스크립트
├─ START_AKFES.bat           개발 환경 원클릭 실행
└─ .github/workflows/        CI와 Windows 설치 파일 빌드
```

기존 Electron 클라이언트는 제거했으며 새 코드는 `apps/desktop`과 `server`만 사용합니다.

## 원클릭 실행

Windows에서 저장소를 내려받은 뒤 루트의 다음 파일을 실행합니다.

```text
START_AKFES.bat
```

스크립트가 자동으로 다음 작업을 수행합니다.

1. Python·Node.js·Rust 설치 여부 확인
2. `server/.venv` 생성
3. FastAPI와 데스크톱 의존성 설치
4. FastAPI 서버 시작 및 `/health` 확인
5. Tauri 데스크톱 실행

처음 실행에는 의존성 설치가 필요합니다. Python 3.11 이상, Node.js LTS, Rust와 Tauri Windows 빌드 도구가 설치되어 있어야 합니다.

## Windows 설치 실행 파일

GitHub Actions의 **Build AKFES Windows Installer** 워크플로가 NSIS 설치 파일을 생성합니다.

결과물 이름:

```text
AKFES-Windows-Installer
```

워크플로 아티팩트 안의 `.exe` 파일을 실행하면 현재 사용자 계정에 AKFES 데스크톱 앱이 설치됩니다. 이 설치 파일은 데스크톱 앱용이며 FastAPI 서버는 별도로 실행되어야 합니다. 완전한 단일 실행 파일 배포는 서버 사이드카 패키징 단계에서 진행합니다.

## 보안 흐름

- 라이선스·만료·취소 검증
- 첫 로그인 장치 바인딩
- 만료 시간이 있는 세션
- 일회용 챌린지
- HTTP 경로·본문 해시·장치 ID 기반 HMAC-SHA256 요청 서명
- 명시적 로그아웃과 미사용 챌린지 폐기
- PBKDF2-HMAC-SHA256 200,000회 기반 AES-256-GCM
- 암호문 변조와 잘못된 비밀번호 감지

## 파일 전송

데스크톱은 다음 바이너리 API를 사용합니다.

```text
POST /api/v2/files/encrypt-binary
POST /api/v2/files/decrypt-binary
```

파일은 `application/octet-stream`으로 전송되어 JSON Base64 방식의 약 33% 크기 증가와 문자열 복사 비용을 제거합니다. 기존 JSON API는 호환성을 위해 서버에 남아 있습니다.

## 개발 실행

```powershell
npm install
npm run desktop:dev
```

서버만 실행:

```powershell
cd server
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 검사

```powershell
cd server
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest

cd ..
npm --workspace apps/desktop run build
cd apps/desktop/src-tauri
cargo check
```

GitHub Actions에서는 FastAPI Ruff·pytest, TypeScript·Vite 빌드, Rust `cargo check`를 독립적으로 검사합니다.

## Arduino

```text
펌웨어: firmware/arduino/project.ino
키패드: D2~D9
초록 LED: D10
빨강 LED: D11
통신 속도: 9600 baud
```

## 남은 핵심 작업

- FastAPI 서버의 Windows 사이드카 패키징
- 파일 전체 메모리 적재를 없애는 청크 기반 AKFES v3 포맷
- 실제 앱 아이콘과 코드 서명
- Windows·Arduino·서버 통합 테스트

세부 진행 상황은 [`V2_MIGRATION.md`](V2_MIGRATION.md), 개선 계획은 [`IMPROVEMENTS.md`](IMPROVEMENTS.md)를 확인하세요.
