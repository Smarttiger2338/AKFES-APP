# AKFES v2

Arduino 키패드를 이용해 파일 암호화·복호화 비밀번호를 입력하는 데스크톱 보안 애플리케이션입니다.

이 브랜치에서는 기존 Electron과 PySide6 클라이언트를 사용하지 않습니다. 데스크톱 클라이언트는 Tauri v2, Rust, React, TypeScript로 다시 구성하고 있습니다.

## 현재 구성

```text
AKFES-APP/
├─ apps/
│  └─ desktop/
│     ├─ src/                 React + TypeScript UI
│     └─ src-tauri/           Tauri v2 + Rust
├─ firmware/
│  └─ arduino/
│     └─ project.ino
├─ AKFES-Server/              기존 서버, FastAPI 이전 예정
├─ V2_MIGRATION.md
└─ package.json
```

## 데스크톱 클라이언트

현재 구현된 기능:

- Tauri v2 데스크톱 프로젝트 구조
- React·TypeScript 기반 단계별 화면
- 대표 블루 색상의 웹앱형 디자인
- 기본 운영체제 제목 표시줄을 대신하는 AKFES 전용 상단 바
- 최소화, 최대화·복원, 종료 버튼
- 화면 스크롤바 숨김
- 라이선스 → 장치 연결 → 파일 작업 → 결과 흐름
- Rust 명령을 통한 시리얼 포트 검색
- Arduino 펌웨어의 `firmware/arduino` 경로 이전

라이선스 인증과 실제 파일 처리는 아직 v2 서버와 연결하지 않았습니다. 화면에서 인증 성공이나 파일 처리 성공을 임의로 표시하지 않도록 초기화 상태로 두었습니다.

## 실행 준비

필요한 개발 도구:

- Node.js 및 npm
- Rust 및 Cargo
- Tauri v2를 빌드할 수 있는 Windows 개발 환경

저장소 루트에서 실행합니다.

```bash
npm install
npm run desktop:dev
```

프런트엔드 화면만 확인할 때는 다음 명령을 사용합니다.

```bash
npm run desktop:web
```

배포 빌드는 다음 명령으로 준비되어 있습니다.

```bash
npm run desktop:build
```

현재 `tauri.conf.json`의 번들 생성은 비활성화되어 있습니다. 앱 아이콘, 설치 프로그램, 코드 서명 구성을 완료한 뒤 활성화할 예정입니다.

## Rust 시리얼 통신

현재 Rust 명령 `list_serial_ports`가 운영체제의 시리얼 포트를 조회하여 React 화면에 전달합니다.

다음 단계에서 추가할 항목:

- Arduino 포트 연결 및 연결 해제
- 9600 baud 데이터 수신
- `READY`, `PAIR`, `LED:GREEN`, `LED:RED` 프로토콜 처리
- 키패드 입력 매핑과 비밀번호 상태 관리

## 서버 이전 상태

현재 저장소에는 기존 Python 서버가 남아 있습니다. 다음 단계에서 FastAPI 기반 서버 구조로 이전하며 다음 보안 원칙을 유지합니다.

- 클라이언트를 신뢰하지 않는 서버 중심 권한 검증
- 라이선스 및 세션 검증
- 장치 바인딩
- 일회용 챌린지와 요청 서명
- AES-256-GCM 파일 처리
- 허용된 API 경로만 공개

운영 서버의 비밀키와 설정은 클라이언트에 포함하지 않습니다.

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

> 현재 브랜치는 리팩터링 중인 개발 브랜치입니다. 실제 Arduino, Rust 의존성, Tauri 창, 서버 통신을 함께 실행한 통합 테스트는 아직 완료되지 않았습니다.
