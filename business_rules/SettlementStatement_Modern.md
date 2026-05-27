# Settlement Statement Modern Business Rules

Human-readable reference for `business_rules_ss_modern.py`.

## Purpose

`business_rules_ss_modern.py` evaluates the same settlement-statement math rules as
`business_rules_ss.py`, but reads the modern flattened extraction schema stored in:

```text
uwm_ss_v14.db
```

The script writes document-level rule results to `business_rule_eval` with the same
core columns and rule names as the original evaluator. The modern evaluator also adds
diagnostic columns when missing:

| Column | Meaning |
| --- | --- |
| `failure_reason` | Short machine-readable reason for failed rules, such as `line_item_sum_mismatch` or `no_item_rows_extracted`. |
| `details` | JSON with difference amounts, row counts, skipped rollup examples, and possible offset rows. |

## Source Data

The modern schema stores summary values as flat `field_id` records:

| Modern `field_id` | Canonical rule field |
| --- | --- |
| `subtotal-debits-amount` | `Subtotal Debits Amount` |
| `subtotal-credits-amount` | `Subtotal Credits Amount` |
| `total-debits-amount` | `Total Debits Amount` |
| `total-credits-amount` | `Total Credits Amount` |
| `due-from-borrower` | `Due From Borrower` |
| `due-to-brorrower` | `Due To Borrower` |

Line items are read from `field_id = 'items'` table rows:

| Modern item field | Canonical rule field |
| --- | --- |
| `item-description` | `Item Description` |
| `debit-amount` | `Debit Amount` |
| `credit-amount` | `Credit Amount` |
| `parent-section` | `Parent Section` |
| `row-role` | `Row Role` |

Values prefer `validated_field_value`, then `field_value`, then
`field_unformatted_value`.

## Rollup-Only Item Handling

Modern extractions can sometimes produce only one `items` row, and that row may be a
rollup such as `TOTALS`. That is treated as a missed detail-line extraction, not as a
valid line-item section.

The evaluator excludes a row from debit and credit line-item sums when:

| Skip condition | Example |
| --- | --- |
| `Row Role` contains `subtotal`, `total`, or `summary` | `subtotal row` |
| `Item Description` is exactly a rollup label | `TOTALS` |
| `Item Description` contains `subtotal` or `sub-total` | `Current Subtotal` |
| The row is a balance row | `Due To Borrower` or `Due From Borrower` |
| The row has no usable description and both debit and credit match the same extracted subtotal or total | blank description with debit and credit `409,972.50` |
| The row has a total-like label and its amount matches an extracted subtotal or total | `Total` with `755,233.93` |
| It is the only extracted item row and its debit or credit matches an extracted subtotal or total | one row where debit and credit equal `Total` |

When subtotal fields exist and all item rows are excluded, the subtotal rules still run
and fail with an actual line-item total of `0`. This makes likely table extraction
misses visible in `business_rule_eval`.

## Rules

The modern evaluator writes these rule names:

| Rule | Runs when | Expected | Actual |
| --- | --- | --- | --- |
| `borrower_balance_fields_are_mutually_exclusive` | every processed document | one or zero borrower balance fields | fails when both due-from-borrower and due-to-borrower are extracted |
| `debit_amounts_equal_subtotal_debits` | `Subtotal Debits Amount` exists | Extracted subtotal debits | Sum of non-rollup item debit amounts |
| `credit_amounts_equal_subtotal_credits` | `Subtotal Credits Amount` exists | Extracted subtotal credits | Sum of non-rollup item credit amounts |
| `total_debits_equal_subtotal_debits_plus_due_to_borrower` | subtotal debits and total debits exist | Extracted total debits | subtotal debits plus due-to-borrower, or `0` if missing |
| `total_credits_equal_subtotal_credits_plus_due_from_borrower` | subtotal credits and total credits exist | Extracted total credits | subtotal credits plus due-from-borrower, or `0` if missing |
| `total_debits_balance_total_credits` | total debits and total credits exist | Extracted total debits | total credits, adjusted by due-from-borrower or due-to-borrower when either explains the difference |

All money comparisons use a `0.01` tolerance.

## Current Valid Extraction Example

`Fir_1016138480.pdf` currently has one populated modern extraction. Its only item row
is `TOTALS`, with debit and credit amounts that match the extracted total. Therefore:

| Rule | Expected | Actual | Outcome |
| --- | ---: | ---: | --- |
| `debit_amounts_equal_subtotal_debits` | `350176.50` | `0` | Fail |
| `credit_amounts_equal_subtotal_credits` | `755233.93` | `0` | Fail |
| `total_credits_equal_subtotal_credits_plus_due_from_borrower` | `755233.93` | `755233.93` | Pass |
| `total_debits_balance_total_credits` | `755233.93` | `755233.93` | Pass |

## Running

Run the modern evaluator:

```bash
python3 business_rules_ss_modern.py
```

Run the focused modern tests:

```bash
python3 -m unittest test_business_rules_ss_modern.py
```
