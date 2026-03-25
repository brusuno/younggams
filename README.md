# 은솔마린 통합 홈페이지

은솔마린 바다낚시 운영에 필요한 핵심 페이지를 포함한 웹앱입니다.

## 구성 페이지
- 메인 페이지: `/`
- 실시간 예약 페이지(캘린더/정원/예약현황): `/booking.html`
- 배 소개 페이지: `/boats.html`
- 게시판 페이지(조업현황/공지사항): `/board.html`

## 핵심 기능
- 월간 캘린더에서 날짜별 정원/예약/잔여 현황 조회
- 날짜/회차별 잔여 좌석 조회 및 즉시 예약
- 조업현황 게시판 등록/조회
- 공지사항 게시판 등록/조회
- SQLite 기반 데이터 저장

## 로컬 실행
```bash
npm start
```
또는
```bash
python3 server.py
```

접속: `http://localhost:4173`

## API
- `GET /api/config`
- `GET /api/availability?date=YYYY-MM-DD`
- `GET /api/calendar?month=YYYY-MM`
- `POST /api/bookings`
- `GET /api/posts?board=catch|notice`
- `POST /api/posts`

## 배포
기존 `Dockerfile`, `docker-compose.yml`, `systemd`, `nginx` 구성으로 그대로 배포 가능합니다.
