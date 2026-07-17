# AKFES v2 Migration

이 브랜치는 AKFES를 Tauri v2 기반 데스크톱 애플리케이션으로 리팩터링하는 작업 공간입니다.

- User Desktop: Tauri v2 + Rust + React + TypeScript
- Admin Desktop: Tauri v2 + Rust + React + TypeScript
- Server: FastAPI + Uvicorn + PyInstaller sidecar
- Hardware: Arduino UNO + USB Serial

## 완료된 핵심 작업

- [x] 사용자용 Tauri 데스크톱 앱
- [x] Arduino 시리얼 연결과 키패드·LED 처리
- [x] FastAPI 라이선스·세션·장치 바인딩·감사 로그
- [x] 일회용 챌린지와 HMAC-SHA256 요청 서명
- [x] AES-256-GCM·PBKDF2-HMAC-SHA256 파일 처리
- [x] 바이너리 파일 전송 API와 네이티브 파일 선택·저장
- [x] 명시적 로그아웃과 세션·챌린지 즉시 폐기
- [x] PyInstaller FastAPI Windows 사이드카
- [x] 사용자용 NSIS 설치 파일과 원클릭 서버 실행
- [x] 관리자용 AKFES License Manager
- [x] 관리자 앱 로컬 토큰 자동 로드
- [x] 라이선스 발급·목록·취소·장치 초기화 UI
- [x] 관리자 감사 로그 UI
- [x] 관리자 앱 FastAPI 사이드카 자동 실행
- [x] 관리자용 NSIS 설치 파일 빌드
- [x] 사용자·관리자 React·TypeScript·Rust CI

## 관리자 앱 기능

1. 관리자 앱 실행 시 포함된 FastAPI 서버를 로컬에서 시작합니다.
2. `%LOCALAPPDATA%\AKFES\server-runtime.json`의 관리자 토큰을 Rust 계층에서 읽습니다.
3. 기간과 라벨을 지정해 라이선스를 발급합니다.
4. 발급 키는 한 번만 표시되며 클립보드로 복사할 수 있습니다.
5. 라이선스 상태, 만료 시각, 장치 바인딩, 활성 세션 수를 조회합니다.
6. 라이선스 취소 또는 장치 바인딩 초기화를 실행합니다.
7. 발급·취소·초기화·로그아웃 등의 감사 로그를 조회합니다.

## 생성되는 Windows 아티팩트

- `AKFES-Windows-Installer`: 사용자용 앱 + FastAPI 사이드카
- `AKFES-License-Manager`: 관리자 앱 + FastAPI 사이드카
- `AKFES-Server-Sidecar`: 서버 단독 진단 실행 파일

## 남은 핵심 작업

- [ ] 청크 단위 인증이 가능한 AKFES v3 파일 포맷
- [ ] 실제 AKFES 사용자·관리자 앱 아이콘
- [ ] Windows 코드 서명과 자동 릴리스
- [ ] 관리자 토큰을 Windows Credential Manager 또는 TPM으로 보호
- [ ] Windows + Arduino + 서버 통합 테스트

## 현재 한계

- 파일 암복호화는 아직 전체 파일을 메모리에 적재합니다.
- 관리자 토큰은 현재 Windows 사용자 앱 데이터 파일에 저장됩니다.
- 임시 투명 아이콘은 배포 전 실제 브랜드 아이콘으로 교체해야 합니다.
