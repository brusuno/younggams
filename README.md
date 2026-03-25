# 은솔마린 실시간 예약

은솔마린 바다낚시 예약을 실제 서버에 배포해 사용할 수 있도록 만든 웹앱입니다.

## 핵심 기능
- 날짜/회차별 잔여 좌석 조회
- 즉시 예약 생성 및 좌석 차감
- SQLite 기반 예약 데이터 저장
- 동시 예약 시 초과 예약 방지 트랜잭션 처리
- 5초 자동 갱신으로 다중 사용자 예약 반영

## 로컬 실행
```bash
npm start
```
또는
```bash
python3 server.py
```

접속: `http://localhost:4173`

## 실제 배포 방법 (추천)
### 1) Ubuntu 서버 준비
- 22/tcp(SSH), 80/tcp(HTTP), 443/tcp(HTTPS) 오픈
- Python 3 설치

### 2) 앱 실행 서비스 등록 (`systemd`)
아래 예시는 `/opt/eunsol-marine` 경로 배포 기준입니다.

`/etc/systemd/system/eunsol-marine.service`
```ini
[Unit]
Description=Eunsol Marine Booking Service
After=network.target

[Service]
WorkingDirectory=/opt/eunsol-marine
ExecStart=/usr/bin/python3 /opt/eunsol-marine/server.py
Restart=always
User=www-data
Group=www-data
Environment=PORT=4173

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now eunsol-marine
sudo systemctl status eunsol-marine
```

### 3) Nginx 리버스 프록시
```nginx
server {
    server_name reservation.eunsolmarine.com;

    location / {
        proxy_pass http://127.0.0.1:4173;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

### 4) HTTPS 적용
```bash
sudo certbot --nginx -d reservation.eunsolmarine.com
```

## 운영 시 추가 권장사항
- 관리자 페이지(예약 조회/취소/변경)
- 휴대폰 인증(SMS)
- 결제 연동
- 예약/취소 알림톡
- 백업 및 모니터링
