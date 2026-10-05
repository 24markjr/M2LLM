/** Phase 38: the rules behind the New Mission document picker. */

import { describe, expect, it } from "vitest";

import type { FormatSpec } from "../api/types";
import { acceptAttribute, contextFileName, formatsLine, isSupported, sizeLabel } from "./documents";

const FORMATS: FormatSpec[] = [
  { kind: "word", extensions: [".docx"], parser: "python-docx", yields_text: true, becomes: "" },
  { kind: "spreadsheet", extensions: [".xlsx", ".xlsm"], parser: "openpyxl", yields_text: true, becomes: "" },
  { kind: "image", extensions: [".png", ".jpg"], parser: "pillow", yields_text: false, becomes: "" },
];

describe("the document picker", () => {
  it("offers exactly the engine's extensions", () => {
    expect(acceptAttribute(FORMATS)).toBe(".docx,.xlsx,.xlsm,.png,.jpg");
    expect(isSupported("Budget.XLSX", FORMATS)).toBe(true);
    expect(isSupported("tool.exe", FORMATS)).toBe(false);
    expect(isSupported("README", FORMATS)).toBe(false);
  });

  it("names typed context safely and never overwrites an earlier one", () => {
    expect(contextFileName("Witness notes, day 2!", [])).toBe("Witness-notes-day-2.txt");
    expect(contextFileName("", [])).toBe("context.txt");
    expect(contextFileName("context.txt", ["context.txt", "context-2.txt"])).toBe("context-3.txt");
    expect(contextFileName("../../etc/passwd", [])).toBe("etc-passwd.txt");
  });

  it("says what it reads and how big a file is", () => {
    expect(formatsLine(FORMATS)).toBe("word (.docx) · spreadsheet (.xlsx, .xlsm) · image (.png, .jpg)");
    expect(sizeLabel(900)).toBe("900 B");
    expect(sizeLabel(2048)).toBe("2.0 kB");
    expect(sizeLabel(5 * 1024 * 1024)).toBe("5.0 MB");
  });
});
