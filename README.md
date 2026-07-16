# AKFES v2

Arduino 키패드를 이용해 파일 암호화·복호화 비밀번호를 입력하는 데스크톱 보안 애플리케이션입니다.

이 브랜치에서는 기존 Electron과 PySide6 클라이언트를 사용하지 않습니다. 데스크톱 클라이언트는 Tauri v2, Rust, React, TypeScript로 다시 구성하고 있으며 서버는 FastAPI로 단계적으로 이전하고 있습니다.

## 현재 구성

```text
AKFES-APP/
├─ apps/
│  └─ desktop/
│     ├─ src/                 React + TypeScript UI
│     └─ src-tauri/           Tauri v2 + Rust
├─ server/
│  ├─ app/                    FastAPI v2 애플리케이션
│  ├─ tests/                  서버 자동 테스트
│  └─ README.md
├─ firmware/
│  └─ arduino/
│     └─ project.ino
├─ AKFES-Server/              이전 전의 기존 서버
├─ V2_MIGRATION.md
└─ package.json
```

## 데스크톱 클라이언트

현재 구현된 기능:

- Tauri v2 데스크톱 프로젝트 구조
- React·TypeScript 기반 단계별 화면
- 대표 블루 색상의 웹앱형 디자인
- AKFES 전용 상단 바와 창 제어 버튼
- 라이선스 → 장치 연결 → 파일 작업 → 결과 흐름
- Rust 기반 시리얼 포트 검색, 연결, 해제, 송신, 백그라운드 수신
- Arduino `READY`, `PAIR:`, `KEY:` 프로토콜 처리
- 16키 키패드 매핑과 로컬 저장
- 키패드 비밀번호 입력과 삭제
- `SUCCESS`, `FAIL` 명령을 이용한 초록·빨강 LED 테스트
- 연결 상태, 오류, 통신 로그 UI

라이선스 인증과 실제 파일 처리는 아직 v2 서버와 연결하지 않았습니다. 화면에서 인증 성공이나 파일 처리 성공을 임의로 표시하지 않습니다.

## 데스크톱 실행 준비

필요한 개발 도구:

- Node.js 및 npm
- Rust 및 Cargo
- Tauri v2를 빌드할 수 있는 Windows 개발 환경

저장소 루트에서 실행합니다.

```bash
npm install
npm run desktop:dev
```

프런트엔드 화면만 확인할 때:

```bash
npm run desktop:web
```

배포 빌드:

```bash
npm run desktop:build
```

현재 `tauri.conf.json`의 번들 생성은 비활성화되어 있습니다. 앱 아이콘, 설치 프로그램, 코드 서명 구성을 완료한 뒤 활성화할 예정입니다.

## FastAPI 서버

새 서버 기본 구조는 `server/`에 있습니다.

현재 구현된 기능:

- `GET /api/v2/health`
- 기존 클라이언트 호환용 `GET /health`
- 환경변수 기반 CORS와 Trusted Host 제한
- 업로드 최대 크기 설정
- 캐시 방지, Referrer 제한, MIME 스니핑 방지, 요청 ID 응답 헤더
- 개발 환경에서만 기본 활성화되는 API 문서
- pytest 상태 확인 테스트

Windows PowerShell 실행 예시:

```powershell
cd server
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

검사:

```powershell
python -m pytest
python -m ruff check .
```

자세한 서버 설정은 [`server/README.md`](server/README.md)에서 확인할 수 있습니다.

## 남은 서버 이전

기존 `AKFES-Server`의 다음 기능은 검증하면서 새 `server/`로 옮길 예정입니다.

- 라이선스 발급·검증
- 만료 시간이 있는 세션
- 장치 바인딩
- 일회용 챌린지와 요청 서명
- AES-256-GCM 파일 처리
- 결과 파일 다운로드

운영 서버의 비밀키와 설정은 클라이언트나 저장소에 포함하지 않습니다.

## Arduino

펌웨어 위치:

```text
firmware/arduino/project.ino
```

기본 핀 구성:

```text
키패드 8선: D2~D9
초록색 LED: D10
빨간색 LED: D11
통신 속도: 9600 baud
```

## 마이그레이션 진행 상황

자세한 작업 상태는 [`V2_MIGRATION.md`](V2_MIGRATION.md)에서 확인할 수 있습니다.

> 현재 브랜치는 리팩터링 중인 개발 브랜치입니다. FastAPI 상태 확인 테스트는 통과했지만 실제 Arduino, Windows Tauri 빌드, 라이선스, 파일 암호화까지 포함한 통합 테스트는 아직 완료되지 않았습니다.
