const tbody = document.getElementById('tbody');
const scanInfo = document.getElementById('scan-info');
const refreshBtn = document.getElementById('refresh');

function renderRows(rows) {
  tbody.innerHTML = '';
  rows.forEach(r => {
    const tr = document.createElement('tr');
    tr.className = 'hover:bg-slate-50/50';
    tr.innerHTML = `
      <td class="px-3 py-2 text-sm text-slate-700 font-medium">${r.roll}</td>
      <td class="px-3 py-2 text-sm text-slate-700">${r.name}</td>
      <td class="px-3 py-2 text-sm text-slate-700">${r.class}</td>
      <td class="px-3 py-2 text-sm text-slate-700">${r.date}</td>
      <td class="px-3 py-2 text-sm text-slate-700">${r.inTime}</td>
      <td class="px-3 py-2 text-sm text-slate-700">${r.outTime}</td>
      <td class="px-3 py-2 text-sm">
        <span class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${r.status === 'In Library' ? 'bg-emerald-50 text-emerald-700 ring-emerald-200' : 'bg-slate-50 text-slate-700 ring-slate-200'}">${r.status}</span>
      </td>`;
    tbody.appendChild(tr);
  });
}

async function loadAttendance() {
  try {
    const res = await fetch('/api/attendance');
    const data = await res.json();
    renderRows(data.attendance || []);
  } catch (e) {
    console.error('Failed to load attendance', e);
  }
}

function updateLastScan(barcode, action) {
  const now = new Date().toLocaleString();
  scanInfo.textContent = `${barcode} — ${action} @ ${now}`;
}

document.addEventListener('DOMContentLoaded', () => {
  loadAttendance();
  refreshBtn.addEventListener('click', loadAttendance);

  const socket = io();
  socket.on('connect', () => {
    console.log('Connected');
  });
  socket.on('barcode_scanned', (payload) => {
    const { barcode, record } = payload;
    updateLastScan(barcode, record?.action || 'Scanned');
    // refresh table quickly
    loadAttendance();
  });
});


