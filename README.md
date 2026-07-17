# AKFES v2

Arduino 키패드와 Tauri 데스크톱 앱을 이용해 파일을 AES-256-GCM으로 암호화·복호화하는 프로젝트입니다.

## 구성

```text
AKFES-APP/
├─ apps/desktop/             Tauri v2 + Rust + React + TypeScript
├─ server/                   FastAPI 인증·암호화 서버와 사이드카 진입점
├─ firmware/arduino/         Arduino UNO 펌웨어
├─ scripts/                  Windows 개발 실행 스크립트
├─ START_AKFES.bat           개발 환경 원클릭 실행
└─ .github/workflows/        CI와 Windows 설치 파일 빌드
```

기존 Electron 클라이언트는 제거했으며 새 코드는 `apps/desktop`과 `server`만 사용합니다.

## 설치형 원클릭 실행

GitHub Actions의 **Build AKFES Windows Installer** 워크플로가 FastAPI 서버를 포함한 NSIS 설치 파일을 생성합니다.

```text
AKFES-Windows-Installer
```

설치 후 AKFES 앱만 실행하면 다음 흐름이 자동으로 진행됩니다.

1. 포함된 `akfes-server.exe` 실행
2. `127.0.0.1:8000`에서 FastAPI 서버 시작
3. Tauri 데스크톱 화면 실행
4. 앱 종료 시 서버 프로세스도 종료

서버 비밀값과 SQLite DB는 사용자별 Windows 앱 데이터의 `AKFES` 폴더에 저장됩니다. 비밀값은 최초 실행 시 무작위로 생성되며 설치 파일이나 저장소에 포함되지 않습니다.

## 개발 환경 원클릭 실행

저장소 루트의 다음 파일을 실행합니다.

```text
START_AKFES.bat
```

스크립트가 Python·Node.js·Rust 확인, 가상환경과 의존성 설치, FastAPI 상태 확인, Tauri 개발 앱 실행을 자동으로 처리합니다.

## 보안 흐름

- 라이선스·만료·취소 검증
- 첫 로그인 장치 바인딩
- 만료 시간이 있는 세션
- 일회용 챌린지
- HTTP 경로·본문 해시·장치 ID 기반 HMAC-SHA256 요청 서명
- 명시적 로그아웃과 미사용 챌린지 폐기
- PBKDF2-HMAC-SHA256 200,000회 기반 AES-256-GCM
- 암호문 변조와 잘못된 비밀번호 감지
- 사용자별 무작위 서버 비밀값과 로컬 전용 서버 바인딩

## 파일 전송

데스크톱은 바이너리 API를 사용합니다.

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

GitHub Actions에서는 FastAPI Ruff·pytest, TypeScript·Vite 빌드, Rust `cargo check`, PyInstaller 서버 상태 확인, Windows NSIS 설치 파일 생성을 검사합니다.

## Arduino

```text
펌웨어: firmware/arduino/project.ino
키패드: D2~D9
초록 LED: D10
빨강 LED: D11
통신 속도: 9600 baud
```

## 남은 핵심 작업

- 파일 전체 메모리 적재를 없애는 청크 기반 AKFES v3 포맷
- 실제 앱 아이콘과 코드 서명
- Windows·Arduino·서버 통합 테스트

세부 진행 상황은 [`V2_MIGRATION.md`](V2_MIGRATION.md), 개선 계획은 [`IMPROVEMENTS.md`](IMPROVEMENTS.md)를 확인하세요.
