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
- [x] 서버 시작 실패 시 관리자 앱 즉시 종료 방지와 오류 로그
- [x] 관리자용 NSIS 설치 파일 빌드
- [x] 사용자·관리자 React·TypeScript·Rust CI
- [x] 태그와 앱 버전 일치 검증
- [x] 사용자·관리자·서버 동시 릴리스 워크플로
- [x] GitHub Release 자동 생성과 릴리스 노트
- [x] 배포 파일 SHA-256 체크섬 생성
- [x] 보안 정책·릴리스 절차·변경 기록 문서

## 관리자 앱 기능

1. 관리자 앱 실행 시 포함된 FastAPI 서버를 로컬에서 시작합니다.
2. 이미 서버가 실행 중이면 중복 실행하지 않습니다.
3. `%LOCALAPPDATA%\AKFES\server-runtime.json`의 관리자 토큰을 Rust 계층에서 읽습니다.
4. 기간과 라벨을 지정해 라이선스를 발급합니다.
5. 발급 키는 한 번만 표시되며 클립보드로 복사할 수 있습니다.
6. 라이선스 상태, 만료 시각, 장치 바인딩, 활성 세션 수를 조회합니다.
7. 라이선스 취소 또는 장치 바인딩 초기화를 실행합니다.
8. 발급·취소·초기화·로그아웃 등의 감사 로그를 조회합니다.
9. 서버 시작 오류가 발생하면 창을 유지하고 오류 파일을 남깁니다.

## 생성되는 Windows 아티팩트

일반 빌드:

- `AKFES-Windows-Installer`: 사용자용 앱 + FastAPI 사이드카
- `AKFES-License-Manager`: 관리자 앱 + FastAPI 사이드카
- `AKFES-Server-Sidecar`: 서버 단독 진단 실행 파일

태그 릴리스:

- `AKFES-vX.Y.Z-Windows-x64-Setup.exe`
- `AKFES-License-Manager-vX.Y.Z-Windows-x64-Setup.exe`
- `akfes-server-vX.Y.Z-Windows-x64.exe`
- `SHA256SUMS.txt`

## 코드로 완료할 수 없는 외부 준비

- [ ] 실제 AKFES 사용자·관리자 앱 아이콘 제공
- [ ] Windows Authenticode 코드 서명 인증서 발급
- [ ] GitHub Actions에 코드 서명·업데이트 서명 Secret 등록
- [ ] Windows + Arduino + 서버 실제 장치 통합 테스트

## 후속 기술 개선

- [ ] 청크 단위 인증이 가능한 AKFES v3 파일 포맷
- [ ] 관리자 토큰을 Windows Credential Manager 또는 TPM으로 보호
- [ ] 서명된 자동 업데이트 UI 활성화

## 현재 한계

- 파일 암복호화는 아직 전체 파일을 메모리에 적재합니다.
- 관리자 토큰은 현재 Windows 사용자 앱 데이터 파일에 저장됩니다.
- 임시 투명 아이콘은 실제 브랜드 아이콘으로 교체해야 합니다.
- Authenticode 인증서를 등록하기 전에는 Windows에서 알 수 없는 게시자 경고가 표시될 수 있습니다.
