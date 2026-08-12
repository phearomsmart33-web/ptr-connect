# PTR Checkout UI Reference

`checkout-reference.html` is a **frontend-only plain-JavaScript checkout reference** designed to match the current PTR Connect booking and invoice appearance. It uses the same navy-and-blue design system, compact business header, invoice reference, service summary, and balance-due presentation. It does not modify the existing payment logic, backend, API, hosting, or merchant configuration.

The checkout reference uses responsive CSS with mobile-safe sizing, `min-width: 0` containers, flexible grid columns, controlled text wrapping, and device-specific breakpoints. It is designed to prevent clipped text, overlap, and misplaced labels on browser, iPhone, iPad, iOS, and Android layouts.

| Item | Result |
|---|---|
| iPhone layout (390 × 844) | Passed: page and payment rows fit without horizontal overflow. |
| Android layout (412 × 915) | Passed: page and payment rows fit without horizontal overflow. |
| iPad layout (768 × 1024) | Passed: payment summary and method list stay readable. |
| Desktop layout (1440 × 1000) | Passed: aligned two-column checkout presentation. |
| Credit / debit card reference | Passed: selection, summary update, continue label, and safe handoff event work. |
| ABA KHQR reference | Passed: selection, summary update, continue label, and safe handoff event work. |
| Actual payment submission | Not performed. The UI only emits reference events and never collects or submits card details. |

## Future API connection

The checkout reference exposes `window.PTRCheckoutReference` for safe integration. Set invoice data without changing the UI implementation:

```js
PTRCheckoutReference.setData({
  reference: "INV-PTR-2026-0009",
  service: "Private Transport · Phnom Penh to Siem Reap",
  balance: 245,
  method: "aba-khqr"
});
```

Your application can listen for the selected method and the intentional handoff event:

```js
window.addEventListener("ptr:checkout-method", ({ detail }) => {
  // detail.method.id is aba-khqr, card, alipay, or wechat
  // detail.invoice contains reference, service, and balance
});

window.addEventListener("ptr:checkout-continue", ({ detail }) => {
  // Call the approved hosted-payment API here.
  // Do not collect card number, PIN, CVV, OTP, or wallet credentials in this UI.
});
```
