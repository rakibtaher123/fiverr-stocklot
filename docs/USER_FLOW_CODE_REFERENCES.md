# StockLot Code-Referenced User Flow Guide
> Companion to `docs/USER_OPERATION_FLOWS.md`. This guide ties the narrated flows to the exact frontend screens, Redux queries/mutations, and backend services that implement admin, buyer, and seller behaviors.

## Shared Routing & Authentication
- **Entry point**: `frontend/src/App.js` wires public routes plus buyer (`/dashboard`, `/buyer/*`), seller (`/seller/*`), and admin (`/admin/*`) experiences behind `AuthProvider`/`AuthGate` (`frontend/src/auth/AuthProvider.jsx`), `ProtectedRoute` (`frontend/src/auth/ProtectedRoute.jsx`), and `PublicOnlyRoute` (`frontend/src/auth/PublicOnlyRoute.jsx`). 
- **Session store**: `frontend/src/store/authSlice.js` is the single source of truth for CRM data, ensuring `loadUserProfile`, `logoutUser`, and `user`/`roles` changes stay in sync with RTK Query’s `userApi`.
- **API foundation**: `frontend/src/store/api/baseApi.js` points every slice at `<BACKEND_URL>/api`, adds Bearer tokens from localStorage, and refreshes via `/auth/refresh`. All downstream sections consume injected endpoints such as `userApi`, `adminApi`, `listingsApi`, `buyRequestsApi`, `ordersApi`, `wishlistApi`, `messagingApi`, and `analyticsApi`.

## Buyer Flow (browse → request → order)
1. **Registration & login**  
   - `frontend/src/components/auth/LoginGate.jsx` (login/register modal with social sign-in) and `frontend/src/components/auth/EnhancedRegister.jsx` (individual/organization onboarding) post to `/auth/register`, `/auth/login`, `/auth/register-enhanced`, `/auth/login-enhanced`, and `/auth/social` via `frontend/src/store/api/user.api.js`.  
   - Upon success, `AuthProvider` caches the token/user and navigates buyers to `/dashboard`, `/marketplace`, or `/buy-requests`.
2. **Marketplace discovery**  
   - `frontend/src/components/pagesNo/Marketplace.jsx` builds species/price/delivery filters and uses `frontend/src/store/api/listings.api.js` (`/listings`, `/listings/search`, `/taxonomies/*`) to render `frontend/src/components/listings/ListingCard.jsx`, `frontend/src/components/pdp/ListingPDP.jsx`, and `frontend/src/components/geofence/DeliverableFilterBar.jsx`.  
   - The cart badge in `frontend/src/components/ui/common/Header.jsx` derives the count from `frontend/src/store/api/cart.api.js` (`/cart`, `/cart/add`, `/cart/item/:id`), pulling guest state from `localStorage` when no token exists.
3. **Wishlist, saved searches & alerts**  
   - Buyer personalization views (`frontend/src/components/buyer/Wishlist.jsx`, `frontend/src/components/buyer/SavedSearches.jsx`, `frontend/src/components/buyer/PriceAlerts.jsx`) rely on `frontend/src/store/api/wishlist.api.js` (`/wishlist`, `/price-alerts/*`, `/price-alerts/check`).  
   - Backend services `backend/services/wishlist_service.py` and `backend/services/price_alerts_service.py` persist favorites, compute price thresholds, and send notifications via email/in-app/SMS channels defined in those files.
4. **Buy request lifecycle**  
   - `frontend/src/components/buyRequests/CreateBuyRequestForm.jsx` and `frontend/src/components/pagesNo/BuyRequestsPage.jsx` submit to `/api/buy-requests` (and `/buy-requests/enhanced`) via `frontend/src/store/api/buyRequests.api.js`. Smart matches, offer feeds, and price suggestions surface through the same slice.  
   - The backend `backend/services/buy_request_service.py` (plus `services/enhanced_buy_request_service.py`) moderates requests, records offers, and enforces buyer-facing endpoints consumed by `frontend/src/pages/buy-requests/BuyerOffersInbox.jsx`.
5. **Offer acceptance → order**  
   - `frontend/src/pages/buy-requests/BuyerOffersInbox.jsx`, `frontend/src/pages/orders/UserOrders.jsx`, and `frontend/src/components/orders/OrderTracking.jsx` call `frontend/src/store/api/orders.api.js` (`/orders`, `/orders/:id`, `/orders/:id/status`, `/checkout/order`, `/orders/:id/confirm-delivery`) to lock pricing and pay.  
   - `backend/services/order_management_service.py` creates order groups, escrows, compliance checks (KYC via `backend/services/kyc_service.py`, disease zones via `backend/services/admin_moderation_service.py`), and price locks referenced by the API.
6. **Communication & notifications**  
   - `frontend/src/pages/InboxPage.jsx`, `frontend/src/components/unified/UnifiedInbox.jsx`, and `frontend/src/components/support/FAQChatbot.jsx` surface conversations through `frontend/src/store/api/messaging.api.js`, while `frontend/src/components/notifications/NotificationBell.jsx` subscribes to SSE/WebSocket topics.  
   - Real-time messaging is handled by `backend/services/unified_inbox_service.py`, `backend/messaging_service.py`, and `backend/services/realtime_messaging_service.py`, with `backend/services/notification_event_service.py` + `backend/services/notification_service_extended.py` emitting topics like `notifications.new` and `orders.updated`.

## Seller Flow (list → promote → fulfill)
1. **Onboarding & organizational context**  
   - Sellers pick their role in `frontend/src/components/auth/EnhancedRegister.jsx` or later via `frontend/src/components/orgs/CreateOrganizationPage.jsx`, which POSTs metadata through `frontend/src/utils/apiHelper.js` to `/orgs`.  
   - UI cues (`frontend/src/components/ui/common/Header.jsx`, `frontend/src/components/seller/ContextSwitcher.jsx`) show seller CTA shortcuts; the same `frontend/src/store/authSlice.js`/`ProtectedRoute` logic in `frontend/src/App.js` keeps `/seller/*` gated.
2. **Listing & inventory management**  
   - `frontend/src/components/pagesNo/CreateListing.jsx`, `frontend/src/components/seller/MyListings.jsx`, and `frontend/src/components/seller/SellerOffers.jsx` drive `frontend/src/store/api/listings.api.js` (`/seller/listings`, `/listings`, `/{id}/enhance`, `/{id}`) for create/edit/publish workflows, and non-RTK components (e.g., `InventoryBulkUpdate`) also lean on these endpoints.  
   - `backend/models.py` stores listings while enhancement helpers (`backend/services/enhanced_buy_request_service.py`, `backend/services/photo_intelligence_service.py`, `backend/services/openai_listing_service.py`) enrich metadata and media.
3. **Responding to requests**  
   - Sellers review offers in `frontend/src/components/seller/SellerOffers.jsx` backed by `frontend/src/store/api/buyRequests.api.js` (`/seller/offers`, `/buy-requests/{id}/offers`, `/buy-requests/price-suggestions`).  
   - `backend/services/buy_request_service.py` enforces pending offer limits, joins buyer/seller context, and populates requests so sellers can respond with pricing and documents.
4. **Orders, shipping & payouts**  
   - `frontend/src/pages/orders/SellerOrders.jsx`, `frontend/src/components/orders/OrderHistory.jsx`, `frontend/src/components/seller/SellerShippingRates.jsx`, and `frontend/src/components/analytics/MonthlyTradingStatements.jsx` query `frontend/src/store/api/orders.api.js` + `frontend/src/store/api/admin.api.js` to show fulfillment, tracking, and payout status.  
   - `backend/services/order_management_service.py`, `backend/services/paystack_service.py`, `backend/services/fee_service.py`, and `backend/services/monthly_trading_statements_service.py` create escrow releases, calculate platform commissions, and generate statements; admin endpoints such as `/admin/payments/escrows`/`/admin/payouts` surface the same data.
5. **Analytics & growth tools**  
   - `frontend/src/components/seller/SellerAnalytics.jsx`, `frontend/src/components/seller/SellerCampaigns.jsx`, and `frontend/src/components/seller/ListingPerformance.jsx` call `frontend/src/store/api/seller.api.js` + `frontend/src/store/api/analytics.api.js` (`/analytics/seller/{id}`, `/analytics/market-intelligence`, `/analytics/platform-overview`).  
   - Aggregates come from `backend/services/business_intelligence_service.py` and `backend/services/analytics_service.py`, which synthesize listings, order histories, and referral signals.

## Admin Flow (control center)
1. **Authentication & access control**  
   - Admin routes (`/admin`, `/admin/analytics/*`, `/admin/moderation/*`) are mounted in `frontend/src/App.js` behind `ProtectedRoute roles={['admin']}`; `frontend/src/components/ui/common/Header.jsx` adds the “Admin Panel” shortcut only when `user.roles` includes `admin`.
2. **Dashboard & metrics**  
   - `frontend/src/pages/dashboard/AdminDashboard.jsx`, `frontend/src/components/admin/AdminAnalyticsOverview.jsx`, `frontend/src/components/admin/AdminRevenueReport.jsx`, and `frontend/src/components/admin/AdminSellerPerformance.jsx` read from `frontend/src/store/api/admin.api.js` (`/admin/stats`, `/analytics/platform-overview`, `/admin/reports/revenue`, `/analytics/seller/:id`).  
   - Supporting services (`backend/services/business_intelligence_service.py`, `backend/services/analytics_service_enhanced.py`, `backend/services/admin_moderation_service.py`) feed those endpoints with platform health, growth, and compliance signals.
3. **Moderation & compliance**  
   - `frontend/src/components/admin/UserModeration.jsx`, `frontend/src/components/admin/ListingsModeration.jsx`, `frontend/src/components/admin/BuyRequestModeration.jsx`, and `frontend/src/components/admin/ReviewModeration.jsx` control `/admin/users`, `/admin/moderation/*`, `/admin/listings/pending`, `/admin/reviews`, `/admin/buy-requests/moderation` endpoints.  
   - `backend/services/admin_moderation_service.py` orchestrates role upgrades, disease-zone management, fee configs, and audit logs; `backend/services/review_service.py` + `backend/services/review_cron_service.py` keep review moderation data fresh.
4. **Financial & system safeguards**  
   - `frontend/src/store/api/admin.api.js` exposes `/admin/orders`, `/admin/payments/*`, `/admin/payouts`, `/admin/escrows`, `/admin/kyc/*`, `/admin/roles`, `/admin/documents`, and `/admin/compliance/*` so admins can release/refund escrow, approve KYC, and track webhooks.  
   - These endpoints rely on `backend/services/order_management_service.py`, `backend/services/paystack_service.py`, `backend/services/kyc_service.py`, `backend/services/notification_service_extended.py`, and `backend/services/admin_moderation_service.py`.
5. **Experiments, alerts & notifications**  
   - `frontend/src/components/admin/AdminExperiments.jsx`, `frontend/src/components/admin/AdminExperimentResults.jsx`, and reporting dashboards request AB testing/config data plus live metrics via `adminApi` (e.g., `/ab-test/pdp-config/{listingId}`).  
   - `backend/routes/admin_notifications.py`, `backend/services/notification_event_service.py`, and `backend/services/notification_worker.py` stream SSE/WebSocket topics such as `admin.stats.updated`, `notifications.new`, and `orders.updated` so UIs stay live.

## Platform Overview
- **Frontend stack**: `frontend/src/App.js` orchestrates the landing pages, marketplace, dashboards, FAQChatbot, and notification layers. All views call the RTK Query slices in `frontend/src/store/api/*.js`, while `AuthProvider`, `frontend/src/store/authSlice.js`, and `ProtectedRoute` enforce session + role policies.
- **Backend stack**: `backend/server.py` boots FastAPI, mounts routers (`routes/admin_notifications.py`, `routes/user_notifications.py`, `routes/dev.py`), and wires database-backed services such as `backend/services/buy_request_service.py`, `backend/services/order_management_service.py`, `backend/services/admin_moderation_service.py`, `backend/services/kyc_service.py`, `backend/services/wishlist_service.py`, `backend/services/price_alerts_service.py`, `backend/services/messaging_service.py`, `backend/services/realtime_messaging_service.py`, `backend/services/notification_event_service.py`, `backend/services/paystack_service.py`, and various analytics/BI services. MongoDB collections/models live under `backend/models*.py`.
- **Real-time & security**: SSE topics from `backend/services/sse_service.py`/`notification_event_service.py` power buyer/seller/admin notifications, while `backend/services/two_factor_service.py`, `backend/services/password_reset_service.py`, `backend/services/social_auth_service.py`, and `backend/services/kyc_service.py` protect onboarding flows. The `backend/services/rate_limiting_service.py` can be applied per endpoint for brute-force defense.
- **Documentation & observability**: `docs/API_DOCUMENTATION.md`, `docs/FRONTEND_DOCUMENTATION.md`, `docs/COMPONENT_INVENTORY.md`, and this guide capture the system’s behavior, making it easier for future contributors to map features back to code.

