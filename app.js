const dateInput = document.querySelector('#bookingDate');
const boatSelect = document.querySelector('#boatSelect');
const slotsContainer = document.querySelector('#slots');
const tripSelect = document.querySelector('#tripSelect');
const bookingForm = document.querySelector('#bookingForm');
const message = document.querySelector('#message');
const slotTemplate = document.querySelector('#slotTemplate');
const monthLabel = document.querySelector('#monthLabel');
const calendarHead = document.querySelector('#calendarHead');
const calendarGrid = document.querySelector('#calendarGrid');
const prevMonthBtn = document.querySelector('#prevMonthBtn');
const nextMonthBtn = document.querySelector('#nextMonthBtn');

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토'];

let trips = [];
let boats = [];
let selectedBoatId = '';
let pollTimer;
let currentMonth;
let calendarSummary = {};

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function monthKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
}

function setMessage(text, ok = false) {
  message.textContent = text;
  message.className = `message ${ok ? 'ok' : 'error'}`;
}

function renderTripOptions() {
  const selected = tripSelect.value;
  tripSelect.querySelectorAll('option[data-trip]').forEach((option) => option.remove());
  trips.forEach((trip) => {
    const option = document.createElement('option');
    option.value = trip.id;
    option.dataset.trip = 'true';
    option.textContent = `${trip.name} (${trip.time})`;
    tripSelect.append(option);
  });
  if (selected) tripSelect.value = selected;
}

function renderBoatOptions() {
  boatSelect.innerHTML = '';
  boats.forEach((boat) => {
    const option = document.createElement('option');
    option.value = boat.id;
    option.textContent = `${boat.name} (정원 ${boat.maxSeats}명)`;
    boatSelect.append(option);
  });
  selectedBoatId = boats[0]?.id || '';
  boatSelect.value = selectedBoatId;
}

function renderSlots(slots) {
  slotsContainer.innerHTML = '';
  slots.forEach((slot) => {
    const node = slotTemplate.content.cloneNode(true);
    node.querySelector('.slot-title').textContent = slot.name;
    node.querySelector('.slot-time').textContent = slot.time;
    node.querySelector('.seat-count').textContent = `잔여 좌석 ${slot.remaining}석 / 총 ${slot.maxSeats}석`;
    const state = node.querySelector('.seat-status');
    if (slot.remaining > 0) {
      state.textContent = '예약 가능';
      state.classList.add('ok');
    } else {
      state.textContent = '매진';
      state.classList.add('closed');
    }
    slotsContainer.append(node);
  });
}

function getDayStatus(summary) {
  if (!summary) return { text: '여유', className: 'ok' };
  if (summary.remaining <= 0) return { text: '매진', className: 'closed' };
  const ratio = summary.remaining / summary.capacity;
  if (ratio <= 0.25) return { text: '마감임박', className: 'warn' };
  return { text: '예약가능', className: 'ok' };
}

function renderCalendar() {
  monthLabel.textContent = `${currentMonth.getFullYear()}년 ${currentMonth.getMonth() + 1}월`;
  if (!calendarHead.hasChildNodes()) {
    WEEKDAYS.forEach((day) => {
      const span = document.createElement('span');
      span.textContent = day;
      calendarHead.append(span);
    });
  }
  calendarGrid.innerHTML = '';

  const firstDate = new Date(currentMonth.getFullYear(), currentMonth.getMonth(), 1);
  const lastDate = new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 0);
  const firstDayIndex = firstDate.getDay();

  for (let i = 0; i < firstDayIndex; i += 1) {
    const blank = document.createElement('div');
    blank.className = 'calendar-day calendar-day--empty';
    calendarGrid.append(blank);
  }

  for (let day = 1; day <= lastDate.getDate(); day += 1) {
    const iso = `${monthKey(currentMonth)}-${String(day).padStart(2, '0')}`;
    const boat = boats.find((item) => item.id === selectedBoatId);
    const capacity = (boat?.maxSeats || 0) * trips.length;
    const summary = calendarSummary[iso] || { reserved: 0, capacity, remaining: capacity };
    const status = getDayStatus(summary);

    const button = document.createElement('button');
    button.type = 'button';
    button.className = `calendar-day ${dateInput.value === iso ? 'calendar-day--selected' : ''}`;
    button.dataset.date = iso;
    button.innerHTML = `
      <div class="day-top">
        <span class="day-num">${day}</span>
        <span class="day-status ${status.className}">${status.text}</span>
      </div>
      <div class="day-meta">
        <div>정원 ${summary.capacity}명</div>
        <div>예약 ${summary.reserved}명 / 잔여 ${summary.remaining}명</div>
      </div>
    `;

    button.addEventListener('click', async () => {
      dateInput.value = iso;
      setMessage('');
      await loadAvailability();
      renderCalendar();
    });

    calendarGrid.append(button);
  }
}

async function fetchJSON(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.message || '요청 처리에 실패했습니다.');
  return data;
}

async function loadConfig() {
  const config = await fetchJSON('/api/config');
  trips = config.trips;
  boats = config.boats || [];
  if (config.siteName) document.title = `${config.siteName} | 실시간 바다낚시 예약`;
  renderTripOptions();
  renderBoatOptions();
}

async function loadAvailability() {
  const date = dateInput.value;
  const result = await fetchJSON(`/api/availability?date=${encodeURIComponent(date)}&boatId=${encodeURIComponent(selectedBoatId)}`);
  renderSlots(result.slots);
}

async function loadCalendarSummary() {
  const result = await fetchJSON(`/api/calendar?month=${encodeURIComponent(monthKey(currentMonth))}&boatId=${encodeURIComponent(selectedBoatId)}`);
  calendarSummary = result.days;
  renderCalendar();
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      await Promise.all([loadAvailability(), loadCalendarSummary()]);
    } catch (_) {
      // no-op
    }
  }, 5000);
}

async function reserveSeats(event) {
  event.preventDefault();
  const customerName = document.querySelector('#customerName').value.trim();
  const customerPhone = document.querySelector('#customerPhone').value.trim();
  const tripId = tripSelect.value;
  const guestCount = Number(document.querySelector('#guestCount').value);
  const bookingDate = dateInput.value;

  if (!customerName || !customerPhone || !tripId || guestCount < 1) {
    setMessage('필수 정보를 모두 입력해주세요.');
    return;
  }

  try {
    await fetchJSON('/api/bookings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bookingDate, boatId: selectedBoatId, tripId, customerName, customerPhone, guestCount }),
    });

    setMessage(`${customerName}님 예약이 완료되었습니다. (${guestCount}명)`, true);
    bookingForm.reset();
    tripSelect.value = '';
    document.querySelector('#guestCount').value = '1';
    await Promise.all([loadAvailability(), loadCalendarSummary()]);
  } catch (error) {
    setMessage(error.message);
  }
}

async function init() {
  dateInput.value = todayISO();
  currentMonth = new Date(`${dateInput.value}T00:00:00`);
  await loadConfig();
  await Promise.all([loadAvailability(), loadCalendarSummary()]);
  startPolling();
}

boatSelect.addEventListener('change', async () => {
  selectedBoatId = boatSelect.value;
  setMessage('');
  await Promise.all([loadAvailability(), loadCalendarSummary()]);
  startPolling();
});

prevMonthBtn.addEventListener('click', async () => {
  currentMonth = new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1, 1);
  await loadCalendarSummary();
});

nextMonthBtn.addEventListener('click', async () => {
  currentMonth = new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 1);
  await loadCalendarSummary();
});

dateInput.addEventListener('change', async () => {
  setMessage('');
  const selected = new Date(`${dateInput.value}T00:00:00`);
  if (selected.getFullYear() !== currentMonth.getFullYear() || selected.getMonth() !== currentMonth.getMonth()) {
    currentMonth = new Date(selected.getFullYear(), selected.getMonth(), 1);
    await loadCalendarSummary();
  }
  await loadAvailability();
  renderCalendar();
  startPolling();
});

bookingForm.addEventListener('submit', reserveSeats);

init().catch((error) => {
  console.error(error);
  setMessage('초기 데이터를 불러오지 못했습니다. 서버 실행 상태를 확인해주세요.');
});
