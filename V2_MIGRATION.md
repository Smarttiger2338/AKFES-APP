# AKFES v2 Migration

이 브랜치는 AKFES를 Tauri v2 기반 데스크톱 애플리케이션으로 리팩터링하는 작업 공간입니다.

- Desktop: Tauri v2 + Rust + React + TypeScript
- Server: FastAPI + Uvicorn + PyInstaller sidecar
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
- [x] Electron 클라이언트 파일 제거와 미사용 의존성 정리
- [x] `START_AKFES.bat` Windows 원클릭 개발 실행기
- [x] NSIS Windows 설치 실행 파일 빌드 워크플로
- [x] PyInstaller 기반 `akfes-server.exe` 사이드카 구성
- [x] 사용자 앱 데이터 기반 무작위 서버 비밀값과 SQLite 경로
- [x] Tauri 시작 시 내장 서버 자동 실행, 종료 시 프로세스 정리
- [x] 서버 사이드카 상태 확인 후 NSIS 패키징 워크플로
- [x] FastAPI Ruff·pytest, TypeScript·Vite, Rust `cargo check` CI

## 설치형 원클릭 실행 흐름

1. NSIS 설치 프로그램이 Tauri 앱과 `akfes-server.exe`를 함께 설치합니다.
2. 사용자가 AKFES 앱을 실행하면 Rust가 포함된 서버 실행 파일을 찾습니다.
3. 서버가 `%LOCALAPPDATA%\AKFES`에 무작위 라이선스 비밀값·관리자 토큰을 최초 생성합니다.
4. 같은 폴더의 SQLite DB를 사용해 재실행 후에도 라이선스와 세션 데이터가 유지됩니다.
5. FastAPI는 `127.0.0.1:8000`에만 바인딩되고 운영 모드에서 API 문서를 비활성화합니다.
6. 앱 종료 시 Rust가 자신이 시작한 서버 프로세스를 종료합니다.

## 바이너리 파일 작업 흐름

1. 네이티브 대화상자로 파일을 선택하고 Arduino 키패드로 비밀번호를 입력합니다.
2. `/api/v2/auth/challenge`에서 일회용 챌린지를 받습니다.
3. 원본 파일 바이트의 SHA-256을 포함한 HMAC-SHA256 요청 서명을 생성합니다.
4. 파일을 `application/octet-stream`으로 바이너리 파일 API에 전송합니다.
5. 서버 응답도 바이너리로 수신하고 파일명·크기·알고리즘 헤더를 검증합니다.
6. Rust 네이티브 저장 대화상자로 결과를 기록합니다.

## Windows 설치 빌드

`.github/workflows/windows-installer.yml`은 다음을 자동 수행합니다.

1. PyInstaller로 FastAPI 서버 단독 실행 파일 생성
2. 서버 실행 후 `/health` 상태 확인
3. 서버 실행 파일을 Tauri 리소스에 복사
4. NSIS 설치 프로그램 생성
5. `AKFES-Windows-Installer`와 진단용 `AKFES-Server-Sidecar` 아티팩트 업로드

## 진행 예정

- [ ] 청크 단위 인증이 가능한 AKFES v3 파일 포맷
- [ ] Windows TPM 기반 장치 키 검토
- [ ] 실제 AKFES 앱 아이콘 교체
- [ ] 코드 서명과 자동 릴리스
- [ ] Windows + Arduino + 서버 통합 테스트

## 현재 한계

- 네이티브 파일 선택과 서버 AES-GCM 처리는 아직 파일 전체를 메모리에 올립니다.
- 서버는 로컬 포트 8000을 사용하므로 다른 프로그램이 점유한 경우 시작 오류 처리가 추가로 필요합니다.
- `build.rs`의 투명 임시 아이콘은 빌드 검증용이므로 배포 전 실제 브랜드 아이콘으로 교체해야 합니다.
