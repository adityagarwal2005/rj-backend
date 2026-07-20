# RajwadiTukda API Contract

Base URL (dev): `http://localhost:8000/api/`

Every response is JSON in one of these two shapes:

```json
{ "success": true,  "message": "...", "data": { } }
{ "success": false, "message": "...", "errors": { } }
```

Paginated list endpoints return `data` as:

```json
{
  "count": 42,
  "total_pages": 4,
  "current_page": 1,
  "next": "http://.../?page=2",
  "previous": null,
  "results": [ ]
}
```

Authenticated requests must send `Authorization: Bearer <access_token>`.

---

## Auth — `/api/auth/`

### POST `/api/auth/register/`
Public. Creates an account and immediately returns tokens.

Request:
```json
{ "email": "user@example.com", "full_name": "Aditya Agarwal", "phone": "9999999999", "password": "StrongPass123!" }
```
Response `201`:
```json
{
  "success": true,
  "message": "Account created successfully.",
  "data": {
    "refresh": "...", "access": "...",
    "user": { "id": 1, "email": "user@example.com", "full_name": "Aditya Agarwal", "phone": "9999999999", "role": "customer", "created_at": "..." }
  }
}
```
Errors: `400` — email already registered / weak password.

### POST `/api/auth/login/`
Public. Throttled at 20/min.

Request: `{ "email": "user@example.com", "password": "StrongPass123!" }`

Response `200`: same shape as register's `data` (refresh, access, user).
Errors: `401` — invalid credentials.

### POST `/api/auth/logout/`
Auth required. Blacklists the given refresh token.

Request: `{ "refresh": "<refresh_token>" }`
Response `200`: `{ "success": true, "message": "Logged out successfully." }`

### POST `/api/auth/refresh/`
Public. Exchanges a refresh token for a new access token.

Request: `{ "refresh": "<refresh_token>" }`
Response `200`: `{ "data": { "access": "...", "refresh": "..." } }` (refresh rotates)
Errors: `401` — expired/invalid/blacklisted token.

### GET `/api/auth/profile/`
Auth required. Returns the current user.

### PUT / PATCH `/api/auth/profile/`
Auth required. Update `full_name` / `phone`. `email` and `role` are read-only.

---

## Products — `/api/products/`

### GET `/api/products/`
Public. Paginated, filterable catalog listing.

Query params: `category=<slug>`, `min_price`, `max_price`, `is_featured`, `search=<name/description>`, `ordering=price|-price|created_at|name`.

Response item shape:
```json
{
  "id": 1, "name": "Besan Ladoo", "slug": "besan-ladoo", "category": "Ladoo",
  "price": "300.00", "discount_price": null, "effective_price": "300.00",
  "weight_label": "500g", "in_stock": true, "is_featured": true,
  "primary_image": "https://.../media/products/1/photo.jpg"
}
```

### GET `/api/products/{slug}/`
Public. Full product detail including all images and stock count.

### POST `/api/products/` — Admin only
```json
{ "name": "Ghewar", "category_id": 2, "description": "...", "price": "450.00", "discount_price": null, "weight_label": "1kg", "stock_quantity": 20, "is_active": true, "is_featured": false }
```

### PUT / PATCH `/api/products/{slug}/` — Admin only
### DELETE `/api/products/{slug}/` — Admin only

### POST `/api/products/{slug}/images/` — Admin only
`multipart/form-data`: `image` (file), `alt_text`, `is_primary`, `display_order`.

### Categories — `/api/products/categories/`
Same public-read / admin-write pattern. `GET` list/detail is public; `POST/PUT/PATCH/DELETE` require admin.
```json
{ "name": "Ladoo", "description": "..." }
```

---

## Orders — `/api/orders/`

All endpoints below require authentication.

**Business rules (early-stage launch constraints, not permanent):**
- **Jaipur-only delivery.** Any address with `city` other than `"Jaipur"` (case-insensitive) is rejected with `400` at creation/update — enforced server-side, not just in the UI.
- **Tiered discount**, applied automatically to cart and order totals based on subtotal: **≥ ₹200 → 10% off, ≥ ₹300 → 15% off, ≥ ₹400 → 20% off** (flat rate on the whole subtotal, highest applicable tier wins — not stacked). See `apps/orders/pricing.py`.
- **Prepaid only.** Checkout no longer auto-confirms an order — it's created with status `pending` and only flips to `confirmed` once a payment against it is marked `success` (see Payments below).

### GET `/api/orders/cart/`
Returns the current user's cart, with the live discount already applied.
```json
{
  "id": 3,
  "items": [ { "id": 10, "product": 1, "product_name": "Kunafa Chocolate", "unit_price": "499.00", "quantity": 2, "subtotal": "998.00" } ],
  "subtotal_amount": "998.00", "discount_percentage": "20.00", "discount_amount": "199.60", "total_amount": "798.40"
}
```

### POST `/api/orders/cart/items/`
Add a product to the cart (adds to existing quantity if already present).
Request: `{ "product_id": 1, "quantity": 2 }` → returns the updated cart.

### PATCH `/api/orders/cart/items/{item_id}/`
Request: `{ "quantity": 3 }` → returns the updated cart.

### DELETE `/api/orders/cart/items/{item_id}/`
Removes the item → returns the updated cart.

### Addresses — `/api/orders/addresses/`
Standard CRUD, scoped to the authenticated user (admins see all). `city` must be `"Jaipur"`.
```json
{ "full_name": "Aditya", "phone": "9999999999", "line1": "123 MG Road", "line2": "", "city": "Jaipur", "state": "Rajasthan", "postal_code": "302001", "country": "India", "is_default": true }
```
Errors: `400` — `{ "city": ["We currently deliver only within Jaipur. Support for other cities is coming soon!"] }`

### GET `/api/orders/`
List the authenticated user's orders (admins see everyone's).

### POST `/api/orders/`
Checkout — creates an order from the current cart (status `pending`), applies the discount tier, decrements stock, clears the cart.
Request: `{ "address_id": 4, "notes": "Leave at gate" }`
Response `201`: full order object (see below).
Errors: `400` — cart empty / insufficient stock / address belongs to another user.

### GET `/api/orders/{id}/`
Order detail:
```json
{
  "id": "3f9c...", "status": "pending",
  "subtotal_amount": "998.00", "discount_percentage": "20.00", "discount_amount": "199.60", "total_amount": "798.40",
  "notes": "", "address": { },
  "items": [ { "id": 1, "product": 1, "product_name": "Kunafa Chocolate", "unit_price": "499.00", "quantity": 2, "subtotal": "998.00" } ],
  "created_at": "..."
}
```

### POST `/api/orders/{id}/cancel/`
Owner or admin. Cancels the order and restores stock. `400` if already cancelled.

### PATCH `/api/orders/{id}/status/` — Admin only
Request: `{ "status": "shipped" }` — one of `pending|confirmed|processing|shipped|delivered|cancelled`. Triggers a notification to the customer. (Normally you won't need this for `pending → confirmed` — marking the Payment successful does that automatically.)

---

## Payments — `/api/payments/`

**Prepaid-only right now**: only the `manual` gateway (UPI/bank transfer) can be initiated. `cod` and `razorpay` exist in the schema for later but are rejected with `400` if requested.

### GET `/api/payments/details/`
Public. Static UPI/bank details to show customers, sourced from `PAYMENT_UPI_ID` / `PAYMENT_BANK_*` env vars.
```json
{ "upi_id": "rajwaditukda@upi", "bank_account_name": "RajwadiTukda", "bank_account_number": "...", "bank_ifsc": "...", "bank_name": "...", "instructions": "..." }
```

### POST `/api/payments/initiate/`
Auth required. Starts a payment attempt for an order you own.
Request: `{ "order_id": "3f9c...", "gateway": "manual" }`
Response `201`:
```json
{ "payment": { "id": "...", "order": "3f9c...", "gateway": "manual", "status": "pending", "amount": "798.40", "currency": "INR", "created_at": "..." }, "gateway_data": { "gateway": "manual", "amount": "798.40", "upi_id": "...", "...": "..." } }
```

### GET `/api/payments/{id}/`
Auth required (owner or admin). Returns current payment status.

### POST `/api/payments/{id}/webhook/`
Public (for a future automated gateway). Not used by the `manual` gateway — see below.

### Confirming a manual payment (no endpoint — use Django admin)
There's no customer-facing "I've paid" button and no automated verification for
bank transfers. To confirm one: open the Payment in **Django admin**
(`/admin/payments/payment/`), change its status to `success`, save. A signal
(`apps/payments/signals.py`) then automatically flips the linked order from
`pending` to `confirmed` and notifies the customer.

---

## Notifications — `/api/notifications/`

### GET `/api/notifications/`
Auth required. Paginated list of the current user's notifications.

### PATCH `/api/notifications/{id}/read/`
Auth required. Marks a notification as read.

---

## HTTP status codes used throughout

| Code | Meaning |
|------|---------|
| 200  | OK |
| 201  | Created |
| 400  | Validation error / business rule violation (see `errors`) |
| 401  | Missing/invalid/expired credentials |
| 403  | Authenticated but not permitted (e.g. customer hitting an admin-only endpoint) |
| 404  | Resource not found |
| 500  | Unhandled server error |
