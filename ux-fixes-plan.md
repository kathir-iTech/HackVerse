# UX Fixes Plan — frontend/app/page.tsx + backend/app/main.py

## Top-Level Overview

Five targeted UX changes to be applied in a **single pass** to `frontend/app/page.tsx` plus two small backend edits to `backend/app/main.py` and `backend/.env.example`. No feature additions, no logic changes to data flow.

---

## Current State Map (relevant to the fixes)

```
State machine:  "pin" → "upload" → "report" | "retry" | "history"
Step order:     1-Photos · 2-Voice · 3-Transactions · 4-Location · 5-Documents
Auth:           pin useState, authHeaders memo, handleAuthFailure()
                X-Officer-Pin header on every fetch
                backend: verify_officer_pin dependency + OFFICER_PIN env var
Auto-advance:   useEffect lines 439-446 fires setActiveStep(2) when formal-status fields filled
Back button:    Only on Step 5 (lines 1850-1856); not on steps 2/3/4
Change files:   remove/re-record exist on audio; photos have × per-image; CSV has remove
                But none are "Change" re-picker triggers; they just clear
```

---

## Sub-Tasks

---

### Sub-Task 1 — Remove PIN Authentication Completely

**Intent:**
Strip every trace of PIN auth from frontend and backend so the app opens directly to the upload screen with no gating.

**Expected Outcomes:**
- `useState("pin")` replaced with `useState("upload")` as initial screen.
- `pin`, `pinError` state variables removed.
- `authHeaders` memo removed.
- `handleAuthFailure()` removed.
- All `headers: authHeaders` removed from every `fetch()` call (`/report`, `/report/synthesize`, `/agents/vision`, `/agents/voice`, `/reports`, `/vendors/…/history`, `/reports/{id}`).
- The `if (screen === "pin")` JSX block (lines 643–680) deleted entirely.
- `reset()` no longer calls `setPin("")` or `setPinError(false)`.
- `backend/app/main.py`: `OFFICER_PIN` constant, `verify_officer_pin` function, and `dependencies=[Depends(verify_officer_pin)]` on both POST routes removed.
- `backend/.env.example`: `OFFICER_PIN=…` line removed.

**Todo List:**
1. In `page.tsx` line 156: change `useState<"pin"|"upload"|"report"|"history"|"retry">("pin")` → `useState<"upload"|"report"|"history"|"retry">("upload")`.
2. Delete lines 157–158 (`pin` and `pinError` state).
3. Delete lines 246–252 (`authHeaders` useMemo).
4. Delete lines 253–260 (`handleAuthFailure` useCallback).
5. Remove `headers: authHeaders` from the four `fetch()` calls inside `handleSubmit` (lines ~522, ~542, ~556) and from `fetchReports` (line ~580) and `viewReport` (line ~600).
6. Remove the `handleAuthFailure` reference from `handleSubmit`'s dependency array (line 574) and from `fetchReports`/`viewReport` dependency arrays.
7. Remove `401` response checks (lines 544–547, 557–559, 581–583, 601–603) — replace with generic error handling or just `if (!res.ok) throw new Error(…)`.
8. Delete the entire `if (screen === "pin") { return (…) }` block (lines 643–680).
9. Delete `setPin("")` and `setPinError(false)` from `reset()` (lines 618–619).
10. In `backend/app/main.py`: delete lines 21–28 (`OFFICER_PIN` + `verify_officer_pin`), remove `Depends` import if unused, remove `dependencies=[Depends(verify_officer_pin)]` from both `@app.post` decorators (lines 257, 379).
11. In `backend/.env.example`: delete the `OFFICER_PIN=…` line.

**Relevant Context:**
- `page.tsx:156-158` — screen/pin/pinError state
- `page.tsx:246-260` — authHeaders + handleAuthFailure
- `page.tsx:522,542,556,580,600` — fetch() calls with headers
- `page.tsx:643-680` — pin screen JSX
- `page.tsx:616-641` — reset()
- `backend/app/main.py:21-28` — PIN logic
- `backend/app/main.py:257,379` — POST route decorators
- `backend/.env.example:2`

**Status:** [ ] pending

---

### Sub-Task 2 — Reorder Steps: Vendor Formal Status Moved Before Voice

**Intent:**
Re-sequence the five upload steps so quick-to-fill structured fields come before the time-consuming voice recording step. New order: Photos → Formal Status → Voice → Transactions → Documents. The Location step is removed from the step tabs (it currently lives inside Step 4 but will stay in place; the tab labels and nav just remap).

> **Clarification on current layout:** Currently Steps 1–5 are: Photos (+ Formal Status inlined), Voice, Transactions, Location, Documents. The request is to make Formal Status its **own** Step 2, then Voice becomes Step 3, Transactions Step 4, Documents Step 5. The Location step is absorbed into the step it currently occupies or removed from tab nav entirely (it currently shows as a step tab labeled "Location" / step 4). Per the spec the new 5 steps are: Photos, Formal Status, Voice, Transactions, Documents — Location is not listed separately; it should remain accessible but not as a dedicated numbered step tab.

**New Mapping:**

| New Step | Content | Old Step |
|----------|---------|---------|
| 1 | Shop Photos (upload + thumbnails + vision progress) | 1 (partial) |
| 2 | Vendor Formal Status (savings acct, turnover, Udyam) | inlined in old Step 1 |
| 3 | Voice Note | old Step 2 |
| 4 | Transaction Records | old Step 3 |
| 5 | Official Documents | old Step 5 |

Location/Address fields (old Step 4) are moved into Step 5 (Documents) as a secondary section, or appended below Documents, so nothing is lost.

**Expected Outcomes:**
- Step nav tabs show: 📷 Photos · 📋 Status · 🎙 Voice · 💰 Transactions · 📄 Documents.
- `activeStep` type remains `1|2|3|4|5`.
- `stepStatus` array updated to match new order.
- Vendor Formal Status block extracted from Step 1 card and rendered as its own Step 2 card.
- Voice block moved to Step 3, Transactions to Step 4, Documents to Step 5.
- Location/address inputs moved under Step 5 (Documents) or Step 4 (Transactions) — Step 4 "Location" tab disappears.
- `retryFocus` mapping for `"voice"` updated to `setActiveStep(3)`, `"transactions"` to `setActiveStep(4)` in the retry screen.
- The auto-advance `useEffect` (lines 439–446) deleted (per Fix 5).

**Todo List:**
1. Update the step nav array (lines 1333–1362) to new 5-step labels and icons.
2. Update `stepStatus` array (lines 448–454) to new order — remove Location, add Formal Status entry.
3. Remove the Vendor Formal Status block from inside Step 1 card (lines 1452–1516) and build it as a new Step 2 card.
4. Shift voice JSX to be guarded by `activeStep === 3`.
5. Shift transactions JSX to be guarded by `activeStep === 4`.
6. Move location + vendor name + address inputs into Step 4 (Transactions) as a collapsible section, OR append to bottom of Step 5 (Documents) with a subtle divider — pick the simpler approach (appending to Step 5 is simpler).
7. Shift documents JSX to be guarded by `activeStep === 5`.
8. Update all "Next →" button labels to reflect the new step names.
9. Update retry screen `setActiveStep` calls: voice → 3, transactions → 4.

**Relevant Context:**
- `page.tsx:182` — `activeStep` state
- `page.tsx:437` — `step2Unlocked` (used to lock Step 2 tab — update or remove lock with new ordering)
- `page.tsx:448-454` — `stepStatus`
- `page.tsx:1332-1363` — step nav tabs
- `page.tsx:1382-1526` — Step 1 card (contains formal status to remove)
- `page.tsx:1529-1678` — Step 2 (Voice) → becomes Step 3
- `page.tsx:1681-1724` — Step 3 (Transactions) → becomes Step 4
- `page.tsx:1726-1787` — Step 4 (Location) → absorbed
- `page.tsx:1789-1858` — Step 5 (Documents) → stays Step 5 but absorbs Location
- `page.tsx:1280-1282` — retry screen step routing

**Status:** [ ] pending

---

### Sub-Task 3 — Back Button on Every Step (Steps 2–5)

**Intent:**
Each step card (2 through 5) should have a small, unobtrusive "← Back" ghost button in the top-left of the card header that navigates to the previous step without clearing any entered data.

**Expected Outcomes:**
- Step 1 card: no back button (it's the first step).
- Steps 2–5 cards: a `← Back` ghost button appears top-left of the card, styled `text-sm text-gray-500 border border-gray-200 rounded-lg px-3 py-1.5 hover:bg-gray-50 transition`.
- Clicking back sets `activeStep` to `n - 1`.
- No state is cleared on back navigation.
- The button sits in the same flex row as the step number circle and title, left-aligned before the number circle, OR as an absolute/relative element above the header row — whichever requires less restructuring (a row before the header or using the existing flex row is fine).

**Todo List:**
1. In each step card header `div.flex.items-center.gap-3` for steps 2, 3, 4, 5, prepend a back button before the number circle:
   ```tsx
   <button type="button" onClick={() => setActiveStep((activeStep - 1) as any)}
     className="mr-1 text-sm text-gray-500 border border-gray-200 rounded-lg px-3 py-1.5 hover:bg-gray-50 transition shrink-0">
     ← Back
   </button>
   ```
2. Step 1 card header: no back button added.
3. Verify `activeStep - 1` results in valid step numbers (step 2 → 1, step 3 → 2, step 4 → 3, step 5 → 4).

**Relevant Context:**
- After Sub-Task 2 reorder, back buttons land on:
  - Step 2 (Formal Status) → back to 1
  - Step 3 (Voice) → back to 2
  - Step 4 (Transactions) → back to 3
  - Step 5 (Documents) → back to 4

**Status:** [ ] pending

---

### Sub-Task 4 — "Change" Re-picker on Every Uploaded File

**Intent:**
Once a file is uploaded and confirmed (shows the ✓ line), show a small "Change" button/link beside the file name that re-opens the native file picker for **that field only**, replacing the file in state without affecting other fields. For the recorded voice blob, show "Re-record" alongside the duration display (this already partially exists for the recording path but needs to also trigger re-picker for uploaded audio files).

**Scope per field:**

| Field | Current confirmation UI | Required change |
|-------|------------------------|-----------------|
| Photos (multi) | Thumbnails with × remove | Add `label` wrapper (acts as "Change" trigger) below thumbnails that re-picks the entire set |
| Audio (file upload) | `✓ {audio.name}` + remove button | Add "Change" link that clicks `audioRef.current` |
| Audio (recorded) | `✓ Recording saved ({n}s)` + Re-record | "Re-record" already exists — keep it; add a second "Upload file instead" link to trigger `audioRef` |
| CSV | `✅ Ready — {csv.name}` + remove | Add "Change" link that clicks `csvRef.current` |
| Documents (6 slots) | `✓ {file.name}` + remove | Add "Change" link that clicks `docRefs[key].current` |

**Expected Outcomes:**
- Clicking "Change" on any field opens the OS file picker for that field only.
- The new file replaces the old one in state; background processing (vision/voice) re-fires as it currently does on fresh selection.
- No page reload, no clearing of other fields.
- The existing hidden `<input type="file">` elements are reused by programmatically calling `.click()` on them via their refs.

**Todo List:**
1. **Photos:** After the thumbnails div, add a small `<label>` that wraps a hidden `<input>` with the same `onChange={handlePhotos}` — styled as "Change photos" link. This replaces all selected photos when new selection is made (matching existing behavior since `handlePhotos` calls `setPhotos(files)`).  
   *Alternative:* The existing upload label area already has a file input — just ensure it allows re-selection (it does, since the file input is always visible). Add a "Change" text link below the thumbnails that scrolls the label into view or directly triggers the same input's click.
2. **Audio file upload:** Next to the existing `✓ {audio.name}` + remove, add:
   ```tsx
   <button type="button" onClick={() => audioRef.current?.click()}
     className="text-xs text-indigo-600 hover:text-indigo-800 underline underline-offset-2 ml-1">
     Change
   </button>
   ```
3. **Audio recorded blob:** "Re-record" button already exists (line 1568–1574). Keep it. Also add "Upload file instead" that calls `audioRef.current?.click()`.
4. **CSV:** Next to existing `remove` button, add:
   ```tsx
   <button type="button" onClick={() => { if(csvRef.current) { csvRef.current.value = ""; csvRef.current.click(); }}}
     className="text-xs text-indigo-600 hover:text-indigo-800 underline underline-offset-2 ml-1">
     Change
   </button>
   ```
   Note: must clear `.value` first so the `onChange` fires even if same file is re-selected.
5. **Documents (each slot):** In the `{file && (…)}` block for each doc, next to `remove`, add:
   ```tsx
   <button type="button" onClick={() => { const r = docRefs[key]; if(r?.current) { r.current.value = ""; r.current.click(); }}}
     className="text-xs text-indigo-600 hover:text-indigo-800 underline underline-offset-2 ml-1">
     Change
   </button>
   ```

**Relevant Context:**
- `page.tsx:1395-1451` — photos input + thumbnails
- `page.tsx:1606-1624` — audio file input + confirmation
- `page.tsx:1565-1576` — recorded audio confirmation + Re-record
- `page.tsx:1689-1708` — CSV input + confirmation
- `page.tsx:1826-1845` — per-document input + confirmation

**Status:** [ ] pending

---

### Sub-Task 5 — Stop Auto-Advance on Photo Upload

**Intent:**
Remove the `useEffect` that automatically navigates to Step 2 when formal-status fields are filled while on Step 1. Steps should only advance by explicit user click on "Next →" or a step tab. Background vision/voice processing continues on file select.

**Expected Outcomes:**
- `useEffect` at lines 439–446 is deleted entirely.
- No automatic `setActiveStep()` calls remain anywhere in the component except in explicit button `onClick` handlers and the retry screen navigation.
- The "Next →" button is visible at the bottom of every step card (Steps 1–4); Step 5 shows "Generate Report" (or the generate button is always visible below the step card).
- The Step 1 "Next" button is always enabled (no `disabled={photos.length === 0}`) — or at minimum, photos are not required to proceed (they are already optional per `canSubmit`).
- Background fetch calls in `handlePhotos` and `handleAudio` remain — they still fire on file selection, just no navigation side-effect.

**Todo List:**
1. Delete the `useEffect` block at lines 439–446 entirely.
2. Verify `step2Unlocked` (line 437) — this was only used to disable the Step 2 tab. After the reorder (Sub-Task 2), decide whether any step tab should be locked. Per spec, all tabs should be clickable freely — remove the `locked` logic from the step nav or set `locked = false` always.
3. On Step 1's "Next →" button (line 1517–1524): remove `disabled={photos.length === 0}`.
4. Confirm no other `useEffect` or handler calls `setActiveStep` automatically.
5. Ensure the "Generate Report" button remains visible below the step cards at all times (it currently is, at the bottom of the `<main>`), so users can generate from any step.

**Relevant Context:**
- `page.tsx:437` — `step2Unlocked`
- `page.tsx:439-446` — auto-advance useEffect to delete
- `page.tsx:1340-1341` — `locked` variable in step nav (references `step2Unlocked`)
- `page.tsx:1517-1524` — Step 1 "Next" button with `disabled`

**Status:** [ ] pending

---

## Implementation Order

All five sub-tasks apply to the same file, so they must be done in a **single coordinated pass** to avoid conflicting edits. The recommended sequencing within the pass:

```
1. Sub-Task 1  (PIN removal)           — state/hooks surgery, cleanest to do first
2. Sub-Task 5  (remove auto-advance)   — removes the useEffect before reorder touches steps
3. Sub-Task 2  (step reorder)          — restructures the JSX blocks
4. Sub-Task 3  (back buttons)          — add to newly-structured step cards
5. Sub-Task 4  (Change re-picker)      — add to file confirmation blocks
```

Backend changes (Sub-Task 1: main.py + .env.example) are independent and can be done in the same pass.

---

## Key Invariants to Preserve

- `handlePhotos` and `handleAudio` still fire background fetch calls on file selection — do not change their logic.
- `handleSubmit` logic (FormData construction, precomputed vs. fresh path) is unchanged except removing `authHeaders`.
- `fetchReports` and `viewReport` lose `authHeaders` but keep all other logic.
- `formData` state (used for annual_turnover in the formal-status inputs) remains — it has a bug (it stores `annual_turnover` in a FormData object but `annualTurnover` state is read in GST hint; the `onChange` for annual turnover writes to `formData` not `annualTurnover` state). This is pre-existing and **not** in scope to fix — preserve it as-is during the reorder.
- Document `docRefs` and their `useRef` declarations remain unchanged.
- The `retryFocus` mapping in the retry screen must be updated to use new step numbers after the reorder.
