import { Observer } from "@ishubhamx/panchangam-js";

/**
 * Create an Observer for the panchangam-js library.
 * Observer(lat, lng, elevation_meters)
 */
export function createObserver(
  lat: number,
  lng: number,
  elevation: number = 0
): Observer {
  return new Observer(lat, lng, elevation);
}
