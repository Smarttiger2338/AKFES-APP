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
- [x] SQLite 기반 라이선스·세션 저장소 구현
- [x] 관리자 토큰 기반 라이선스 발급 API 구현
- [x] 라이선스 검증과 만료 세션 발급 API 구현
- [x] 선택적 장치 ID 세션 바인딩 구현
- [x] 라이선스 키·세션 토큰 원문 대신 HMAC 다이제스트 저장
- [x] 라이선스 목록 조회와 상태·활성 세션 수 표시
- [x] 라이선스 취소와 관련 세션 즉시 무효화
- [x] 관리자 작업자 식별 헤더와 감사 로그 저장·조회
- [x] FastAPI 상태 확인·인증·관리 흐름 자동 테스트 추가
- [x] v2 기준 README와 서버 실행 문서 작성

## 진행 예정

- [ ] 일회용 챌린지와 요청 서명 검증 연결
- [ ] 장치 바인딩 정책 강화
- [ ] 실제 파일 암호화·복호화 API 연결
- [ ] Tauri 라이선스 로그인 화면과 FastAPI 연결
- [ ] 결과 파일 저장 대화상자 연결
- [ ] 앱 아이콘 및 Windows 설치 프로그램
- [ ] 코드 서명과 자동 릴리스
- [ ] Windows + Arduino + 서버 통합 테스트

## 검증 상태

- FastAPI 서버 코드 정적 검토 완료
- 기존 인증 흐름 테스트에 라이선스 목록·취소·세션 무효화·감사 로그 검증 추가
- 외부 네트워크가 차단된 현재 실행 환경에서는 저장소 복제 기반 전체 테스트를 다시 실행하지 못함
- 실제 Arduino 연결과 Windows Tauri 실행은 해당 장치가 있는 개발 환경에서 추가 검증 필요
- 전체 데스크톱 빌드와 Rust `cargo check`는 Windows Rust/Tauri 환경에서 추가 검증 필요

## 현재 한계

라이선스 발급·검증·목록·취소와 기본 세션, 관리자 감사 로그는 새 서버로 이전됐습니다. 일회용 챌린지, 요청 서명, 강제 장치 바인딩, 파일 암호화·복호화는 아직 연결되지 않았으며 Tauri 클라이언트도 새 인증 API를 아직 호출하지 않습니다.
