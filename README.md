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
└─ .github/workflows/        CI·설치 파일·릴리스 자동화
```

기존 Electron 클라이언트는 제거했으며 사용자 앱과 관리자 앱은 각각 독립된 Tauri 프로그램으로 구성됩니다.

## 공식 릴리스

`vX.Y.Z` 태그를 push하면 **Publish AKFES Release** 워크플로가 다음 항목을 검증하고 GitHub Release를 자동 생성합니다.

- FastAPI Ruff·pytest
- 사용자·관리자 React·TypeScript·Vite 빌드
- 사용자·관리자 Rust `cargo check`
- PyInstaller FastAPI 사이드카 `/health` 확인
- 사용자용·관리자용 Windows NSIS 설치 파일
- 독립 서버 실행 파일
- 배포 파일 SHA-256 체크섬

릴리스 산출물:

```text
AKFES-vX.Y.Z-Windows-x64-Setup.exe
AKFES-License-Manager-vX.Y.Z-Windows-x64-Setup.exe
akfes-server-vX.Y.Z-Windows-x64.exe
SHA256SUMS.txt
```

상세 절차는 [`RELEASE.md`](RELEASE.md), 보안 제보와 비밀정보 정책은 [`SECURITY.md`](SECURITY.md)를 확인하세요.

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

관리자 앱은 서버 시작에 실패하더라도 즉시 종료되지 않습니다. 시작 오류는 다음 파일에 기록됩니다.

```text
%LOCALAPPDATA%\AKFES\license-manager-startup-error.txt
```

개발 실행:

```powershell
npm install
npm run admin:dev
```

## 로컬 빌드 원클릭 실행

저장소 루트의 `BUILD_AKFES.bat`을 실행하면 로컬 빌드에 필요한 확인과 빌드 단계를 자동으로 처리합니다.

```powershell
BUILD_AKFES.bat -Mode web -SkipTests
BUILD_AKFES.bat -Mode server
BUILD_AKFES.bat -Mode installer
BUILD_AKFES.bat
```

`-Mode web`은 사용자 앱과 관리자 앱의 React·TypeScript·Vite 빌드만 확인합니다. `-Mode server`는 FastAPI 사이드카 실행 파일을 만들고 두 Tauri 앱에 복사합니다. `-Mode installer`는 서버 실행 파일, Rust 검사, 사용자·관리자 NSIS 설치 파일 생성을 진행하고 결과물을 `release-local/`에 모읍니다. 인자를 생략하면 `-Mode all`로 실행됩니다.

설치 파일 빌드에는 Rust와 Visual Studio Build Tools의 `Desktop development with C++` 워크로드가 필요합니다.

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
- 태그와 전체 앱 버전 일치 확인
- 릴리스 파일 SHA-256 생성

## Arduino

```text
펌웨어: firmware/arduino/project.ino
키패드: D2~D9
초록 LED: D10
빨간 LED: D11
통신 속도: 9600 baud
```

## 릴리스 전 남은 외부 준비

- 임시 아이콘을 실제 AKFES 브랜드 아이콘으로 교체
- Windows Authenticode 코드 서명 인증서 발급 및 Secret 등록
- Tauri 업데이트 서명 키 등록
- Windows·Arduino·서버 실제 장치 통합 테스트
- 대용량 파일용 청크 기반 AKFES v3 포맷

코드 서명 인증서와 실제 브랜드 아이콘은 외부 자산이므로 저장소 코드만으로 자동 생성할 수 없습니다.

세부 진행 상황은 [`V2_MIGRATION.md`](V2_MIGRATION.md), 개선 계획은 [`IMPROVEMENTS.md`](IMPROVEMENTS.md)를 확인하세요.
