import * as Location from 'expo-location';
import * as TaskManager from 'expo-task-manager';

import { get } from '@/demo-data';

export const TRACKING_TASK = 'finexa-work-location';
const EVERY_MS = 15 * 60 * 1000; // one reading about every 15 minutes

export type Point = { lat: number; lon: number };
export type Reading = Point & { time: string };
export type Schedule = { days: number[]; start: string; end: string }; // days 0 = Sunday, times "09:00"
export type WorkSettings = { workplace: Point | null; radius_m: number; schedule: Schedule; remote: boolean };

const minutes = (hhmm: string) => {
  const [h, m] = hhmm.split(':').map(Number);
  return h * 60 + m;
};

export function inWorkHours(date: Date, s: Schedule) {
  const day = date.getDay(); // 0 = Sunday, like the schedule
  const now = date.getHours() * 60 + date.getMinutes();
  const start = minutes(s.start);
  const end = minutes(s.end);
  if (start < end) return s.days.includes(day) && now >= start && now < end;
  return (s.days.includes(day) && now >= start) || (s.days.includes((day + 6) % 7) && now < end); // night shift
}

export const toReading = (l: Location.LocationObject): Reading => ({
  lat: l.coords.latitude,
  lon: l.coords.longitude,
  time: new Date(l.timestamp).toISOString(),
});

export const post = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export async function sendReadings(readings: Reading[]) {
  const { schedule } = await get<WorkSettings>('/workplace');
  const atWork = readings.filter((r) => inWorkHours(new Date(r.time), schedule));
  if (!atWork.length) return 0;
  return (await get<{ saved: number }>('/locations', post({ readings: atWork }))).saved;
}

TaskManager.defineTask<{ locations: Location.LocationObject[] }>(TRACKING_TASK, async ({ data, error }) => {
  if (error || !data?.locations?.length) return;
  await sendReadings(data.locations.map(toReading)).catch(() => {});
});

export const isTracking = () => Location.hasStartedLocationUpdatesAsync(TRACKING_TASK);

export async function startTracking() {
  if (!(await Location.requestForegroundPermissionsAsync()).granted) {
    throw new Error('Location permission was not given.');
  }
  if (!(await Location.requestBackgroundPermissionsAsync()).granted) {
    throw new Error('In Settings, choose "Allow all the time" for Finexa\'s location, then try again.');
  }
  await Location.startLocationUpdatesAsync(TRACKING_TASK, {
    accuracy: Location.Accuracy.Balanced,
    timeInterval: EVERY_MS,
    deferredUpdatesInterval: EVERY_MS,
    distanceInterval: 0,
    foregroundService: {
      notificationTitle: 'Finexa work check',
      notificationBody: 'Your location is sent to Finexa only during your work hours.',
    },
  });
}

export async function stopTracking() {
  if (await isTracking()) await Location.stopLocationUpdatesAsync(TRACKING_TASK);
}
