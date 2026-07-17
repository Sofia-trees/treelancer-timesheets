export const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

export const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function daysInMonth(year, month /* 1-12 */) {
  return new Date(year, month, 0).getDate();
}

// 0=Mon .. 6=Sun for a given day of a month.
export function weekdayIdx(year, month, day) {
  return (new Date(year, month - 1, day).getDay() + 6) % 7;
}

export function isWeekend(year, month, day) {
  return weekdayIdx(year, month, day) >= 5;
}

export function periodLabel(iso /* YYYY-MM-DD */) {
  const [y, m] = iso.split("-");
  return `${MONTHS[Number(m) - 1]} ${y}`;
}

export function statusLabel(s) {
  return {
    draft: "Draft",
    submitted: "Submitted",
    manager_approved: "Manager approved",
    approved: "Approved",
    rejected: "Rejected",
  }[s] || s;
}

export function num(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}
