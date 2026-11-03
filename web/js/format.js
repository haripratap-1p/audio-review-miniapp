// date and verdict text
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

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
