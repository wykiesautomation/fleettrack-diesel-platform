# PayFast Sandbox

REV08 creates signed checkout fields server-side and redirects the customer to PayFast Sandbox. The browser return URL never activates the subscription. `/billing/payfast/notify` validates the signature, payment reference and expected amount, applies idempotency using the provider payment ID, records the payment and updates the subscription.

Before live use, implement PayFast server validation according to the active merchant documentation, verify source/network requirements, validate all required ITN fields, test recurring token lifecycle, renewal, failed payment, pause and cancellation. Never store card details.
