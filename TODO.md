# TODO: Validation Workflow Improvements

## P0 - Fastest Reviewer Loop

1. Add compact review toolbar actions
   - Add `Mark reviewed`, `Ignore`, and `Needs extraction fix` buttons next to the existing `Add to training` button.
   - Keep each action one click and persist it immediately.
   - Reset button state when moving to the next document.

2. Add next-document workflow action
   - Add a prominent `Next failed doc` button in the review header.
   - Keep the current filtered queue context.
   - Move to the next unreviewed failed document after save/mark actions.

3. Add keyboard shortcuts
   - `A`: add current document to training exceptions.
   - `R`: mark current rule/document reviewed.
   - `I`: ignore current rule/document.
   - `N`: next document.
   - `1-4`: switch between rule buttons.

## P1 - Better Triage

4. Sort review queue by validation value
   - Prioritize documents with largest rule differences.
   - Prioritize known recurring failure patterns.
   - Prioritize low-confidence or missing-evidence cases.
   - Keep existing filters but add a default `highest value first` sort.

5. Add validation status dashboard metrics
   - Unreviewed failed documents.
   - Reviewed documents.
   - Added-to-training documents.
   - Ignored documents.
   - Top recurring root causes.

6. Improve root-cause suggestions
   - Detect missing due-from-buyer rows.
   - Detect rollup rows included or excluded incorrectly.
   - Detect subtotal mismatch patterns.
   - Detect parse failures.
   - Detect missing table rows.

## P2 - Dataset Handoff

7. Add batch training exception export
   - Copy all marked exception PDFs into the exceptions folder.
   - Generate a CSV manifest with filename, rule, root cause, notes, expected/actual totals, and reviewer status.
   - Include whether the source file was already present.

8. Add exception queue page
   - List files currently marked for training.
   - Show copied path and review metadata.
   - Allow removing a document from the exception queue if marked by mistake.

## P3 - Deeper Validation Accuracy

9. Add inline evidence annotations
   - Allow reviewer corrections in a separate annotation table.
   - Support corrected amount, include/exclude row, and root-cause notes.
   - Do not mutate the immutable `extraction` table.

10. Add live recomputation from annotations
    - Recompute the selected rule using corrected values and row inclusion decisions.
    - Show original result and corrected result side by side.
    - Use this to confirm that the proposed training correction would fix the rule.

## Recommended Next Build

Start with P0:

1. `Mark reviewed`, `Ignore`, and `Needs extraction fix` buttons.
2. `Next failed doc` button.
3. Keyboard shortcuts for the same actions.

This should reduce validation to a few clicks or keystrokes per document before investing in deeper annotation and recomputation features.
