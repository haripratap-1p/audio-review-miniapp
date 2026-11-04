// date and verdict text
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const FULL = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

export const fmtDate = (d) => `${Number(d.slice(8))} ${MONTHS[Number(d.slice(5, 7)) - 1]}`;
export const todayIst = () => new Date(Date.now() + 5.5 * 3600e3).toISOString().slice(0, 10);
// lists are ordered and grouped by when a recording reached us; the call time comes from the phone
export const arrDay = (i) => (i.arrived || "").slice(0, 10) || i.date;
export const arrTime = (i) => (i.arrived || "").slice(11, 16);
export const listWhen = (i) => (i.date === arrDay(i) ? i.time : `called ${fmtDate(i.date)}, ${i.time}`);
export const whenText = (i) => (i.date === arrDay(i) ? `${fmtDate(i.date)}, ${i.time}`
  : `Called ${fmtDate(i.date)}, ${i.time} · arrived ${fmtDate(arrDay(i))}, ${arrTime(i)}`);
export const dayLabel = (d) => (d === todayIst() ? "Today" : d === new Date(Date.now() + 5.5 * 3600e3 - 864e5).toISOString().slice(0, 10) ? "Yesterday" : fmtDate(d));
export const verdictText = (v) => (v === "ok" ? "Correct" : v === "bad" ? "Wrong" : "To review");
export const monthLabel = (ym) => `${FULL[Number(ym.slice(5, 7)) - 1]} ${ym.slice(0, 4)}`;
// one month, Monday first: null for the blanks before the 1st, then "YYYY-MM-DD" per day
export function monthGrid(ym) {
  const [y, m] = ym.split("-").map(Number);
  const lead = (new Date(Date.UTC(y, m - 1, 1)).getUTCDay() + 6) % 7, n = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return [...Array(lead).fill(null), ...Array.from({ length: n }, (_, i) => `${ym}-${String(i + 1).padStart(2, "0")}`)];
}
