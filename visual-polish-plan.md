# Visual Polish Plan — frontend/app/page.tsx

## Top-Level Overview

**File:** `frontend/app/page.tsx` (1923 lines) — no other files touched.  
**Approach:** 5 independent polish items, each targeting specific line ranges. Applied in a single coordinated pass via `apply_diff`. No new state, no logic changes, no new imports.

The previous redesign plan (report-redesign-plan.md) was **not applied** — the file is still the original. These 5 polish items are applied to the original file as it stands.

---

## Precise Location Map (from file read)

| Target | Lines | Current class/pattern |
|--------|-------|----------------------|
| `bandColor()` helper | 112–123 | `text-red-700 bg-red-50 border-red-200` etc. |
| Band pill renders in band rows | 827 | `px-2.5 py-0.5 text-[11px] font-semibold border rounded ${bandColor(...)}` |
| Band pill in vendor history | 926 | same pattern |
| Assessment band card | 849–853 | `bg-indigo-50 border-indigo-200`, `text-lg font-semibold` |
| Card title spans (report screen) | 761, 800, 808, 852, 858, 875, 917, 943, 968, 1011, 1038, 1098, 1118, 1128, 1143 | `text-xs font-medium text-slate-400 uppercase tracking-wide` |
| Loading state outer div | 1885–1907 | `bg-slate-50 border border-slate-200 rounded-xl p-5` |
| Loading step rows | 1888–1897 | `flex items-center gap-2.5 text-sm` |
| Report screen main padding | 687 | `px-4 py-10` |
| Report cards padding (p-5) | multiple | `p-5` on each card div |
| Metric grid in Financial Evidence | 969 | `grid grid-cols-2 gap-x-6 gap-y-2.5` |

---

## Sub-Tasks

---

### Sub-Task 1 — Typography: Card Titles + Band Value Badges

**Intent:**
Standardise card title spans to `font-semibold text-gray-800` and upgrade band value badges to the specified pill-shaped Tailwind classes with filled backgrounds.

**Changes:**

**A. `bandColor()` helper (lines 112–123):**
Replace existing color returns with the new spec:
- `"Strong"` → `"bg-green-100 text-green-800 border-green-200"`
- `"Moderate"` → `"bg-yellow-100 text-yellow-800 border-yellow-200"`
- `"Low"` (and default/Further) → `"bg-red-100 text-red-800 border-red-200"`

**B. Card title spans inside the report screen:**
Every `<span className="text-xs font-medium text-slate-400 uppercase tracking-wide">` that acts as a card section title should become `<span className="text-xs font-semibold text-gray-800 uppercase tracking-wide">`. Applies only inside the `if (screen === "report" && report)` block (lines 682–1176).

**Exact occurrences to update (inside report screen only):**
- Line 761: Risk Indicators title
- Line 800: Officer Guidance title
- Line 808: Business Type title
- Line 851: Assessment title
- Line 858: Onboarding Pathway title
- Line 875: Formal Status title
- Line 917: Assessment History title
- Line 943: Location Verification title
- Line 968: Financial Evidence title
- Line 1011: Document Analysis title
- Line 1038: Cross-Verification title
- Line 1098: Needs Officer Review title
- Line 1118: Scheme Note title
- Line 1128: Evidence Summary title
- Line 1143: Input Errors title

Also update the Profile Completeness title at line 734 (`text-xs font-medium text-indigo-500`) — keep the indigo color but upgrade to `font-semibold`.

**C. Band pill render shape:**
The existing pill at line 827 already uses `rounded` (small radius). Update to `rounded-full` for the pill shape:
```
px-2.5 py-0.5 text-[11px] font-semibold border rounded-full ${bandColor(row.value)}
```
Same update for the vendor history pill at line 926.

**Todo List:**
1. Update `bandColor()` return values (lines 112–122).
2. Find-and-replace all 15 card title spans inside the report screen — change `font-medium text-slate-400` to `font-semibold text-gray-800`.
3. Update Profile Completeness title at line 734 to `font-semibold`.
4. Change `rounded` to `rounded-full` on the band pill at line 827 and line 926.

**Relevant Context:**
- `page.tsx:112-123` — `bandColor()` function
- `page.tsx:827` — band pill in band rows card
- `page.tsx:926` — band pill in vendor history card
- `page.tsx:734,761,800,808,851,858,875,917,943,968,1011,1038,1098,1118,1128,1143` — card titles

**Status:** [ ] pending

---

### Sub-Task 2 — Assessment Header Card: Color-Coded Full-Width Verdict

**Intent:**
Replace the plain indigo assessment band card (lines 849–853) with a full-width, solid-color verdict card. The background color is driven by the `assessment_band` string. Verdict text is `text-3xl font-bold`.

**Color logic (as a helper or inline ternary):**

```typescript
function verdictStyle(band: string): string {
  if (band === "Suitable") return "bg-green-600 text-white border-green-700";
  if (/needs|review/i.test(band)) return "bg-amber-500 text-white border-amber-600";
  return "bg-red-600 text-white border-red-700"; // "Further assessment required" and others
}
```

**New card structure (replaces lines 849–853):**
```tsx
<div className={`rounded-xl border p-6 ${verdictStyle(report.assessment_band)}`}>
  <p className="text-xs font-semibold uppercase tracking-wide opacity-80">Overall Assessment</p>
  <p className="mt-2 text-3xl font-bold leading-tight">{report.assessment_band}</p>
  <p className="mt-2 text-sm opacity-80">Assessed by Theligai — Officer review required before any credit decision</p>
</div>
```

**Placement:** Replaces the existing assessment band card at lines 849–853 exactly. No other cards move.

**Todo List:**
1. Add `verdictStyle()` helper function after `needsRetry()` at line 154 (before `export default function Page()`).
2. Replace lines 849–853 (the `{/* Assessment band */}` card) with the new color-coded card JSX.
3. Verify no duplicate assessment band rendering elsewhere in the report screen.

**Relevant Context:**
- `page.tsx:143-153` — `needsRetry()` — add `verdictStyle()` immediately after
- `page.tsx:849-853` — existing assessment band card to replace

**Status:** [ ] pending

---

### Sub-Task 3 — Section Dividers Between Card Groups

**Intent:**
Add thin `<hr>` dividers between the three major sections of the report:
1. After the Officer Guidance card (before Business Type) — separates "verdict + evidence" from "details"
2. After the Evidence Summary card (before Input Errors / Footers) — separates "supporting info" from "technical plumbing"

**Divider element:**
```tsx
<hr className="border-0 border-t border-gray-200 my-2" />
```

**Placement:**
- Divider 1: between `</div>` closing the Officer Guidance card (line 803) and `{/* Business type */}` (line 806) — inside the `<div className="space-y-6">` wrapper that opens at line 805. The `space-y-6` wrapper already provides spacing; `my-2` on the `<hr>` adds visual weight on top of that.
- Divider 2: between the Evidence Summary card closing `</div>` (line 1138) and `{/* Input errors */}` (line 1140).

**Todo List:**
1. Insert `<hr className="border-0 border-t border-gray-200 my-2" />` after line 803 (before the `<div className="space-y-6">` that opens the detail section, or as first element inside it).
2. Insert second `<hr className="border-0 border-t border-gray-200 my-2" />` after line 1138 (closing of Evidence Summary card, before Input Errors).

**Relevant Context:**
- `page.tsx:803-806` — gap between Officer Guidance and Business Type
- `page.tsx:1138-1141` — gap between Evidence Summary and Input Errors

**Status:** [ ] pending

---

### Sub-Task 4 — Mobile Readability: Responsive Padding + Grid

**Intent:**
Three targeted responsive fixes:
1. Report screen `<main>` — no change needed (already `px-4`).
2. All report card `<div>` elements that have `p-5` — change to `p-4 md:p-5` for mobile breathing room (spec says `p-4` on mobile, `p-6` on md — use `p-4 md:p-6` to match spec exactly).
3. Financial Evidence grid — change `grid-cols-2` to `grid-cols-2 md:grid-cols-2` (already 2 cols, spec says 2 on mobile / 3 on md — but the financial card uses exactly 2 cols with a `col-span-2` row, so a 3-column reflow would break layout; use `p-4 md:p-6` padding fix only here, leave grid as-is to avoid breaking the col-span-2 date range row).
4. The Key Evidence metric grid (if it existed) would need `grid-cols-2 md:grid-cols-3` — but since the report redesign plan was not applied, this chip grid does not yet exist. Apply the responsive grid rule only where a 3-col grid would not break existing layout.

**Actual changes:**
- Every `p-5` on a report card `<div>` → `p-4 md:p-6` (this covers all 15+ card containers).
- The `px-5 pt-5 pb-3` on the cross-verification card (line 1037) → `px-4 pt-4 pb-3 md:px-6 md:pt-6`.
- The `p-4` on evidence completeness (line 702) → `p-3 md:p-5`.
- No horizontal scroll issues exist (no fixed-width elements without overflow handling), so no explicit overflow-x fix needed beyond what already exists.

**Todo List:**
1. In the report screen (lines 682–1176), replace all standalone `p-5` on card container `<div>` elements with `p-4 md:p-6`.
2. Update the cross-verification card padding at line 1037 to responsive classes.
3. Update evidence completeness card padding at line 702.
4. Do NOT change `p-6` on the upload step cards (lines 1383+) — mobile padding fix is report-screen-only per spec.

**Relevant Context:**
- `page.tsx:702` — evidence completeness card (`p-4`)
- `page.tsx:733` — Profile Completeness card (`p-5`)
- `page.tsx:760` — Risk Indicators card (`p-5`)
- `page.tsx:799` — Officer Guidance card (`p-5`)
- `page.tsx:807` — Business Type card (`p-5`)
- `page.tsx:815` — Band rows card (`p-5`)
- `page.tsx:850` — Assessment band card (`p-5`) — will be replaced in Sub-Task 2
- `page.tsx:857` — Onboarding Pathway card (`p-5`)
- `page.tsx:874` — Formal Status card (`p-5`)
- `page.tsx:916` — Vendor history card (`p-5`)
- `page.tsx:942` — Location Verification card (`p-5`)
- `page.tsx:967` — Financial Evidence card (`p-5`)
- `page.tsx:1010` — Document Analysis card (`p-5`)
- `page.tsx:1037` — Cross-verification card (`px-5 pt-5 pb-3`)
- `page.tsx:1097` — Discrepancy flags card (`p-5`)
- `page.tsx:1117` — Scheme Note card (`p-5`)
- `page.tsx:1128` — Evidence Summary card (`p-5`)

**Status:** [ ] pending

---

### Sub-Task 5 — Loading State: Styled Card with Min-Height Step Rows

**Intent:**
The loading state (lines 1885–1907) currently renders on a `bg-slate-50` container with raw `div` rows of `h-auto`. Per spec: white background with shadow, each step row minimum 40px height with icon left / label right layout.

**Current:**
```tsx
<div className="bg-slate-50 border border-slate-200 rounded-xl p-5 flex flex-col gap-3">
  <div className="space-y-2">
    {processingSteps.map((step) => {
      const icon = step.status === "done" ? "✅" : step.status === "active" ? "🔄" : "⬜";
      return (
        <div key={step.id} className="flex items-center gap-2.5 text-sm">
          <span className={`text-base ${step.status === "active" ? "animate-pulse" : ""}`}>{icon}</span>
          <span className={...}>{step.label}</span>
        </div>
      );
    })}
  </div>
  <p className="text-xs text-slate-400 mt-1">Generating... {elapsed}s</p>
  <div ...progress bar... />
</div>
```

**Target:**
- Outer container: `bg-white border border-slate-200 rounded-xl shadow-sm p-4 md:p-6 flex flex-col gap-3`
- Each step row: `flex items-center gap-3 min-h-[40px] text-sm`
- Icon span: `text-xl w-8 shrink-0 flex items-center justify-center`
- Label span: unchanged conditional classes (done=strikethrough, active=indigo+medium, waiting=muted)
- `space-y-2` wrapper → `space-y-1` (rows have min-h already providing rhythm)

**Todo List:**
1. Change outer div className at line 1886 from `bg-slate-50 ...` to `bg-white border border-slate-200 rounded-xl shadow-sm p-4 md:p-6 flex flex-col gap-3`.
2. Change inner `space-y-2` at line 1887 to `space-y-1`.
3. Change each step row div at line 1891 from `flex items-center gap-2.5 text-sm` to `flex items-center gap-3 min-h-[40px] text-sm`.
4. Change icon span at line 1892 to `text-xl w-8 shrink-0 flex items-center justify-center`.

**Relevant Context:**
- `page.tsx:1885-1907` — entire loading state block

**Status:** [ ] pending

---

## Implementation Order

Apply as a single `apply_diff` call with multiple SEARCH/REPLACE blocks in this order:

```
1. Sub-Task 1a  — bandColor() helper (lines 112-122)
2. Sub-Task 2   — verdictStyle() helper (insert after line 153)
3. Sub-Task 1b  — card title spans (15 occurrences inside report screen)
4. Sub-Task 1c  — band pill rounded → rounded-full (lines 827, 926)
5. Sub-Task 2   — replace assessment band card (lines 849-853)
6. Sub-Task 3   — insert hr dividers (after 803, after 1138)
7. Sub-Task 4   — responsive padding on report cards (p-5 → p-4 md:p-6)
8. Sub-Task 5   — loading state styling (lines 1885-1897)
```

---

## Invariants

- No state variables added or removed.
- No logic changes — only className strings and one new pure helper.
- Upload screen cards (lines 1382–1857) are NOT touched — mobile padding fix is report-screen only.
- The `bandColor()` function is used in both the report screen AND the history screen (line 1207). The updated colors will apply there too — that is intentional and correct.
- `bandColor()` default branch covers both `"Low"` explicitly AND any unrecognised value (e.g., "Further assessment required" is the `assessment_band`, not a `Band` type — so it won't be passed to `bandColor()`; the default only fires for unknown Band values).
