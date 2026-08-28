from pathlib import Path
import py_compile
for f in ['app/models.py','app/routes.py','app/__init__.py','app/payment_entitlement_migration.py']:py_compile.compile(f,doraise=True)
r=Path('app/routes.py').read_text();m=Path('app/models.py').read_text();h=Path('app/templates/billing.html').read_text()
for x in ['BILLING_TERMS','subscription_is_entitled','paid_period_end','THREE_YEAR','paid_until','term_months']:assert x in r or x in m,x
for x in ['Month-to-month','Annual prepaid','Three-year prepaid','HTTP 402']:assert x in h,x
print('PAYMENT_ENTITLEMENT PASS')
