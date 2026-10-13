/**
 * The component library (Phase U2). Small, accessible, themed only through tokens (ui.css).
 * Every new screen from U3 is built from these; the old pages are replaced one by one.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useReducer,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type KeyboardEvent,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

import { IconAlert, IconCheck, IconClose, IconInfo } from "./icons";
import { STATUS, type Status } from "./status";
import { nextTab } from "./tabs";
import { TOAST_MS, toastReducer, type ToastTone } from "./toast";

// --- buttons ---------------------------------------------------------------------------------------

type Variant = "primary" | "secondary" | "ghost" | "danger";

export function Button({
  variant = "secondary",
  size = "md",
  icon,
  busy = false,
  children,
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: "sm" | "md";
  icon?: ReactNode;
  busy?: boolean;
}) {
  return (
    <button
      type="button"
      {...rest}
      className={`ui-button ${variant} ${size} ${className}`.trim()}
      disabled={rest.disabled || busy}
      aria-busy={busy || undefined}
    >
      {busy ? <span className="ui-spinner" aria-hidden="true" /> : icon}
      {children ? <span>{children}</span> : null}
    </button>
  );
}

// --- form fields -----------------------------------------------------------------------------------

function Field({
  label,
  hint,
  error,
  id,
  children,
}: {
  label: string;
  hint?: string | undefined;
  error?: string | undefined;
  id: string;
  children: ReactNode;
}) {
  return (
    <div className={`ui-field ${error ? "invalid" : ""}`}>
      <label htmlFor={id}>{label}</label>
      {children}
      {error ? (
        <div className="ui-field-error" id={`${id}-msg`} role="alert">
          {error}
        </div>
      ) : hint ? (
        <div className="ui-field-hint" id={`${id}-msg`}>
          {hint}
        </div>
      ) : null}
    </div>
  );
}

type FieldProps = { label: string; hint?: string | undefined; error?: string | undefined };

export function TextInput({ label, hint, error, ...rest }: FieldProps & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return (
    <Field label={label} hint={hint} error={error} id={id}>
      <input id={id} aria-invalid={!!error || undefined} aria-describedby={hint || error ? `${id}-msg` : undefined} {...rest} />
    </Field>
  );
}

export function TextArea({ label, hint, error, ...rest }: FieldProps & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const id = useId();
  return (
    <Field label={label} hint={hint} error={error} id={id}>
      <textarea id={id} aria-invalid={!!error || undefined} aria-describedby={hint || error ? `${id}-msg` : undefined} {...rest} />
    </Field>
  );
}

export function Select({
  label,
  hint,
  error,
  options,
  ...rest
}: FieldProps & SelectHTMLAttributes<HTMLSelectElement> & { options: { value: string; label: string }[] }) {
  const id = useId();
  return (
    <Field label={label} hint={hint} error={error} id={id}>
      <select id={id} aria-invalid={!!error || undefined} {...rest}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </Field>
  );
}

// --- cards -----------------------------------------------------------------------------------------

export function Card({
  title,
  meta,
  actions,
  children,
  flush = false,
}: {
  title?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  flush?: boolean;
}) {
  return (
    <section className="ui-card">
      {title || actions ? (
        <header className="ui-card-head">
          <div className="ui-card-title">
            {title ? <h3>{title}</h3> : null}
            {meta ? <span className="ui-card-meta">{meta}</span> : null}
          </div>
          {actions ? <div className="ui-card-actions">{actions}</div> : null}
        </header>
      ) : null}
      <div className={flush ? "ui-card-body flush" : "ui-card-body"}>{children}</div>
    </section>
  );
}

// --- badges and status marks -----------------------------------------------------------------------

export type Tone = "neutral" | "accent" | "verified" | "inferred" | "unsupported" | "unknown" | "sensitive";

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`ui-badge ${tone}`}>{children}</span>;
}

/** A status badge: glyph and word, in the status colour. */
export function StatusBadge({ status }: { status: Status }) {
  const meta = STATUS[status];
  return (
    <span className={`ui-badge ${status}`} title={meta.description}>
      <span aria-hidden="true">{meta.glyph}</span> {meta.label}
    </span>
  );
}

/** The status underline: text marked with its status. The word is read out and shown on hover. */
export function StatusMark({ status, children }: { status: Status; children: ReactNode }) {
  const meta = STATUS[status];
  return (
    <span className={`ui-mark ${status}`} title={`${meta.label}: ${meta.description}`}>
      {children}
      <span className="ui-sr">({meta.label})</span>
    </span>
  );
}

// --- tables ----------------------------------------------------------------------------------------

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  align?: "left" | "right";
  /** Shown in the stacked layout on narrow screens; defaults to `header`. */
  label?: string;
  /** Short values (dates, counts, ids) stay on one line; the long column takes the rest (U5). */
  nowrap?: boolean;
}

/**
 * A table that never scrolls the page sideways: cells wrap, and below 720px each row becomes a
 * stacked card with every value labelled.
 */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  empty = "Nothing here yet.",
  caption,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  empty?: ReactNode;
  caption?: string;
}) {
  if (rows.length === 0) return <div className="ui-empty">{empty}</div>;
  return (
    <table className="ui-table">
      {caption ? <caption className="ui-sr">{caption}</caption> : null}
      <thead>
        <tr>
          {columns.map((c) => (
            <th key={c.key} className={cellClass(c)} scope="col">
              {c.header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={rowKey(row)}>
            {columns.map((c) => (
              <td key={c.key} data-label={c.label ?? c.header} className={cellClass(c)}>
                {c.render(row)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function cellClass<T>(c: Column<T>): string | undefined {
  const names = [c.align === "right" ? "num" : "", c.nowrap ? "nowrap" : ""].filter(Boolean).join(" ");
  return names || undefined;
}

// --- tabs ------------------------------------------------------------------------------------------

export function Tabs({
  tabs,
  active,
  onChange,
  label,
}: {
  tabs: { id: string; label: ReactNode }[];
  active: string;
  onChange: (id: string) => void;
  label: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const index = Math.max(
    0,
    tabs.findIndex((t) => t.id === active),
  );
  const onKey = (e: KeyboardEvent) => {
    const next = nextTab(e.key, index, tabs.length);
    if (next === null) return;
    const target = tabs[next];
    if (!target) return;
    e.preventDefault();
    onChange(target.id);
    refs.current[next]?.focus();
  };
  return (
    <div className="ui-tabs" role="tablist" aria-label={label} onKeyDown={onKey}>
      {tabs.map((t, i) => (
        <button
          key={t.id}
          ref={(el) => {
            refs.current[i] = el;
          }}
          type="button"
          role="tab"
          id={`tab-${t.id}`}
          aria-selected={t.id === active}
          aria-controls={`panel-${t.id}`}
          tabIndex={t.id === active ? 0 : -1}
          className={t.id === active ? "on" : ""}
          onClick={() => onChange(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function TabPanel({ id, children }: { id: string; children: ReactNode }) {
  return (
    <div role="tabpanel" id={`panel-${id}`} aria-labelledby={`tab-${id}`} className="ui-tabpanel">
      {children}
    </div>
  );
}

// --- dialogs ---------------------------------------------------------------------------------------

/** A modal dialog on the native <dialog> element: focus is trapped, Escape closes it. */
export function Dialog({
  open,
  title,
  onClose,
  children,
  footer,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal?.();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      className="ui-dialog"
      aria-labelledby="ui-dialog-title"
      onClose={onClose}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
    >
      <header className="ui-dialog-head">
        <h2 id="ui-dialog-title">{title}</h2>
        <button type="button" className="icon-button" aria-label="Close" onClick={onClose}>
          <IconClose />
        </button>
      </header>
      <div className="ui-dialog-body">{children}</div>
      {footer ? <footer className="ui-dialog-foot">{footer}</footer> : null}
    </dialog>
  );
}

/**
 * Asks before something that cannot be undone. With `typeToConfirm`, the confirm button is enabled
 * only once that word is typed - used for deleting everything.
 */
export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  danger = true,
  typeToConfirm,
  busy = false,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  body: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  typeToConfirm?: string | undefined;
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const [typed, setTyped] = useState("");
  useEffect(() => {
    if (!open) setTyped("");
  }, [open]);
  const ready = !typeToConfirm || typed.trim().toLowerCase() === typeToConfirm.toLowerCase();
  return (
    <Dialog
      open={open}
      title={title}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant={danger ? "danger" : "primary"} disabled={!ready} busy={busy} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="ui-confirm-body">{body}</div>
      {typeToConfirm ? (
        <TextInput
          label={`Type "${typeToConfirm}" to confirm`}
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          autoComplete="off"
        />
      ) : null}
    </Dialog>
  );
}

// --- notices and toasts ----------------------------------------------------------------------------

export function Notice({ tone = "info", children }: { tone?: ToastTone | "warning"; children: ReactNode }) {
  const Icon = tone === "success" ? IconCheck : tone === "info" ? IconInfo : IconAlert;
  return (
    <div className={`ui-notice ${tone}`} role={tone === "error" ? "alert" : "status"}>
      <Icon size={16} />
      <div>{children}</div>
    </div>
  );
}

type Notify = (message: string, tone?: ToastTone) => void;
const ToastContext = createContext<Notify>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, dispatch] = useReducer(toastReducer, []);
  const counter = useRef(0);
  const notify = useCallback<Notify>((message, tone = "info") => {
    const id = ++counter.current;
    dispatch({ type: "add", toast: { id, tone, message } });
    const ms = TOAST_MS[tone];
    if (ms !== null) window.setTimeout(() => dispatch({ type: "dismiss", id }), ms);
  }, []);
  return (
    <ToastContext.Provider value={notify}>
      {children}
      <div className="ui-toasts" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`ui-toast ${t.tone}`} role={t.tone === "error" ? "alert" : "status"}>
            <span>{t.message}</span>
            <button
              type="button"
              className="icon-button"
              aria-label="Dismiss"
              onClick={() => dispatch({ type: "dismiss", id: t.id })}
            >
              <IconClose size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): Notify {
  return useContext(ToastContext);
}
