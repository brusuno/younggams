import json
import os
import sqlite3
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = int(os.environ.get('PORT', '4173'))
MAX_SEATS = 22
TRIPS = [
    {'id': 'dawn', 'name': '새벽 출항', 'time': '05:30 ~ 11:30'},
    {'id': 'day', 'name': '오전 출항', 'time': '09:00 ~ 15:00'},
    {'id': 'sunset', 'name': '오후 출항', 'time': '13:30 ~ 19:30'},
]
DB_PATH = os.path.join(os.path.dirname(__file__), 'booking.db')


def get_conn():
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute(
            '''
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_date TEXT NOT NULL,
                trip_id TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                customer_phone TEXT NOT NULL,
                guest_count INTEGER NOT NULL CHECK (guest_count > 0),
                created_at TEXT NOT NULL
            )
            '''
        )


def is_valid_date(date_text):
    try:
        datetime.strptime(date_text, '%Y-%m-%d')
        return True
    except ValueError:
        return False


def is_valid_month(month_text):
    try:
        datetime.strptime(month_text, '%Y-%m')
        return True
    except ValueError:
        return False


def get_availability(conn, booking_date):
    rows = conn.execute(
        '''
        SELECT trip_id, COALESCE(SUM(guest_count), 0) AS reserved
        FROM bookings
        WHERE booking_date = ?
        GROUP BY trip_id
        ''',
        (booking_date,),
    ).fetchall()
    reserved_by_trip = {row['trip_id']: int(row['reserved']) for row in rows}

    slots = []
    for trip in TRIPS:
        reserved = reserved_by_trip.get(trip['id'], 0)
        slots.append(
            {
                **trip,
                'maxSeats': MAX_SEATS,
                'reserved': reserved,
                'remaining': max(0, MAX_SEATS - reserved),
            }
        )
    return slots


def get_month_summary(conn, month_text):
    rows = conn.execute(
        '''
        SELECT booking_date, COALESCE(SUM(guest_count), 0) AS reserved
        FROM bookings
        WHERE booking_date LIKE ?
        GROUP BY booking_date
        ''',
        (f'{month_text}-%',),
    ).fetchall()

    days = {}
    total_capacity = MAX_SEATS * len(TRIPS)
    for row in rows:
        reserved = int(row['reserved'])
        days[row['booking_date']] = {
            'reserved': reserved,
            'capacity': total_capacity,
            'remaining': max(0, total_capacity - reserved),
        }
    return days


class Handler(SimpleHTTPRequestHandler):
    def _send_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get('Content-Length', '0'))
        if length <= 0:
            return None
        raw = self.rfile.read(length)
        return json.loads(raw.decode('utf-8'))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/healthz':
            return self._send_json({'ok': True, 'service': 'eunsol-marine'})

        if parsed.path == '/api/config':
            return self._send_json({'siteName': '은솔마린', 'trips': TRIPS, 'maxSeats': MAX_SEATS})

        if parsed.path == '/api/availability':
            qs = parse_qs(parsed.query)
            booking_date = qs.get('date', [None])[0]
            if not booking_date:
                return self._send_json({'message': 'date 쿼리가 필요합니다.'}, HTTPStatus.BAD_REQUEST)
            if not is_valid_date(booking_date):
                return self._send_json({'message': 'date 형식은 YYYY-MM-DD 이어야 합니다.'}, HTTPStatus.BAD_REQUEST)

            with get_conn() as conn:
                slots = get_availability(conn, booking_date)
            return self._send_json({'date': booking_date, 'slots': slots})

        if parsed.path == '/api/calendar':
            qs = parse_qs(parsed.query)
            month = qs.get('month', [None])[0]
            if not month:
                return self._send_json({'message': 'month 쿼리가 필요합니다.'}, HTTPStatus.BAD_REQUEST)
            if not is_valid_month(month):
                return self._send_json({'message': 'month 형식은 YYYY-MM 이어야 합니다.'}, HTTPStatus.BAD_REQUEST)

            with get_conn() as conn:
                days = get_month_summary(conn, month)
            return self._send_json({'month': month, 'days': days})

        if parsed.path == '/':
            self.path = '/index.html'
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != '/api/bookings':
            return self._send_json({'message': 'Not Found'}, HTTPStatus.NOT_FOUND)

        try:
            payload = self._read_json() or {}
        except json.JSONDecodeError:
            return self._send_json({'message': 'JSON 형식이 올바르지 않습니다.'}, HTTPStatus.BAD_REQUEST)

        booking_date = payload.get('bookingDate')
        trip_id = payload.get('tripId')
        customer_name = (payload.get('customerName') or '').strip()
        customer_phone = (payload.get('customerPhone') or '').strip()
        guest_count = payload.get('guestCount')

        try:
            guest_count = int(guest_count)
        except (TypeError, ValueError):
            guest_count = 0

        if not booking_date or not trip_id or not customer_name or not customer_phone:
            return self._send_json({'message': '필수 항목이 누락되었습니다.'}, HTTPStatus.BAD_REQUEST)

        if not is_valid_date(booking_date):
            return self._send_json({'message': '예약 날짜 형식이 올바르지 않습니다.'}, HTTPStatus.BAD_REQUEST)

        if guest_count < 1 or guest_count > 6:
            return self._send_json({'message': '예약 인원은 1~6명 사이여야 합니다.'}, HTTPStatus.BAD_REQUEST)

        if trip_id not in {trip['id'] for trip in TRIPS}:
            return self._send_json({'message': '존재하지 않는 회차입니다.'}, HTTPStatus.BAD_REQUEST)

        now = datetime.utcnow().isoformat(timespec='seconds')

        with get_conn() as conn:
            conn.execute('BEGIN IMMEDIATE')
            slots = get_availability(conn, booking_date)
            selected = next((slot for slot in slots if slot['id'] == trip_id), None)

            if not selected or selected['remaining'] < guest_count:
                conn.execute('ROLLBACK')
                return self._send_json({'message': '잔여 좌석이 부족합니다.'}, HTTPStatus.CONFLICT)

            conn.execute(
                '''
                INSERT INTO bookings (booking_date, trip_id, customer_name, customer_phone, guest_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (booking_date, trip_id, customer_name, customer_phone, guest_count, now),
            )
            conn.execute('COMMIT')

        return self._send_json({'message': '예약이 완료되었습니다.'}, HTTPStatus.CREATED)


if __name__ == '__main__':
    init_db()
    server = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    print(f'은솔마린 예약 서버 실행: http://localhost:{PORT}')
    server.serve_forever()
