# AKFES v2

Arduino 키패드와 Tauri 데스크톱 앱을 이용해 파일을 AES-256-GCM으로 암호화·복호화하는 프로젝트입니다.

## 구성

```text
AKFES-APP/
├─ apps/desktop/             사용자용 Tauri 데스크톱 앱
├─ apps/admin/               관리자용 라이선스 관리 앱
├─ server/                   FastAPI 인증·암호화 서버와 사이드카 진입점
├─ firmware/arduino/         Arduino UNO 펌웨어
├─ scripts/                  Windows 개발 실행 스크립트
├─ START_AKFES.bat           개발 환경 원클릭 실행
└─ .github/workflows/        CI와 Windows 설치 파일 빌드
```

기존 Electron 클라이언트는 제거했으며 사용자 앱과 관리자 앱은 각각 독립된 Tauri 프로그램으로 구성됩니다.

## 사용자용 Windows 설치

GitHub Actions의 **Build AKFES Windows Installer** 워크플로가 FastAPI 서버를 포함한 NSIS 설치 파일을 생성합니다.

```text
AKFES-Windows-Installer
```

설치 후 AKFES 앱만 실행하면 포함된 `akfes-server.exe`와 데스크톱 화면이 함께 시작됩니다. 서버 비밀값과 SQLite DB는 사용자별 Windows 앱 데이터의 `AKFES` 폴더에 저장됩니다.

## 관리자용 License Manager

GitHub Actions의 **Build AKFES License Manager** 워크플로가 별도의 관리자 설치 파일을 생성합니다.

```text
AKFES-License-Manager
```

관리자 프로그램에서 다음 작업을 수행할 수 있습니다.

- 기간과 라벨을 지정한 라이선스 발급
- 생성된 라이선스 키 즉시 복사
- 활성·만료·취소 라이선스 목록 조회
- 활성 세션 수와 장치 바인딩 상태 확인
- 라이선스 취소와 기존 세션 무효화
- 장치 바인딩 초기화
- 관리자 감사 로그 조회

관리자 앱도 FastAPI 사이드카를 포함하며 로컬 `%LOCALAPPDATA%\AKFES\server-runtime.json`의 관리자 토큰을 Rust 계층에서 읽습니다. 관리자 토큰은 화면에 평문으로 표시하지 않으며, 원격 서버를 관리할 때만 직접 입력할 수 있습니다.

개발 실행:

```powershell
npm install
npm run admin:dev
```

## 개발 환경 원클릭 실행

저장소 루트의 `START_AKFES.bat`을 실행하면 Python·Node.js·Rust 확인, 가상환경과 의존성 설치, FastAPI 상태 확인, 사용자용 Tauri 개발 앱 실행을 자동으로 처리합니다.

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
- 관리자 작업 감사 로그

## 파일 전송

사용자용 데스크톱은 바이너리 API를 사용합니다.

```text
POST /api/v2/files/encrypt-binary
POST /api/v2/files/decrypt-binary
```

파일은 `application/octet-stream`으로 전송되어 JSON Base64 방식의 약 33% 크기 증가와 문자열 복사 비용을 제거합니다. 기존 JSON API는 호환성을 위해 서버에 남아 있습니다.

## 검사

GitHub Actions에서는 다음 항목을 검사합니다.

- FastAPI Ruff·pytest
- 사용자 앱과 관리자 앱 React·TypeScript·Vite 빌드
- 사용자 앱과 관리자 앱 Rust `cargo check`
- PyInstaller 서버 상태 확인
- 사용자용·관리자용 Windows NSIS 설치 파일 생성

## Arduino

```text
펌웨어: firmware/arduino/project.ino
키패드: D2~D9
초록 LED: D10
빨간 LED: D11
통신 속도: 9600 baud
```

## 남은 핵심 작업

- 파일 전체 메모리 적재를 없애는 청크 기반 AKFES v3 포맷
- 실제 앱 아이콘과 Windows 코드 서명
- 관리자 권한을 Windows 자격 증명 또는 TPM과 연결
- Windows·Arduino·서버 통합 테스트

세부 진행 상황은 [`V2_MIGRATION.md`](V2_MIGRATION.md), 개선 계획은 [`IMPROVEMENTS.md`](IMPROVEMENTS.md)를 확인하세요.
