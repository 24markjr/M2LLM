/**
 * Settings: my account, and - for an admin - the people in my organisation (v4 Phase 1a), and -
 * for the operator's admins - the customer organisations (v4 Phase 1c).
 * The server enforces every rule shown here; the page only explains them.
 */

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { api, ApiError, type Organisation, type Role, type User } from "../api/client";
import { useUser } from "../auth/AuthGate";
import { Badge, Button, Notice, useToast } from "../ui/components";

const ROLES: { id: Role; label: string; can: string }[] = [
  { id: "viewer", label: "Viewer", can: "reads everything, changes nothing" },
  { id: "reviewer", label: "Reviewer", can: "a viewer who reviews and challenges findings" },
  { id: "analyst", label: "Analyst", can: "runs investigations, files evidence, manages cases" },
  { id: "admin", label: "Admin", can: "everything, including people and deleting everything" },
];

function message(exc: unknown): string {
  return exc instanceof ApiError ? exc.message : "Something went wrong.";
}

export function AccountCard() {
  const { user, signOut } = useUser();
  const notify = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);

  if (!user) return null;

  const change = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.changePassword(current, next);
      notify("Password changed. Other sessions were signed out.", "success");
      setCurrent("");
      setNext("");
    } catch (exc) {
      notify(message(exc), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="settings-card" aria-labelledby="s-account">
      <h2 id="s-account">Your account</h2>
      <dl className="settings-facts">
        <dt>Signed in as</dt>
        <dd>
          {user.name ? `${user.name} · ` : ""}
          <span className="mono">{user.email}</span>
        </dd>
        <dt>Role</dt>
        <dd>
          <Badge tone="accent">{user.role}</Badge> {ROLES.find((r) => r.id === user.role)?.can}
        </dd>
      </dl>
      <form className="settings-row" onSubmit={(e) => void change(e)}>
        <input type="password" placeholder="Current password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
        <input type="password" placeholder="New password (12+, mixed case, a digit)" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} required />
        <Button size="sm" type="submit" disabled={busy}>
          Change password
        </Button>
        <Button size="sm" variant="ghost" type="button" onClick={signOut}>
          Sign out
        </Button>
      </form>
    </section>
  );
}

export function PeopleCard() {
  const { user } = useUser();
  const notify = useToast();
  const [people, setPeople] = useState<User[]>([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState({ email: "", name: "", role: "analyst" as Role, password: "" });

  const load = useCallback(() => {
    api
      .listUsers()
      .then(setPeople)
      .catch((exc: unknown) => setError(message(exc)));
  }, []);
  useEffect(() => {
    if (user?.role === "admin") load();
  }, [user, load]);

  if (user?.role !== "admin") return null;

  const add = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api.createUser(form);
      notify(`${form.email} can now sign in.`, "success");
      setForm({ email: "", name: "", role: "analyst", password: "" });
      load();
    } catch (exc) {
      notify(message(exc), "error");
    }
  };

  const change = async (person: User, body: { role?: Role; active?: boolean }) => {
    try {
      await api.updateUser(person.user_id, body);
      notify(`${person.email} updated; their sessions were signed out.`, "success");
      load();
    } catch (exc) {
      notify(message(exc), "error");
    }
  };

  return (
    <section className="settings-card" aria-labelledby="s-people">
      <h2 id="s-people">People</h2>
      <p className="settings-note">
        Everyone in your organisation. {ROLES.map((r) => `${r.label}: ${r.can}`).join(". ")}.
      </p>
      {error ? <Notice tone="error">{error}</Notice> : null}
      <table className="settings-people">
        <thead>
          <tr>
            <th>Person</th>
            <th>Role</th>
            <th>Last signed in</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {people.map((p) => (
            <tr key={p.user_id} className={p.active ? "" : "inactive"}>
              <td>
                {p.name || p.email}
                <div className="settings-note mono">{p.email}</div>
              </td>
              <td>
                <select value={p.role} disabled={p.user_id === user.user_id} onChange={(e) => void change(p, { role: e.target.value as Role })} aria-label={`Role of ${p.email}`}>
                  {ROLES.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </td>
              <td>{p.last_login_at ? new Date(p.last_login_at).toLocaleString() : "never"}</td>
              <td>
                {p.user_id === user.user_id ? (
                  <span className="settings-note">you</span>
                ) : (
                  <Button size="sm" variant="ghost" onClick={() => void change(p, { active: !p.active })}>
                    {p.active ? "Deactivate" : "Reactivate"}
                  </Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <form className="settings-row settings-add" onSubmit={(e) => void add(e)}>
        <input type="email" placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
        <input placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })} aria-label="Role">
          {ROLES.map((r) => (
            <option key={r.id} value={r.id}>
              {r.label}
            </option>
          ))}
        </select>
        <input type="password" placeholder="First password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
        <Button size="sm" type="submit">
          Add person
        </Button>
      </form>
    </section>
  );
}

/** The operator's admins create customers: an organisation and its first admin, who then adds
 * their own people. Each organisation sees only its own investigations, cases and evidence. */
export function OrganisationsCard() {
  const { user } = useUser();
  const notify = useToast();
  const [orgs, setOrgs] = useState<Organisation[]>([]);
  const [error, setError] = useState("");
  const blank = { org_id: "", email: "", name: "", password: "" };
  const [form, setForm] = useState(blank);
  const operator = user?.role === "admin" && user.org_id === "default";

  const load = useCallback(() => {
    api
      .listOrganisations()
      .then(setOrgs)
      .catch((exc: unknown) => setError(message(exc)));
  }, []);
  useEffect(() => {
    if (operator) load();
  }, [operator, load]);

  if (!operator) return null;

  const add = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api.createOrganisation({
        org_id: form.org_id,
        admin: { email: form.email, name: form.name, password: form.password },
      });
      notify(`${form.org_id} created; ${form.email} can sign in as its admin.`, "success");
      setForm(blank);
      load();
    } catch (exc) {
      notify(message(exc), "error");
    }
  };

  return (
    <section className="settings-card" aria-labelledby="s-orgs">
      <h2 id="s-orgs">Organisations</h2>
      <p className="settings-note">
        Each customer organisation sees only its own investigations, cases, evidence, memory and audit log. Yours is{" "}
        <span className="mono">default</span>.
      </p>
      {error ? <Notice tone="error">{error}</Notice> : null}
      <table className="settings-people">
        <thead>
          <tr>
            <th>Organisation</th>
            <th>Accounts</th>
            <th>Admins</th>
          </tr>
        </thead>
        <tbody>
          {orgs.map((o) => (
            <tr key={o.org_id}>
              <td className="mono">{o.org_id}</td>
              <td>{o.accounts}</td>
              <td className="mono">{o.admins.join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <form className="settings-row settings-add" onSubmit={(e) => void add(e)}>
        <input placeholder="Organisation id (e.g. acme-bank)" pattern="[a-z0-9][a-z0-9-]{1,47}" title="lower-case letters, digits and hyphens" value={form.org_id} onChange={(e) => setForm({ ...form, org_id: e.target.value })} required />
        <input type="email" placeholder="Their admin's email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required />
        <input placeholder="Admin's name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input type="password" placeholder="First password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required />
        <Button size="sm" type="submit">
          Create organisation
        </Button>
      </form>
    </section>
  );
}
