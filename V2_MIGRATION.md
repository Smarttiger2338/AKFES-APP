# AKFES v2 Migration

이 브랜치는 AKFES를 Tauri v2 기반 데스크톱 애플리케이션으로 리팩터링하는 작업 공간입니다.

- Desktop: Tauri v2 + Rust + React + TypeScript
- Server: FastAPI + Uvicorn
- Hardware: Arduino UNO + USB Serial
- Security target: 서버 중심 권한 검증, 장치 바인딩, 일회용 챌린지, 요청 서명, AES-256-GCM

## 완료된 작업

- [x] Tauri v2 + React + TypeScript 데스크톱 구조
- [x] Rust 시리얼 검색·연결·해제·백그라운드 수신
- [x] Arduino `READY`, `PAIR:`, `KEY:` 처리와 키패드 매핑
- [x] FastAPI 서버 기본 구조와 보안 헤더
- [x] SQLite 기반 라이선스·세션 저장소
- [x] 라이선스 발급·검증·목록·취소와 관리자 감사 로그
- [x] HMAC 다이제스트 기반 라이선스 키·세션 토큰 저장
- [x] 일회용 챌린지와 HMAC-SHA256 요청 서명
- [x] 첫 로그인 장치 자동 바인딩과 관리자 초기화
- [x] AES-256-GCM·PBKDF2-HMAC-SHA256 파일 처리
- [x] 명시적 서버 로그아웃과 미사용 챌린지 폐기
- [x] Tauri 로그인·파일 작업·Arduino LED 연결
- [x] 네이티브 파일 열기·저장 대화상자와 상태 피드백
- [x] 바이너리 파일 전송 API와 데스크톱 클라이언트 전환
- [x] JSON Base64 전송 크기 증가와 문자열 복사 제거
- [x] 기존 JSON 파일 API 호환성 유지
- [x] Electron 클라이언트 파일 제거
- [x] 미사용 Rust `serde_json` 의존성 제거
- [x] README의 오래된 구성·미완료 설명 정리
- [x] `START_AKFES.bat` Windows 원클릭 개발 실행기
- [x] FastAPI 준비 확인 후 Tauri 자동 실행 PowerShell 스크립트
- [x] NSIS Windows 설치 실행 파일 빌드 워크플로
- [x] 빌드 시 임시 PNG·ICO 자동 생성
- [x] FastAPI Ruff·pytest, TypeScript·Vite, Rust `cargo check` CI

## 원클릭 실행 흐름

1. 저장소 루트에서 `START_AKFES.bat`을 실행합니다.
2. Python 3.11 이상, Node.js, Rust 설치 여부를 확인합니다.
3. `server/.venv`가 없으면 생성하고 FastAPI 의존성을 설치합니다.
4. 루트 `node_modules`가 없으면 npm 의존성을 설치합니다.
5. `http://127.0.0.1:8000/health`를 확인하고 서버가 없으면 시작합니다.
6. 서버 준비가 확인되면 `npm run desktop:dev`로 Tauri 앱을 실행합니다.

## 바이너리 파일 작업 흐름

1. 네이티브 대화상자로 파일을 선택하고 Arduino 키패드로 비밀번호를 입력합니다.
2. `/api/v2/auth/challenge`에서 일회용 챌린지를 받습니다.
3. 원본 파일 바이트의 SHA-256을 포함한 HMAC-SHA256 요청 서명을 생성합니다.
4. 파일을 `application/octet-stream`으로 `/api/v2/files/encrypt-binary` 또는 `/api/v2/files/decrypt-binary`에 전송합니다.
5. 서버 응답도 바이너리로 수신하고 파일명·크기·알고리즘 헤더를 검증합니다.
6. Rust 네이티브 저장 대화상자로 결과를 기록합니다.

Base64로 인한 약 33% 전송량 증가와 JSON 문자열 직렬화 비용은 제거됐습니다. 다만 현재 암복호화 자체는 파일 전체를 메모리에 적재합니다.

## Windows 설치 파일

`.github/workflows/windows-installer.yml`은 Windows runner에서 Tauri NSIS 번들을 생성하고 `AKFES-Windows-Installer` 아티팩트로 업로드합니다. 현재 설치 파일에는 데스크톱 앱만 포함되며 FastAPI 서버는 별도 실행이 필요합니다.

## 진행 예정

- [ ] FastAPI 서버 Windows 사이드카 패키징
- [ ] 청크 단위 인증이 가능한 AKFES v3 파일 포맷
- [ ] Windows TPM 기반 장치 키 검토
- [ ] 실제 AKFES 앱 아이콘 교체
- [ ] 코드 서명과 자동 릴리스
- [ ] Windows + Arduino + 서버 통합 테스트

## 현재 한계

- 네이티브 파일 선택과 서버 AES-GCM 처리는 아직 파일 전체를 메모리에 올립니다.
- GitHub Actions가 만드는 NSIS 설치 파일은 데스크톱 앱 전용입니다.
- `build.rs`의 투명 임시 아이콘은 설치 빌드 검증용이므로 배포 전 실제 브랜드 아이콘으로 교체해야 합니다.
