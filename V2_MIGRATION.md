# AKFES v2 Migration

이 브랜치는 AKFES를 Tauri v2 기반 데스크톱 애플리케이션으로 리팩터링하는 작업 공간입니다.

- Desktop: Tauri v2 + Rust + React + TypeScript
- Server target: FastAPI + Uvicorn
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
- [x] Arduino 펌웨어를 `firmware/arduino`로 이전
- [x] 기존 Electron main/preload/renderer/launcher/package 설정 제거
- [x] v2 기준 README 재작성

## 진행 예정

- [ ] Rust 시리얼 포트 연결·해제
- [ ] Arduino 데이터 수신과 키패드 매핑
- [ ] FastAPI 서버 기본 구조 생성
- [ ] 기존 라이선스·세션·챌린지 로직 이전
- [ ] 실제 파일 암호화·복호화 API 연결
- [ ] 장치 바인딩과 요청 서명 연결
- [ ] 앱 아이콘 및 Windows 설치 프로그램
- [ ] 코드 서명과 자동 릴리스
- [ ] Windows + Arduino + 서버 통합 테스트

## 현재 한계

현재 Tauri 기본 프로젝트와 시리얼 포트 조회 기능까지 작성된 상태입니다. 라이선스 입력 화면과 파일 작업 화면은 실제 서버 기능을 성공한 것처럼 위조하지 않으며, FastAPI 이전이 완료되기 전까지 초기화 상태로 동작합니다.
