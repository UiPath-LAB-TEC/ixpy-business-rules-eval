const rules = [
  ['debit_amounts_equal_subtotal_debits', 'sum(included debit line items) = subtotal debits'],
  ['credit_amounts_equal_subtotal_credits', 'sum(included credit line items) = subtotal credits'],
  ['total_debits_equal_subtotal_debits_plus_due_to_borrower', 'total debits = subtotal debits + due to borrower'],
  ['total_credits_equal_subtotal_credits_plus_due_from_borrower', 'total credits = subtotal credits + due from borrower'],
  ['total_debits_balance_total_credits', 'total debits = total credits adjusted by due-from/due-to borrower'],
  ['borrower_balance_fields_are_mutually_exclusive', 'one or zero borrower balance fields may be present'],
];

export function RulesPage() {
  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>Rules</h1>
          <p>Settlement-statement rule definitions and formulas.</p>
        </div>
      </header>
      <section className="panel">
        <table>
          <thead><tr><th>Rule</th><th>Formula</th><th>Tolerance</th></tr></thead>
          <tbody>
            {rules.map(([name, formula]) => <tr key={name}><td>{name}</td><td>{formula}</td><td>$0.01</td></tr>)}
          </tbody>
        </table>
      </section>
    </section>
  );
}
