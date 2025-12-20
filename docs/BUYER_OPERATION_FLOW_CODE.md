# Buyer Operation Flow (Code References)
Detailed buyer experience mapped to front and back code. Use this alongside `docs/USER_OPERATION_FLOWS.md` for deeper context.

## 1. Authentication & Role Setup
- `frontend/src/components/auth/LoginGate.jsx` handles login/register (POST `/auth/login`, `/auth/register`) via `frontend/src/store/api/user.api.js`.  
- `frontend/src/components/auth/EnhancedRegister.jsx` offers individual/org onboarding, posting to `/auth/register-enhanced`, storing the token, and redirecting buyers to `/dashboard`.  
- `frontend/src/auth/AuthProvider.jsx` + `frontend/src/store/authSlice.js` keep `loadUserProfile`/`logoutUser`, tokens, and role arrays in sync with `userApi` so UI gating (Protected/Public routes) works predictably.

## 2. Marketplace Discovery & Cart
- `frontend/src/components/pagesNo/Marketplace.jsx` uses `frontend/src/store/api/listings.api.js` (`/listings`, `/listings/search`, `/taxonomies/categories`) with `ListingCard`, `ListingPDP`, `DeliverableFilterBar`, and `OrderModal` to browse animals and optionally place orders/bids.  
- Header cart badge (`frontend/src/components/ui/common/Header.jsx`) calls `frontend/src/store/api/cart.api.js` (`/cart`, `/cart/add`, `/cart/item/:id`) to show counts, reading guest data from `localStorage` until auth is available.

## 3. Personalization (Wishlist & Alerts)
- `frontend/src/components/buyer/Wishlist.jsx` and `frontend/src/components/buyer/SavedSearches.jsx` use `frontend/src/store/api/wishlist.api.js` to fetch, add, remove, and update favorites (`/wishlist`, `/wishlist/add`, `/wishlist/:id`).  
- Price alert flows in `frontend/src/components/buyer/PriceAlerts.jsx` call `/price-alerts/create`, `/price-alerts`, `/price-alerts/check` to manage instant/daily thresholds; backend `backend/services/price_alerts_service.py` persists alerts and triggers email/in-app/SMS notifications.

## 4. Buy Request Lifecycle
- `frontend/src/components/buyRequests/CreateBuyRequestForm.jsx` and `frontend/src/components/pagesNo/BuyRequestsPage.jsx` POST buy requests to `/api/buy-requests` (regular and enhanced) via `frontend/src/store/api/buyRequests.api.js`.  
- The same slice surfaces `/buyers/offers`, `/buy-requests/:id/offers`, `/buy-requests/price-suggestions`, and `/buy-requests/intelligent-matches` for inbox filters; `BuyerOffersInbox` reads these to display incoming offers.  
- `backend/services/buy_request_service.py` (and `services/enhanced_buy_request_service.py`) moderate submissions, insert offers, and expose mongo lookups consumed by those endpoints.

## 5. Offer Acceptance, Checkout & Orders
- `frontend/src/pages/buy-requests/BuyerOffersInbox.jsx`, `frontend/src/pages/orders/UserOrders.jsx`, and `frontend/src/components/orders/OrderTracking.jsx` query `frontend/src/store/api/orders.api.js` endpoints such as `/orders`, `/orders/:id`, `/orders/:id/status`, `/checkout/order`, `/orders/:id/confirm-delivery`, `/orders/:id/tracking`.  
- `backend/services/order_management_service.py` creates order groups, escrows, compliance checks (KYC via `backend/services/kyc_service.py`, diseases via `backend/services/admin_moderation_service.py`), and calculates fees, tying into Paystack via `backend/services/paystack_service.py`.

## 6. Communication & Notifications
- Messaging components (`frontend/src/pages/InboxPage.jsx`, `frontend/src/components/unified/UnifiedInbox.jsx`, `frontend/src/components/support/FAQChatbot.jsx`) use `frontend/src/store/api/messaging.api.js` for inbox/conversation APIs, while `NotificationBell` subscribes to SSE topics from `frontend/src/services/realtime`.  
- Backend real-time capabilities are handled by `backend/services/unified_inbox_service.py`, `backend/messaging_service.py`, and `backend/services/realtime_messaging_service.py`, with `backend/services/notification_event_service.py` + `backend/services/notification_service_extended.py` emitting topics (`notifications.new`, `orders.updated`, `admin.stats.updated`).

## 7. Supporting Services
- `authSlice` and RTK `userApi` keep registered buyers’ metadata in sync, including 2FA (`/auth/2fa/*`), password reset (`/auth/forgot-password`, `/auth/reset-password`), and KYC flows (`/kyc/*`).  
- Monitoring and documentation: refer to `docs/USER_OPERATION_FLOWS.md` plus `docs/API_DOCUMENTATION.md` and `docs/FRONTEND_DOCUMENTATION.md` for endpoint expectations and component-level diagrams.

