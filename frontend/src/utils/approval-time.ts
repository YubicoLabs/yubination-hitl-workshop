import { parseUTCDate } from './date';

/** Absolute timestamp is always local, with seconds and an explicit time zone. */
export function approvalTimestamp(value: string): string {
  const date = parseUTCDate(value);
  if (!value || !Number.isFinite(date.getTime())) return 'Time unavailable';
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZoneName: 'short',
  });
}

export function approvalDeadline(
  value: string,
  status: string,
  now = Date.now()
): string {
  const deadline = parseUTCDate(value).getTime();
  if (!value || !Number.isFinite(deadline)) return 'Deadline unavailable';
  const absolute = approvalTimestamp(value);
  if (status !== 'pending') return `Approval deadline: ${absolute}`;
  const seconds = Math.ceil((deadline - now) / 1000);
  if (seconds <= 0) return `Approval window ended · ${absolute}`;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor(seconds / 60) % 60;
  const duration = `${hours ? `${hours}h ` : ''}${minutes}m ${seconds % 60}s`;
  return `Expires in ${duration} · ${absolute}`;
}

/** A historical late decision is evidence of a defect, not a valid fresh authorization. */
export function approvalWasLate(
  deadline: string | null,
  resolved: string | null,
  status = 'approved'
): boolean {
  return Boolean(
    status === 'approved' &&
    deadline &&
    resolved &&
    parseUTCDate(resolved).getTime() >= parseUTCDate(deadline).getTime()
  );
}
