const serviceSelect = document.querySelector("#serviceSelect");
const quantityInput = document.querySelector("#quantityInput");
const quantityLabel = document.querySelector("#quantityLabel");
const estimateValue = document.querySelector("#estimateValue");
const requestForm = document.querySelector(".request-form");
const requestStatus = document.querySelector("#requestStatus");
const requestService = document.querySelector("#requestService");
const summaryService = document.querySelector("#summaryService");
const summarySupplier = document.querySelector("#summarySupplier");
const summaryFee = document.querySelector("#summaryFee");
const summaryTotal = document.querySelector("#summaryTotal");
const bookingSearch = document.querySelector(".booking-search");
const hostedCheckoutButton = document.querySelector("#hostedCheckoutButton");
const checkoutStatus = document.querySelector("#checkoutStatus");
const checkoutPreviewForm = document.querySelector(".checkout-preview-form");
const checkoutBackButton = document.querySelector(".checkout-preview-form .icon-button");
const loginForm = document.querySelector(".login-form");
const loginStatus = document.querySelector("#loginStatus");
const invoiceReviewButton = document.querySelector("#invoiceReviewButton");
const invoiceReviewPanel = document.querySelector("#invoiceReviewPanel");
const invoiceReference = document.querySelector("#invoiceReference");
const invoiceCustomer = document.querySelector("#invoiceCustomer");
const invoiceContact = document.querySelector("#invoiceContact");
const invoiceSchedule = document.querySelector("#invoiceSchedule");
const invoiceDestination = document.querySelector("#invoiceDestination");
const whatsAppNotifyButton = document.querySelector("#whatsAppNotifyButton");
const payNowButton = document.querySelector("#payNowButton");
const feedbackForm = document.querySelector(".feedback-form");
const feedbackStatus = document.querySelector("#feedbackStatus");
const adminWhatsAppNumber = "85586301033";

const services = {
  hotel: {
    name: "5-Star Hotel Booking",
    unitLabel: "Nights",
    unitPrice: 700,
    min: 1,
    agencyFeeRate: 0.1
  },
  transport: {
    name: "Private Transportation",
    unitLabel: "Days",
    unitPrice: 180,
    min: 1,
    agencyFeeRate: 0.12
  },
  tour: {
    name: "Cambodia Tour Package",
    unitLabel: "Packages",
    unitPrice: 2500,
    min: 1,
    agencyFeeRate: 0.12
  },
  business: {
    name: "Business & Local Legal Coordination",
    unitLabel: "Cases",
    unitPrice: 20000,
    min: 1,
    agencyFeeRate: 0.08
  }
};

const money = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0
});

function getCurrentInvoice() {
  const selected = services[serviceSelect.value];
  const quantity = Math.max(selected.min, Number(quantityInput.value) || selected.min);
  const supplierCost = selected.unitPrice * quantity;
  const agencyFee = Math.round(supplierCost * selected.agencyFeeRate);

  return {
    selected,
    quantity,
    supplierCost,
    agencyFee,
    total: supplierCost + agencyFee
  };
}

function updateEstimate() {
  const invoice = getCurrentInvoice();

  quantityLabel.firstChild.textContent = invoice.selected.unitLabel;
  quantityInput.min = String(invoice.selected.min);
  quantityInput.value = String(invoice.quantity);
  estimateValue.textContent = money.format(invoice.total);

  if (summaryService) summaryService.textContent = invoice.selected.name;
  if (summarySupplier) summarySupplier.textContent = money.format(invoice.supplierCost);
  if (summaryFee) summaryFee.textContent = money.format(invoice.agencyFee);
  if (summaryTotal) summaryTotal.textContent = money.format(invoice.total);
}

function setRequestService(value) {
  if (!services[value]) return;
  serviceSelect.value = value;
  if (requestService) requestService.value = value;
  quantityInput.value = "1";
  updateEstimate();
}

function inferServiceFromText(text) {
  const normalized = text.toLowerCase();
  if (normalized.includes("transport") || normalized.includes("driver") || normalized.includes("car") || normalized.includes("van")) return "transport";
  if (normalized.includes("tour") || normalized.includes("siem") || normalized.includes("angkor")) return "tour";
  if (normalized.includes("business") || normalized.includes("investment") || normalized.includes("legal")) return "business";
  return "hotel";
}

serviceSelect.addEventListener("change", () => {
  quantityInput.value = "1";
  updateEstimate();
});

quantityInput.addEventListener("input", updateEstimate);
updateEstimate();

if (requestService) {
  requestService.addEventListener("change", () => {
    setRequestService(requestService.value);
  });
}

if (bookingSearch) {
  bookingSearch.addEventListener("submit", (event) => {
    event.preventDefault();
    const formData = new FormData(bookingSearch);
    const destination = formData.get("quick_destination") || "";
    const startDate = formData.get("quick_start_date") || "";
    const duration = formData.get("quick_duration") || "";
    const guests = formData.get("quick_guests") || "";
    const inferredService = inferServiceFromText(destination);

    setRequestService(inferredService);
    requestForm.elements.destination.value = destination;
    requestForm.elements.start_date.value = startDate;
    requestForm.elements.duration.value = duration;
    requestForm.elements.quantity.value = Number.parseInt(guests, 10) || 1;
    requestStatus.textContent = "Search details moved into the booking request form for invoice review.";
    requestStatus.classList.add("success");
    document.querySelector("#request").scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

function setBookingFormLocked(locked) {
  if (!requestForm) return;
  requestForm.classList.toggle("login-required", locked);
}

function getSavedLogin() {
  try {
    return JSON.parse(localStorage.getItem("ptrConnectLogin") || "null");
  } catch {
    return null;
  }
}

function applyLoginState() {
  const login = getSavedLogin();
  const loggedIn = Boolean(login && login.email);
  setBookingFormLocked(!loggedIn);

  if (loginStatus) {
    loginStatus.textContent = loggedIn
      ? `Logged in: ${login.email}. You can now record booking details.`
      : "Please login first to process booking.";
    loginStatus.classList.toggle("success", loggedIn);
  }

  if (requestStatus && !loggedIn) {
    requestStatus.textContent = "Login first, then record booking details for invoice review before payment.";
  }
}

if (loginForm) {
  loginForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const formData = new FormData(loginForm);
    const email = String(formData.get("login_email") || "").trim();
    if (!email) return;

    localStorage.setItem("ptrConnectLogin", JSON.stringify({
      email,
      loggedInAt: new Date().toISOString()
    }));
    applyLoginState();
    requestForm.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

document.querySelectorAll(".activity-tabs button").forEach((button) => {
  button.addEventListener("click", () => {
    const category = button.dataset.category;
    document.querySelectorAll(".activity-tabs button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");

    document.querySelectorAll(".activity-row article").forEach((card) => {
      const visible = category === "all" || card.dataset.category === category;
      card.classList.toggle("is-hidden", !visible);
    });

    if (category === "custom") {
      document.querySelector("#request").scrollIntoView({ behavior: "smooth", block: "start" });
      requestStatus.textContent = "Custom package selected. Add destination, duration, and requirements for review.";
      requestStatus.classList.add("success");
    }
  });
});

if (hostedCheckoutButton) {
  hostedCheckoutButton.addEventListener("click", () => {
    const invoice = getCurrentInvoice();
    const demoReference = `PTR-${Date.now().toString().slice(-6)}`;
    const checkoutPayload = {
      reference: demoReference,
      service: invoice.selected.name,
      supplierCost: invoice.supplierCost,
      agencyFee: invoice.agencyFee,
      total: invoice.total,
      provider: "Secure hosted checkout preview"
    };

    localStorage.setItem("latestCheckoutPreview", JSON.stringify(checkoutPayload));
    checkoutStatus.textContent = `Checkout request prepared: ${demoReference}. Review the gateway checkout preview below, then continue to the approved provider setup for ${money.format(invoice.total)}.`;
    checkoutStatus.classList.add("success");
    if (checkoutPreviewForm) {
      checkoutPreviewForm.hidden = false;
      checkoutPreviewForm.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  });
}

if (requestForm) {
  requestForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const login = getSavedLogin();
    if (!login || !login.email) {
      requestStatus.textContent = "Please login with Google account first before recording booking details.";
      requestStatus.classList.remove("success");
      loginForm.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }

    const formData = new FormData(requestForm);
    const service = formData.get("service");
    const quantity = Number.parseInt(formData.get("quantity"), 10) || 1;

    if (services[service]) {
      serviceSelect.value = service;
      if (requestService) requestService.value = service;
      quantityInput.value = String(quantity);
      updateEstimate();
    }

    const savedRequest = {
      name: formData.get("name"),
      contact: formData.get("contact"),
      loginEmail: login.email,
      service,
      startDate: formData.get("start_date"),
      duration: formData.get("duration"),
      quantity,
      destination: formData.get("destination"),
      details: formData.get("details"),
      invoicePreview: getCurrentInvoice(),
      recordedAt: new Date().toISOString()
    };

    localStorage.setItem("latestBookingRequest", JSON.stringify(savedRequest));
    requestStatus.textContent = "Booking details recorded. Press Invoice Review to check full invoice conditions before payment.";
    requestStatus.classList.add("success");
    if (invoiceReviewButton) invoiceReviewButton.hidden = false;
    if (checkoutPreviewForm) checkoutPreviewForm.hidden = true;
    if (checkoutStatus) {
      checkoutStatus.textContent = "Invoice review is ready. Press Request Checkout to continue to payment preview.";
      checkoutStatus.classList.add("success");
    }
  });
}

if (invoiceReviewButton) {
  invoiceReviewButton.addEventListener("click", () => {
    const savedRequest = JSON.parse(localStorage.getItem("latestBookingRequest") || "{}");
    const invoice = getCurrentInvoice();
    const reference = `INV-${Date.now().toString().slice(-6)}`;

    if (invoiceReference) invoiceReference.textContent = reference;
    if (invoiceCustomer) invoiceCustomer.textContent = savedRequest.name || "-";
    if (invoiceContact) invoiceContact.textContent = savedRequest.contact || "-";
    if (invoiceSchedule) invoiceSchedule.textContent = `${savedRequest.startDate || "-"} / ${savedRequest.duration || "-"}`;
    if (invoiceDestination) invoiceDestination.textContent = savedRequest.destination || "-";

    if (invoiceReviewPanel) {
      invoiceReviewPanel.hidden = false;
      invoiceReviewPanel.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    const whatsappText = encodeURIComponent(`PTR Connect booking: ${savedRequest.name || "Customer"} - Total ${money.format(invoice.total)}`);
    if (whatsAppNotifyButton) {
      whatsAppNotifyButton.href = `https://wa.me/${adminWhatsAppNumber}?text=${whatsappText}`;
      whatsAppNotifyButton.hidden = false;
    }
    if (payNowButton) payNowButton.hidden = false;
  });
}

if (payNowButton) {
  payNowButton.addEventListener("click", () => {
    const invoice = getCurrentInvoice();
    localStorage.setItem("latestPaymentHandoff", JSON.stringify({
      total: invoice.total,
      service: invoice.selected.name,
      preparedAt: new Date().toISOString(),
      note: "Replace this placeholder with the approved payment gateway checkout URL."
    }));
    requestStatus.textContent = `Pay Now handoff prepared for ${money.format(invoice.total)}. Replace placeholder with the live approved payment gateway URL after merchant approval.`;
    requestStatus.classList.add("success");
  });
}

if (checkoutBackButton) {
  checkoutBackButton.addEventListener("click", () => {
    checkoutPreviewForm.hidden = true;
    checkoutStatus.textContent = "Returned to invoice preview. Press Request Checkout when ready.";
  });
}

if (checkoutPreviewForm) {
  checkoutPreviewForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const invoice = getCurrentInvoice();
    const confirmationReference = `PAY-${Date.now().toString().slice(-6)}`;

    localStorage.setItem("latestPaymentConfirmationPreview", JSON.stringify({
      reference: confirmationReference,
      service: invoice.selected.name,
      total: invoice.total,
      confirmedAt: new Date().toISOString(),
      note: "Card data is not stored by this website."
    }));

    checkoutPreviewForm.reset();
    checkoutStatus.textContent = `Gateway handoff prepared: ${confirmationReference}. In live mode, card entry, authentication, authorization, and settlement must be completed by the approved payment provider before receipt and service release.`;
    checkoutStatus.classList.add("success");
  });
}

if (feedbackForm) {
  feedbackForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const formData = new FormData(feedbackForm);
    const summary = [
      "PTR Connect website feedback",
      `Name: ${formData.get("reviewer_name") || "Not provided"}`,
      `Location: ${formData.get("reviewer_location") || "Not provided"}`,
      `Device: ${formData.get("device")}`,
      `Service clarity: ${formData.get("service_clarity")}`,
      `Payment clarity: ${formData.get("payment_clarity")}`,
      `Trust level: ${formData.get("trust_level")}`,
      `Comments: ${formData.get("comments") || "No comments"}`
    ].join("\n");

    localStorage.setItem("latestWebsiteFeedback", summary);
    feedbackStatus.textContent = summary;
    feedbackStatus.classList.add("success");
  });
}

applyLoginState();
