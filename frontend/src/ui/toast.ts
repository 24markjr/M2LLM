/**
 * Toasts (Phase U2): short confirmations after an action ("Investigation deleted"), and errors that
 * need no decision. The queue is a pure reducer so it is tested without a browser.
 */

export type ToastTone = "info" | "success" | "error";

export interface Toast {
  id: number;
  tone: ToastTone;
  message: string;
}

export type ToastAction =
  | { type: "add"; toast: Toast }
  | { type: "dismiss"; id: number };

/** At most this many at once; the oldest goes first. */
export const MAX_TOASTS = 4;

/** How long a toast stays, by tone. An error stays until dismissed. */
export const TOAST_MS: Record<ToastTone, number | null> = { info: 5000, success: 4000, error: null };

export function toastReducer(state: Toast[], action: ToastAction): Toast[] {
  switch (action.type) {
    case "add":
      return [...state, action.toast].slice(-MAX_TOASTS);
    case "dismiss":
      return state.filter((t) => t.id !== action.id);
  }
}
