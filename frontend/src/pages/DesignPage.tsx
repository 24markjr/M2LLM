/**
 * The design system on one page (Phase U2): every token and component in the current theme, so a
 * change to either is reviewed where it is seen. Reached from Settings.
 */

import { useState } from "react";

import { useTheme } from "../theme/ThemeProvider";
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  DataTable,
  Dialog,
  Notice,
  Select,
  StatusBadge,
  StatusMark,
  TabPanel,
  Tabs,
  TextArea,
  TextInput,
  useToast,
  type Column,
} from "../ui/components";
import { IconPin, IconPlus, IconSearch, IconTrash } from "../ui/icons";

const SWATCHES = [
  "surface-page",
  "surface",
  "surface-sunken",
  "border",
  "text",
  "text-muted",
  "accent",
  "verified",
  "inferred",
  "unsupported",
  "unknown",
  "sensitive",
];

interface Row {
  id: string;
  question: string;
  status: "verified" | "inferred" | "unsupported" | "unknown";
  findings: number;
}

const ROWS: Row[] = [
  { id: "run_1", question: "Does the Helix spend exceed its approved budget?", status: "verified", findings: 2 },
  { id: "run_2", question: "When did shipment 4821 actually arrive at the warehouse in Pune?", status: "inferred", findings: 1 },
  { id: "run_3", question: "Do these server logs show a compromise?", status: "unknown", findings: 0 },
];

const COLUMNS: Column<Row>[] = [
  { key: "q", header: "Question", render: (r) => r.question },
  { key: "s", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
  { key: "f", header: "Findings", align: "right", render: (r) => r.findings },
];

export function DesignPage() {
  const { theme, setTheme } = useTheme();
  const notify = useToast();
  const [tab, setTab] = useState("answer");
  const [dialog, setDialog] = useState(false);
  const [confirm, setConfirm] = useState(false);

  return (
    <div className="design-page">
      <Card
        title="Design system"
        meta={`${theme} theme`}
        actions={
          <Button size="sm" onClick={() => setTheme(theme === "light" ? "dark" : "light")}>
            Switch to {theme === "light" ? "dark" : "light"}
          </Button>
        }
      >
        <p className="design-lead">
          Light is the default; dark is chosen in Settings. Every colour below is a token from{" "}
          <code>theme/tokens.css</code>; a meaning colour always comes with a glyph and a word.
        </p>
        <div className="design-swatches">
          {SWATCHES.map((name) => (
            <div key={name} className="design-swatch">
              <span style={{ background: `var(--${name})` }} />
              <code>--{name}</code>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Type">
        <div className="design-type">
          <div style={{ fontSize: "var(--text-2xl)", fontWeight: 600 }}>What do you need to find out?</div>
          <div style={{ fontSize: "var(--text-xl)", fontWeight: 600 }}>Investigation journal</div>
          <div style={{ fontSize: "var(--text-lg)" }}>Body large - a summary paragraph.</div>
          <div>Body - the default size for reading.</div>
          <div style={{ fontSize: "var(--text-sm)", color: "var(--text-muted)" }}>Small, muted - metadata.</div>
          <code>ledger.xlsx:Sheet1:r12 - evidence lines in the monospace face</code>
        </div>
      </Card>

      <Card title="Buttons">
        <div className="design-row">
          <Button variant="primary" icon={<IconPlus size={16} />}>
            New investigation
          </Button>
          <Button>Secondary</Button>
          <Button variant="ghost" icon={<IconSearch size={16} />}>
            Search
          </Button>
          <Button variant="danger" icon={<IconTrash size={16} />}>
            Delete
          </Button>
          <Button busy>Running</Button>
          <Button disabled>Disabled</Button>
          <Button size="sm" icon={<IconPin size={14} />}>
            Pin
          </Button>
        </div>
      </Card>

      <Card title="Fields">
        <div className="design-grid">
          <TextInput label="Case title" placeholder="e.g. Helix budget overrun" hint="3 to 200 characters." />
          <Select
            label="Sensitivity"
            options={[
              { value: "INTERNAL", label: "Internal" },
              { value: "CONFIDENTIAL", label: "Confidential" },
            ]}
          />
          <TextInput label="With an error" defaultValue="ab" error="At least 3 characters." />
          <TextArea label="Background" rows={3} placeholder="Optional" />
        </div>
      </Card>

      <Card title="Status: badges and the underline">
        <div className="design-row">
          <StatusBadge status="verified" />
          <StatusBadge status="inferred" />
          <StatusBadge status="unsupported" />
          <StatusBadge status="unknown" />
          <Badge>Neutral</Badge>
          <Badge tone="accent">Investigating</Badge>
          <Badge tone="sensitive">Confidential</Badge>
        </div>
        <p className="design-answer">
          <StatusMark status="verified">The ledger records spend of 287,500 against an approved 250,000.</StatusMark>{" "}
          <StatusMark status="inferred">The overrun probably began in the third quarter.</StatusMark>{" "}
          <StatusMark status="unsupported">The vendor was paid twice.</StatusMark>{" "}
          <StatusMark status="unknown">Whether the board was told is not in these documents.</StatusMark>
        </p>
      </Card>

      <Card title="Table" meta="wraps; stacked on narrow screens" flush>
        <DataTable columns={COLUMNS} rows={ROWS} rowKey={(r) => r.id} caption="Example investigations" />
      </Card>

      <Card title="Tabs">
        <Tabs
          label="Evidence board"
          active={tab}
          onChange={setTab}
          tabs={[
            { id: "answer", label: "Answer" },
            { id: "sources", label: "Sources" },
            { id: "timeline", label: "Timeline" },
            { id: "report", label: "Report" },
          ]}
        />
        <TabPanel id={tab}>
          <p>The {tab} tab. Arrow keys move between tabs; Home and End jump.</p>
        </TabPanel>
      </Card>

      <Card title="Dialogs, notices, toasts">
        <div className="design-row">
          <Button onClick={() => setDialog(true)}>Open a dialog</Button>
          <Button variant="danger" onClick={() => setConfirm(true)}>
            Delete all history
          </Button>
          <Button onClick={() => notify("Investigation deleted.", "success")}>Success toast</Button>
          <Button onClick={() => notify("Could not reach the engine.", "error")}>Error toast</Button>
        </div>
        <Notice tone="info">Investigations are kept after a restart.</Notice>
        <Notice tone="warning">The audit log is in memory: the database was not reachable.</Notice>
        <Notice tone="error">The stored original is missing.</Notice>
        <Notice tone="success">Report exported and recorded in custody.</Notice>
      </Card>

      <Dialog
        open={dialog}
        title="A dialog"
        onClose={() => setDialog(false)}
        footer={<Button variant="primary" onClick={() => setDialog(false)}>Done</Button>}
      >
        Focus stays inside until it closes; Escape closes it.
      </Dialog>
      <ConfirmDialog
        open={confirm}
        title="Delete all history?"
        body="Every finished investigation and its recordings will be removed. The chain of custody, review decisions and the audit log are kept."
        confirmLabel="Delete everything"
        typeToConfirm="delete"
        onConfirm={() => {
          setConfirm(false);
          notify("Nothing was deleted: this is the design page.", "info");
        }}
        onClose={() => setConfirm(false)}
      />
    </div>
  );
}
