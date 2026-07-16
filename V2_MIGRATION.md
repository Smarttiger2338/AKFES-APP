# AKFES v2 Migration

이 브랜치는 AKFES를 Tauri v2 기반 데스크톱 애플리케이션으로 리팩터링하는 작업 공간입니다.

- Desktop: Tauri v2 + Rust + React + TypeScript
- Server: FastAPI + Uvicorn
- Hardware: Arduino UNO + USB Serial
- Security target: 서버 중심 권한 검증, 장치 바인딩, 일회용 챌린지, 요청 서명, AES-256-GCM

## 목표 구조

```text
apps/
  desktop/
    src/
    src-tauri/
server/
  app/
  tests/
firmware/
  arduino/
docs/
```

## 완료된 작업

- [x] v2 전용 브랜치 생성
- [x] npm 워크스페이스 구성
- [x] Tauri v2 Rust 프로젝트 초기화
- [x] React + TypeScript + Vite UI 초기화
- [x] 대표 블루 테마와 독자적인 상단 바 적용
- [x] 스크롤바가 노출되지 않는 반응형 화면 적용
- [x] 라이선스 → 장치 연결 → 파일 작업 → 결과의 단계별 구조 구현
- [x] Rust 기반 시리얼 포트 검색 명령 구현
- [x] Rust 시리얼 포트 연결·해제와 백그라운드 수신 구현
- [x] Arduino `READY`, `PAIR:`, `KEY:` 프로토콜 처리
- [x] 16키 키패드 매핑, 비밀번호 입력, LED 테스트 UI 연결
- [x] Arduino 펌웨어를 `firmware/arduino`로 이전
- [x] 기존 Electron main/preload/renderer/launcher/package 설정 제거
- [x] FastAPI 서버 기본 구조 생성
- [x] `/api/v2/health` 및 호환용 `/health` 상태 확인 API 구현
- [x] CORS, Trusted Host, 보안 응답 헤더, 환경변수 설정 추가
- [x] FastAPI 상태 확인 자동 테스트 추가
- [x] v2 기준 README와 서버 실행 문서 작성

## 진행 예정

- [ ] 기존 라이선스 발급·검증 로직 이전
- [ ] 만료 시간이 있는 세션과 일회용 챌린지 로직 이전
- [ ] 장치 바인딩과 요청 서명 검증 연결
- [ ] 실제 파일 암호화·복호화 API 연결
- [ ] 결과 파일 저장 대화상자 연결
- [ ] 앱 아이콘 및 Windows 설치 프로그램
- [ ] 코드 서명과 자동 릴리스
- [ ] Windows + Arduino + 서버 통합 테스트

## 검증 상태

- FastAPI 서버 코드 Python 구문 검사 통과
- `python -m pytest`: 2개 테스트 통과
- 실제 Arduino 연결과 Windows Tauri 실행은 해당 장치가 있는 개발 환경에서 추가 검증 필요
- 전체 데스크톱 빌드와 Rust `cargo check`는 Windows Rust/Tauri 환경에서 추가 검증 필요

## 현재 한계

Arduino 연결과 FastAPI 기본 서버는 준비됐지만 라이선스 인증, 세션, 장치 바인딩, 요청 서명, 파일 암호화·복호화는 아직 새 서버와 연결되지 않았습니다. 클라이언트는 이 기능들이 성공한 것처럼 임의로 표시하지 않습니다.
