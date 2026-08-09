# Report Screen Redesign + PDF Export Plan

## Top-Level Overview

**Goal:** Replace the existing report screen (`if (screen === "report" && report)`, lines 682–1176 of `frontend/app/page.tsx`) with a redesigned card layout ordered by decision-relevance, and add a `window.print()`-based PDF export button.

**Scope:** Frontend only — `frontend/app/page.tsx`, single file. No backend changes. No new dependencies.

**Non-goals:** No changes to the upload flow, history screen, or data fetching logic.

---

## Current Report Screen Inventory (lines 682–1176)

| Block | Current position | Data fields used |
|-------|-----------------|-----------------|
| Page header (title + New Report btn) | Top | `report.report_id` |
| Evidence completeness dots | 2nd | `ec.sources_provided/total`, `ec.discrepancies_found` |
| Profile Completeness Index | 3rd | `profile_completeness.completeness_tier/score/missing_for_next_tier` |
| Risk Indicators | 4th | `risk_indicators.risk_summary`, `indicators.*`, `indicators_triggered` |
| Officer Guidance | 5th | `officer_guidance` |
| `<div className="space-y-6">` wrapper opens | — | — |
| Business type | 6th | `business_type` |
| Band rows (Revenue / Inventory / Digital) | 7th | `*_band`, `reasoning_trace.*` |
| Assessment band | 8th | `assessment_band` |
| Onboarding Pathway | 9th | `onboarding_pathway` |
| Formal Status | 10th | `vendor_formal_status.*` |
| Vendor history | 11th | `vendorHistory`, `vendor_name` |
| Location Verification | 12th | `location_verification.*` |
| Financial Evidence | 13th | `total_inflow/outflow`, `transaction_count`, etc. |
| Document Analysis | 14th | `document_analysis.*` |
| Cross-verification matrix | 15th | `source_agreement.*` |
| Discrepancy flags | 16th | `discrepancy_flags`, `photo_reuse_flag` |
| Scheme note + Sources cited | 17th | `relevant_scheme_note`, `sources_cited` |
| Evidence summary | 18th | `evidence_summary` |
| Input errors | 19th | `input_errors` |
| Missing inputs note | 20th | `missing_inputs` |
| Footer (DPDPA note + AI disclaimer) | Bottom | — |

---

## New Card Order (target layout)

```
1.  ASSESSMENT HEADER          ← NEW card (replaces old scattered header + assessment band)
2.  KEY EVIDENCE SUMMARY       ← NEW card (2×3 metric chip grid)
3.  DISCREPANCY FLAGS          ← moved up from position 16
4.  ONBOARDING PATHWAY         ← moved up from position 9
5.  FINANCIAL EVIDENCE         ← moved up from position 13
6.  DOCUMENT ANALYSIS          ← moved up from position 14
7.  RISK INDICATORS            ← moved from position 4
8.  OFFICER GUIDANCE           ← moved from position 5
9.  REASONING TRACE            ← currently embedded in band rows; extract as separate collapsible card
10. FORMAL STATUS              ← moved from position 10
11. BASIC INFORMATION (collapsed)  ← NEW collapsible wrapper containing:
      - Business type
      - Profile Completeness Index
      - Evidence completeness dots
      - Vendor history
      - Location Verification
      - Cross-verification matrix
      - Scheme note + Sources cited
      - Evidence summary
      - Input errors / Missing inputs
      - Footer (DPDPA + AI disclaimer)
      - Report ID + timestamp
```

---

## Sub-Tasks

---

### Sub-Task 1 — New Assessment Header Card (Card 1)

**Intent:**
Replace the plain title bar and the scattered `assessment_band` card with a single prominent, color-coded verdict card that gives officers the answer at a glance.

**Expected Outcomes:**
- Full-width card at top of report.
- Background: `bg-emerald-50 border-emerald-300` for "Suitable", `bg-amber-50 border-amber-300` for "Needs Review", `bg-red-50 border-red-300` for anything else.
- Large bold text: `assessment_band` value, 2xl or 3xl font.
- Sub-line: `"Assessed by Theligai — Officer review required before any credit decision"`.
- Right side: Profile Completeness tier badge (pill styled with indigo).
- Top-right corner: `📄 Download PDF` outlined button that calls `window.print()`.
- The existing `<div>` page title header (lines 688–699) is simplified to just "Theligai / New Report" nav row above this card.

**Todo List:**
1. Add a `verdictStyle(band: string)` helper that returns Tailwind class strings for bg/border/text based on the verdict value.
2. Build the assessment header card JSX with:
   - Left column: verdict label + large verdict text + sub-line
   - Right column: completeness tier badge + Download PDF button
3. Wire the Download PDF button to `window.print()`.
4. Remove the old assessment band card (currently lines 849–853) — its data is now in this header.
5. Keep the old page title `<div>` as a minimal nav bar (title + "New Report" button) above this card.

**Relevant Context:**
- `page.tsx:682-699` — old page header
- `page.tsx:849-853` — old assessment band card to remove
- `page.tsx:732-756` — Profile Completeness (tier badge to reuse here)
- `report.assessment_band` — the verdict string

**Status:** [ ] pending

---

### Sub-Task 2 — New Key Evidence Summary Card (Card 2)

**Intent:**
Give officers a scannable 2×3 grid of the most important per-dimension scores before they read detailed cards. Each chip shows a label and a color-coded value.

**Expected Outcomes:**
- 6 metric chips in a `grid grid-cols-2 sm:grid-cols-3` layout.
- Each chip: small label on top, bold value below, full chip colored by value strength.
- Chips and their data sources:
  1. **Inventory** → `report.inventory_observation_band` (Strong/Moderate/Low → green/amber/red)
  2. **Business Activity** → `report.digital_activity_band`
  3. **Revenue Pattern** → `report.revenue_consistency_band`
  4. **Savings Account** → `report.vendor_formal_status?.has_savings_account` (Yes→green, No→amber, Unknown→slate, absent→slate "—")
  5. **Document Confidence** → derived from `document_analysis.documents_processed.length` (≥3 High/green, ≥1 Medium/amber, 0 Low/red, absent "—"/slate)
  6. **Transaction Trend** → `report.trend` if available, else `report.volatility` if available, else "—"
- Helper `chipColor(value: string)` maps: Strong/High/Yes/increasing → green; Moderate/Medium/stable → amber; Low/Further/No/decreasing → red; else → slate.

**Todo List:**
1. Write `chipColor(value: string | undefined): string` helper returning Tailwind classes.
2. Derive `docConfidence` from `document_analysis.documents_processed.length`.
3. Derive `activityValue` (trend or volatility or "—").
4. Build the 6-chip grid card with label + value per chip.
5. Place this card immediately after the Assessment Header card.

**Relevant Context:**
- `report.inventory_observation_band`, `report.digital_activity_band`, `report.revenue_consistency_band`
- `report.vendor_formal_status?.has_savings_account`
- `report.document_analysis?.documents_processed`
- `report.trend`, `report.volatility`

**Status:** [ ] pending

---

### Sub-Task 3 — Reorder All Existing Cards

**Intent:**
Move the existing cards into the new order (as specified in the overview) by physically rearranging the JSX blocks. No content changes to cards — only position changes and removal of the old assessment band card (done in Sub-Task 1).

**New order (after Sub-Tasks 1 + 2):**
```
Card 1:  Assessment Header              [Sub-Task 1]
Card 2:  Key Evidence Summary           [Sub-Task 2]
Card 3:  Discrepancy Flags              [move from pos 16]
Card 4:  Onboarding Pathway             [move from pos 9]
Card 5:  Financial Evidence             [move from pos 13]
Card 6:  Document Analysis              [move from pos 14]
Card 7:  Risk Indicators                [move from pos 4]
Card 8:  Officer Guidance               [move from pos 5]
Card 9:  Reasoning Trace                [extract from band rows — see Sub-Task 4]
Card 10: Formal Status                  [move from pos 10]
Card 11: Basic Information (collapsed)  [Sub-Task 5]
```

**Expected Outcomes:**
- All existing card JSX is preserved exactly; only its position in the render tree changes.
- The `<div className="space-y-6">` wrapper that currently opens mid-page (line 805) is extended to wrap all cards from Card 3 onward.
- Risk Indicators and Officer Guidance move below Financial/Document cards.
- Business type is absorbed into the Basic Information collapsible section.

**Todo List:**
1. Extract each card block as a clearly labeled comment in the source.
2. Cut and re-paste blocks in the new order.
3. Remove the old `<div className="space-y-6">` mid-page opening; replace with a single wrapper from after Card 2.
4. Verify no duplicate renders — the assessment band card (old lines 849–853) is deleted.

**Relevant Context:**
- `page.tsx:682-1176` — entire report screen
- All card positions documented in the inventory table above

**Status:** [ ] pending

---

### Sub-Task 4 — Extract Reasoning Trace as Separate Collapsible Card (Card 9)

**Intent:**
Currently the reasoning trace is inlined inside the band rows card as expandable "Why?" buttons. Extract it as a standalone card titled "Reasoning Trace" positioned after Officer Guidance, so officers can optionally read the AI's reasoning without it cluttering the band scores.

**Expected Outcomes:**
- Band rows card (Revenue / Inventory / Digital) still shows the three band pills and their labels — but the "Why?" buttons and expanded text are removed from that card.
- New "Reasoning Trace" card (Card 9) contains all three reasoning texts, each in a collapsible accordion row (using `expandedReason` state).
- The `expandedReason` state variable is unchanged.
- Card only renders if `report.reasoning_trace` has at least one non-empty value.

**Todo List:**
1. In the band rows card (current lines 814–847): remove the `reasonText`, `expandedReason` toggle button, and expanded paragraph from each row.  Keep only the band label + pill.
2. Create a new Reasoning Trace card with three accordion rows: Revenue Consistency / Inventory Observation / Digital Activity.  Each row shows a label and a "▼ / ▲" toggle; expanded state = `expandedReason === row.reason`.
3. Place this card at position 9 in the new order (after Officer Guidance, before Formal Status).
4. Guard: only render if `report.reasoning_trace && (revenue_consistency_reasoning || inventory_observation_reasoning || digital_activity_reasoning)`.

**Relevant Context:**
- `page.tsx:814-847` — band rows card with inlined reasoning
- `page.tsx:181` — `expandedReason` state
- `report.reasoning_trace?.revenue_consistency_reasoning` etc.

**Status:** [ ] pending

---

### Sub-Task 5 — "Basic Information" Collapsible Section (Card 11)

**Intent:**
Wrap the low-priority technical/regulatory detail cards in a collapsible `<details>` or state-toggled section titled "Show Report Details ▼". Hidden by default. Officers and judges see only the decision-relevant cards unless they expand.

**Cards to wrap (all moved inside this section):**
- Business type
- Profile Completeness Index (full card with progress bar)
- Evidence completeness dots
- Vendor history
- Location Verification
- Cross-verification matrix
- Scheme note + Sources cited
- Evidence summary
- Input errors
- Missing inputs note
- Report ID, generated timestamp, DPDPA footer, AI disclaimer footer

**Expected Outcomes:**
- A new `showDetails` boolean state variable (`useState(false)`).
- A toggle button at position 11: `"Show Report Details ▼"` / `"Hide Report Details ▲"` — styled as a full-width subtle outlined button.
- When `showDetails === false`: all wrapped cards are hidden.
- When `showDetails === true`: all wrapped cards render in their current exact form.
- Print CSS (Sub-Task 6) forces this section to be visible in print regardless of `showDetails` state.

**Todo List:**
1. Add `const [showDetails, setShowDetails] = useState(false)` to the component.
2. At position 11 in the report render, add the toggle button and conditionally render the collapsible section.
3. Move all the listed cards inside the conditional block.
4. Add a `print:block` Tailwind class (or inline `@media print` style) to the collapsible wrapper so it always shows when printing.
5. The toggle button itself gets `print:hidden` so it doesn't appear in the PDF.

**Relevant Context:**
- `page.tsx:731-756` — Profile Completeness card (move inside)
- `page.tsx:701-729` — Evidence completeness dots (move inside)
- `page.tsx:806-812` — Business type card (move inside)
- `page.tsx:914-963` — Vendor history + Location Verification (move inside)
- `page.tsx:1035-1093` — Cross-verification matrix (move inside)
- `page.tsx:1116-1172` — Scheme note, Evidence summary, Input errors, Missing inputs, Footers (move inside)

**Status:** [ ] pending

---

### Sub-Task 6 — Print CSS + PDF Export

**Intent:**
Add a `<style>` block with `@media print` rules injected via a `useEffect` (or a Next.js `<style jsx global>` or a plain `<style>` tag in the JSX) that gives a clean printable layout. The Download PDF button triggers `window.print()`.

**Expected Outcomes:**
- A `<style>` tag with `media="print"` is rendered as part of the report screen JSX (not global — scoped to when the report screen is active, though `@media print` is self-scoping).
- Print rules:
  ```css
  @media print {
    /* Hide UI chrome */
    .no-print, button:not(.print-keep) { display: none !important; }
    
    /* Show collapsed section regardless of JS state */
    .print-show { display: block !important; }
    
    /* Page setup */
    body { font-size: 11pt; font-family: sans-serif; }
    @page { margin: 1.5cm; }
    
    /* Preserve colors */
    * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    
    /* No card breaks mid-page */
    .report-card { page-break-inside: avoid; break-inside: avoid; }
    
    /* Print-only header block */
    .print-header { display: block !important; }
    
    /* Hide the main page nav, step tabs, Generate Report btn */
    nav, .upload-ui { display: none !important; }
  }
  ```
- A `.print-header` div (rendered as `hidden` normally, `block` in print) containing:
  - `"THELIGAI — Microenterprise Credit Assessment Report"`
  - Report ID + generated timestamp
- A `.print-footer` div (hidden normally, visible in print) containing:
  - `"This report is for officer reference only. Not a credit decision. Human officer review required."`
- Every report card div gets a `report-card` class added.
- The Download PDF button gets class `no-print` so it hides in the printout (the browser's own print dialog handles it).
- The collapsible Basic Information section wrapper gets class `print-show` so it is always visible in print.
- Buttons that should hide in print get class `no-print`: "New Report", toggle buttons, "Why?" reasoning toggles, "View Full Report" etc. within the report card.

**Todo List:**
1. Add a `<style dangerouslySetInnerHTML>` or plain `<style>` tag at the top of the report screen `<main>` with the print CSS.
2. Add a `.print-header` div (hidden by default, visible in print) with title, report ID, and `new Date().toLocaleDateString()` timestamp.
3. Add a `.print-footer` div at the bottom of the report (hidden by default, visible in print).
4. Add `report-card` className to every major card `<div>`.
5. Add `no-print` className to: Download PDF button, "New Report" button, "Show/Hide Report Details" toggle, all reasoning "Why?" buttons.
6. Add `print-show` className to the collapsible details wrapper div.
7. Wire the Download PDF button's `onClick` to `() => window.print()`.

**Relevant Context:**
- `report.report_id` — for print header
- All card `<div>` blocks — each needs `report-card` class
- The Download PDF button is placed in Sub-Task 1's Assessment Header card

**Status:** [ ] pending

---

## Implementation Order

All sub-tasks touch the same file and must be applied in a single coordinated pass:

```
Sub-Task 1  Assessment Header card         (new JSX, remove old assessment band card)
Sub-Task 2  Key Evidence Summary card      (new JSX)
Sub-Task 4  Extract Reasoning Trace card   (modify band rows + new card)
Sub-Task 5  Basic Information collapsible  (new state + wrapper, move cards inside)
Sub-Task 3  Reorder all cards              (repositioning pass)
Sub-Task 6  Print CSS + PDF wiring         (style tag + class additions)
```

---

## Key Invariants to Preserve

- All existing card content is preserved verbatim — no data field changes.
- `expandedReason` state and its toggle logic remain — just relocated to Sub-Task 4's new card.
- `vendorHistory`, `vendorHistoryLoading`, `ec` variables referenced in the report screen remain unchanged.
- The `hasFinancial` local variable (line 683) is preserved.
- No new dependencies or imports added — `useState` is already imported.
- The `reset()` callback on "New Report" button is unchanged.
- `window.print()` is called directly — no library.

---

## Mapping: Old Field → New Card Position

| Data field | Old card | New card |
|-----------|---------|---------|
| `assessment_band` | Card 8 (Assessment) | Card 1 (Header) |
| `profile_completeness.completeness_tier` | Card 3 | Card 1 (badge) + Card 11 (full) |
| `inventory_observation_band` | Card 7 (band rows) | Card 2 (chip) + Card 9 (reasoning) |
| `digital_activity_band` | Card 7 (band rows) | Card 2 (chip) + Card 9 (reasoning) |
| `revenue_consistency_band` | Card 7 (band rows) | Card 2 (chip) + Card 9 (reasoning) |
| `vendor_formal_status.has_savings_account` | Card 10 | Card 2 (chip) + Card 10 (full) |
| `document_analysis.*` | Card 14 | Card 2 (confidence chip) + Card 6 (full) |
| `discrepancy_flags` | Card 16 | Card 3 |
| `onboarding_pathway` | Card 9 | Card 4 |
| `total_inflow/outflow` | Card 13 | Card 5 |
| `risk_indicators.*` | Card 4 | Card 7 |
| `officer_guidance` | Card 5 | Card 8 |
| `reasoning_trace.*` | inlined Card 7 | Card 9 (new dedicated card) |
| `vendor_formal_status.*` | Card 10 | Card 10 (same content, same position) |
| `business_type` | Card 6 | Card 11 (collapsed) |
| `evidence_completeness` | Card 2 | Card 11 (collapsed) |
| `source_agreement.*` | Card 15 | Card 11 (collapsed) |
| `relevant_scheme_note` | Card 17 | Card 11 (collapsed) |
| `evidence_summary` | Card 18 | Card 11 (collapsed) |
| `sources_cited` | Card 17 | Card 11 (collapsed) |
| `input_errors` | Card 19 | Card 11 (collapsed) |
| `missing_inputs` | Card 20 | Card 11 (collapsed) |
| `vendor_name` + vendor history | Card 11 | Card 11 (collapsed) |
| `location_verification.*` | Card 12 | Card 11 (collapsed) |
