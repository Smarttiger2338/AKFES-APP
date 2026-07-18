# Changelog

All notable changes to AKFES are documented in this file.

## [2.0.0] - 2026-07-18

### Added

- Tauri v2 사용자 데스크톱 앱
- 별도 AKFES License Manager 관리자 앱
- FastAPI 서버 Windows 사이드카
- Arduino USB Serial 연결과 키패드 입력
- 라이선스 발급·검증·취소·장치 바인딩 초기화
- 만료 세션, 명시적 로그아웃, 일회용 챌린지
- HMAC-SHA256 요청 서명
- AES-256-GCM 파일 암호화·복호화
- PBKDF2-HMAC-SHA256 키 파생
- 바이너리 파일 전송 API
- 네이티브 파일 열기·저장 대화상자
- 관리자 감사 로그
- GitHub Actions CI
- 사용자·관리자 NSIS 설치 파일 빌드
- 태그 기반 GitHub Release 자동 배포
- SHA-256 배포 파일 체크섬
- 보안 정책과 릴리스 절차 문서

### Changed

- Electron과 PySide6 클라이언트를 Tauri·Rust·React·TypeScript로 교체
- JSON Base64 파일 전송을 바이너리 전송으로 전환
- 서버 비밀값과 SQLite DB를 사용자별 Windows 앱 데이터에 저장
- 라이선스 키와 세션 토큰 원문을 DB에 저장하지 않도록 변경

### Fixed

- 관리자 앱에서 내장 서버 시작 실패 시 창이 즉시 종료되던 문제
- 설치 빌드에서 Tauri 기본 아이콘 누락으로 발생하던 컨텍스트 생성 실패
- CI에서 Ruff·TypeScript·Rust 진단을 확인하기 어려웠던 문제

### Security

- 장치 바인딩
- 라이선스·세션·챌린지 HMAC 다이제스트 저장
- 요청 본문 해시를 포함한 서명 검증
- AES-GCM 인증 태그 기반 암호문 변조 감지
- 관리자 작업 감사 추적

### Known limitations

- Windows Authenticode 코드 서명 인증서 미적용
- 실제 브랜드 아이콘 미적용
- 파일 암호화 시 전체 파일 메모리 적재
- 실제 Windows·Arduino 장치 조합의 수동 통합 테스트 필요
