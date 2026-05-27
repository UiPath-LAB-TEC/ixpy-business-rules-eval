INSERT OR IGNORE INTO rule_definition (rule_name, document_family, label, formula, tolerance) VALUES
('borrower_balance_fields_are_mutually_exclusive', 'settlement_statement', 'Borrower balance fields are mutually exclusive', 'one or zero borrower balance fields may be present', 0.01),
('debit_amounts_equal_subtotal_debits', 'settlement_statement', 'Debit line items equal subtotal debits', 'sum(included debit line items) = subtotal debits', 0.01),
('credit_amounts_equal_subtotal_credits', 'settlement_statement', 'Credit line items equal subtotal credits', 'sum(included credit line items) = subtotal credits', 0.01),
('total_credits_equal_subtotal_credits_plus_due_from_buyer', 'settlement_statement', 'Total credits equal subtotal credits plus due from buyer', 'total credits = subtotal credits + due from buyer', 0.01),
('total_debits_equal_subtotal_debits_plus_due_to_borrower', 'settlement_statement', 'Total debits equal subtotal debits plus due to borrower', 'total debits = subtotal debits + due to borrower', 0.01),
('total_credits_equal_subtotal_credits_plus_due_from_borrower', 'settlement_statement', 'Total credits equal subtotal credits plus due from borrower', 'total credits = subtotal credits + due from borrower', 0.01),
('total_debits_balance_total_credits', 'settlement_statement', 'Total debits balance total credits', 'total debits = adjusted total credits', 0.01);
