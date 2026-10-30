# JARVIS – demo runbook

A 7–8 minute live demonstration for a mixed panel (iDEX, defence and government buyers, investors,
academic reviewers). Everything runs on this laptop. Wi-Fi can be off.

The case is **Project VAJRA**: synthetic, and every file says so. It's a supply of 40 thermal
imaging sights at ₹10,50,000 each (₹4.2 crore), due by 15 March 2026, payable only after joint
inspection and only for accepted units. Planted in the six files:
- The invoice bills all 40 units and claims delivery on 14 March.
- The inspection received them on 28 March and accepted only 36.
- The full ₹4.2 crore was paid on 25 March, before the inspection report of 2 April.
- The Hindi committee minutes approved ₹3,78,00,000 for 36 units.
- A recorded supplier call says "28th of March… don't mention the delay on the invoice".

---

## The night before (30 min)

1. **Docker Desktop:** Settings → General → tick *Start Docker Desktop when you sign in*.
2. **Ollama:** keep the model loaded for the whole talk. In PowerShell:
   `setx OLLAMA_KEEP_ALIVE 4h`, then restart Ollama from the tray.
3. **Pre-run the showcase cases** (each takes 3–4 min):
   ```
   backend/.venv/Scripts/python scripts/demo/run_demo_case.py vajra
   backend/.venv/Scripts/python scripts/demo/run_demo_case.py clean
   ```
   Open the printed link for each. Pick the VAJRA run you like best and bookmark it as **DEMO 1**. Its case page is **DEMO 2**.
4. Leave DEMO 2's conversation empty: step 6 asks its questions live, honesty question first.
5. Take screenshots of every screen in the script into `docs/demo/screens/`. These are your fallback.
6. Charge the laptop and close everything heavy (games, video calls). The GPU is the bottleneck.

## 15 minutes before

1. Start, in this order: Docker Desktop → Ollama → backend → console.
   - Backend, from the project folder:
     `backend/.venv/Scripts/python -m uvicorn app.api.app:create_app --factory --port 8000 --app-dir backend`
   - Console:
     `cd frontend; npm run dev`
2. Run the pre-flight check:
   ```
   backend/.venv/Scripts/python scripts/demo/preflight.py
   ```
   It must say **GO**. It also warms the model. If a line says FIX, do what it says.
3. Open the console at http://localhost:5173 and sign in. Keep these tabs open:
   - DEMO 1 (the investigation)
   - DEMO 2 (the case)
   - Home
4. Light theme, browser zoom 110–125%, full screen (F11).

---

## The script (about 7–8 minutes)

**1. The problem (30 s, no clicks).**
> "Auditors and vigilance officers spend weeks reading files to find what doesn't add up. ChatGPT can read files, but it answers fluently even when it's wrong, and in audit one invented figure destroys the report. JARVIS is an AI investigator that has to prove every claim."

**2. Ask (45 s).** On **Home**:
- Show the six files: PDF order, scanned invoice, Word inspection report, Excel ledger, Hindi minutes, audio call.
- Point at the sensitivity selector: "Restricted: nothing leaves this machine."
- If you have time, actually press Start on a copy of the case and let it run in the background. Then switch to DEMO 1:
> "This is the one I ran before the session. It takes about three minutes on this laptop's GPU; on a cloud GPU, under a minute."

**3. The proof card (45 s).** On DEMO 1, top of the page:
> "Before any answer: N claims checked, N verified, N caught, six files fingerprinted with SHA-256, one read in Hindi. No ordinary AI shows you this."

**4. A finding, proved (1 min).**
- Open the overpayment finding: ₹4,20,00,000 paid, but only 36 of 40 accepted.
- Click its citation. The evidence board opens the **exact line** of the ledger, highlighted.
> "Every claim points at the line it rests on. Click, and you see it."

**5. It catches its own mistakes (45 s).** If your run has a **CONTRADICTED** finding (a false date order), show it:
> "Here the AI wrote that payment came *after* the inspection. The dates say the opposite. JARVIS checked the order of the dates by code, not by trusting the model, and rejected its own claim."

If your run has no such finding, skip this step and say it in one line.

**6. Honesty first, then a follow-up (2 min).** On DEMO 2 → *Ask about this case*.

Ask this first; the small model answers it reliably only before other questions:
> What is the amount of the performance bank guarantee the supplier furnished, and when does it expire?

About 5 s. "The documents do not mention a performance bank guarantee…"
> "It doesn't invent a number. It tells you what's missing."

Then:
- Type:
  > How much was the supplier paid, how many units did the joint inspection accept, and what is the overpayment against the value of the accepted units?

  About 15 s. Three verified sentences, ending in **₹42,00,000 overpaid**, with the arithmetic cited to both source lines.
- Then click the language button (**अ/A**, top right) → **हिन्दी**. The menu and panel switch to Hindi. Type:
  > आपूर्तिकर्ता को कितना भुगतान किया गया और संयुक्त निरीक्षण में कितनी इकाइयाँ स्वीकार की गईं?

  About 10 s. You see "read in English as…", the verified English answer, then the Hindi translation, labelled. Click **सुनें** (Read aloud).

**7. Human in the loop and the report (1 min).** On DEMO 1:
- **Approve** the overpayment finding (a reviewer's decision, recorded in the audit log).
- **Build the report** → **Open the report**. Show:
  - the executive brief;
  - the findings table;
  - the contradiction with both quotes side by side;
  - Appendix: file hashes and the **receipt hash**.
> "Tamper-evident: change one byte of any file and the hash no longer matches."

Optionally choose **हिन्दी → Open in Hindi** for the same report in Hindi.

**8. Close (30 s).**
> "It runs entirely on this laptop. I can turn the Wi-Fi off and it still works. Thirteen Indian languages. About ₹3 of compute per investigation. Ordinary AI answers; JARVIS proves."

---

## Likely questions, short answers

- **"Why not just use ChatGPT?"** It can't show you which line proves each claim, it fills gaps by guessing, and your files go to a foreign cloud. JARVIS verifies each claim against its cited line with a separate verifier, checks figures and date order by code, and runs on your own server.
- **"How accurate is it?"** On our 21-case benchmark: 0 invented figures, 0 false alarms, 90% of key facts stated. It's honest about what it can't establish. A larger model on a cloud GPU is the next step.
- **"Is the data safe?"**
  - It runs on the customer's server, offline if needed.
  - Every file is SHA-256 fingerprinted with a chain of custody.
  - Every action is in the audit log.
  - Roles: admin, analyst, reviewer, viewer.
  - DPDP Act tools: retention, masking, data-subject requests.
- **"What does it need?"** A GPU server for production (an NVIDIA L4 class, about ₹25–40 lakh), or Indian cloud hosting. This demo runs on a 6 GB laptop GPU.
- **"What does it cost?"**
  - About ₹3 of compute per investigation.
  - Plans start at ₹49,999 a month.
  - On-premise licence for government.
  - Paid pilot: ₹2.5 lakh for 8 weeks, credited if they continue.
- **"Is it accurate in Hindi?"** Indian-language files are translated line by line by AI4Bharat's IndicTrans2. The original stays the evidence, every figure is checked against it, and a finding resting only on translation goes to a human reviewer.
- **"What doesn't it do yet?"**
  - read scanned pages in Indian scripts;
  - hold an independent penetration-test certificate;
  - integrate with Bhashini (awaiting approval).

  Saying this openly builds trust.

## Never say
- "Forensic-grade", "100% accurate", "replaces auditors". Say "a verified first draft that a reviewer approves".
- That the VAJRA case is real. It's synthetic, by design.

## If something goes wrong
- **A live run is slow or stuck:** "It runs on a 6 GB laptop GPU; here's the one I ran before." Switch to DEMO 1. A run can't hang: it stops at its time limit and reports what it has.
- **The console won't load:** use the screenshots in `docs/demo/screens/`.
- **The model is cold (first answer slow):** run `preflight.py` again.
- **Results differ from this runbook:** small models vary between runs, which is why you show the pre-run case. Practise step 6 twice tonight on a *spare* VAJRA case, not on DEMO 2.
- **A live answer shows a red mark:** that's the product working. Code checked the AI's dates or arithmetic and caught a mistake. Say so.
