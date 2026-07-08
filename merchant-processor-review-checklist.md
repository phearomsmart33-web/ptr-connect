# Merchant / Processor Review Checklist

## Business Positioning

Use this description:

> PTR Connect is an agency coordination team for travel, business, investment, hotel reservations, private transportation, Cambodia tour packages, and business/local legal coordination. Customer invoices may include third-party supplier costs plus an agency service fee. Card payments are accepted only for approved itemized invoices after customer verification and supplier confirmation. Payments must be processed through an approved gateway or merchant acquirer and settled to the merchant account.

Avoid this wording:

> We collect customer payment and settle overseas.

Also avoid saying:

> We sell hotel rooms directly.

Also avoid saying:

> We provide Mastercard-to-Mastercard transfer, cash-out, remittance, or person-to-person payment service.

## Website Pages Required

- Home page with clear PTR Connect brand, service description, and pricing
- Payment Policy
- Refund / Cancellation Policy
- Terms & Conditions
- Privacy Policy
- AML / KYC Procedure
- Contact page with real company details

## Documents To Prepare

- Company registration
- Director/owner ID
- Business address proof
- Bank account information
- Agency service agreement template
- Itemized invoice template showing supplier cost and agency service fee
- Refund/cancellation policy
- Partner agreement or cooperation SOP
- AML/KYC checklist
- Real support email, phone number, and business address on the website
- Sample customer invoice with invoice number, service scope, supplier cost, agency fee, refund terms, and customer approval line
- Sample receipt and booking/service confirmation record
- Redacted previous hotel quotation/booking proof from prior manual coordination work
- Live payment gateway integration plan, including hosted checkout, callback/webhook verification, success page, failed page, and reconciliation report

## Do Not Submit Until These Are Ready

- Replace all placeholder contact information.
- Confirm legal entity, bank account name, and website brand name are consistent.
- Confirm service descriptions do not look like remittance, cash-out, debt collection, card-to-card transfer, or third-party fund transfer.
- Confirm checkout button does not collect card data directly on the website.
- Confirm high-value cases have enhanced KYC, service agreement, and management approval.
- Redact guest names, invoice numbers, room numbers, phone numbers, and personal identifiers before sharing sample hotel proof publicly.

## Processor Questions To Ask

1. Can this business be approved for card-not-present service payments?
2. Which MCC is appropriate for an agency that collects approved invoices covering supplier costs plus an agency service fee?
3. Can Visa Secure and Mastercard Identity Check / 3DS be enabled?
4. What transaction limit applies to high-value service invoices?
5. What documents are required for a USD 20,000 consulting/legal coordination case?
6. What settlement schedule and rolling reserve may apply?

## Safe Service / Goods Transaction Flow

1. Customer submits request.
2. PTR Connect reviews customer details and service purpose.
3. Supplier availability, scope, price, and timeline are confirmed.
4. PTR Connect issues an itemized invoice with supplier cost, agency fee, refund, and cancellation terms.
5. Customer approves the invoice and pays by Visa or Mastercard through an approved hosted checkout.
6. Booking, supplier work, transport arrangement, tour coordination, or goods dispatch begins.
7. Receipt, booking proof, delivery proof, or service completion record is issued.
8. Supplier payment and agency fee records are reconciled.

## Recommended Payment Option

1. Approved payment gateway hosted checkout for itemized service invoices.
2. Visa Secure / Mastercard Identity Check / 3DS enabled where available.
3. Payment authorization, callback/webhook verification, receipt issue, and merchant account reconciliation.

Avoid collecting card number, expiry, or CVC directly on the agency website.

## Red Flags To Reject

- Anonymous payer.
- Cardholder name does not match customer record.
- No clear service purpose.
- Request looks like cash-out, remittance, card-to-card transfer, or debt payment.
- Customer refuses KYC for high-value case.
- Supplier cannot confirm service scope.
- Payment amount does not match invoice.
