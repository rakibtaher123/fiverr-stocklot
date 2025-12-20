# Seller Operation Flow (Code References)
Companion to the overarching `docs/USER_OPERATION_FLOWS.md` — this focuses just on the seller journey with direct code touchpoints.

## 1. Seller Onboarding & Context
- Sellers are enabled via `frontend/src/components/auth/EnhancedRegister.jsx` (individual vs. org), which posts to `/auth/register-enhanced` and optionally `/orgs` via `frontend/src/utils/apiHelper.js`.  
- `frontend/src/components/ui/common/Header.jsx` and `frontend/src/components/seller/ContextSwitcher.jsx` show seller-specific CTAs (Create Listing, Seller Dashboard) when `user.roles` includes `seller`.  
- Routing in `frontend/src/App.js` wraps `/seller/*` sections with `<ProtectedRoute roles={['seller']}>` so only verified sellers can load those views.

## 2. Listing & Inventory Management
- `frontend/src/components/pagesNo/CreateListing.jsx`, `frontend/src/components/seller/MyListings.jsx`, `frontend/src/components/seller/ListingPerformance.jsx`, and `frontend/src/components/seller/SellerOffers.jsx` rely on `frontend/src/store/api/listings.api.js` endpoints (`/seller/listings`, `/listings`, `/{id}`, `/{id}/enhance`) for creating, editing, archiving, and enhancing listings.  
- Non-RTK helpers such as `frontend/src/components/seller/InventoryBulkUpdate.jsx` manage CSV uploads or bulk edits but still call the same backend endpoints.  
- Backend data resides in `backend/models.py` Mongo collections, with enrichment services (`backend/services/enhanced_buy_request_service.py`, `backend/services/photo_intelligence_service.py`, `backend/services/openai_listing_service.py`) handling media, AI descriptions, and advanced catalog attributes.

## 3. Responding to Buy Requests
- `frontend/src/components/seller/SellerOffers.jsx` plus linked inbox cards call `frontend/src/store/api/buyRequests.api.js` for `getSellerOffers`, `getSellerInbox`, and `/buy-requests/{id}/offers`. Client-side filters (status, search) adapt the API’s response.  
- `backend/services/buy_request_service.py` ensures sellers can only have one pending offer per request, joins buyer context, and indexes offers so `/seller/offers` returns offer metadata, associated buy request, and location details.

## 4. Order Fulfillment & Finances
- `frontend/src/pages/orders/SellerOrders.jsx`, `frontend/src/components/orders/OrderHistory.jsx`, `frontend/src/components/seller/SellerShippingRates.jsx`, `frontend/src/components/analytics/MonthlyTradingStatements.jsx`, and `frontend/src/components/admin/AdminRevenueReport.jsx` reference `frontend/src/store/api/orders.api.js` and `frontend/src/store/api/admin.api.js` to show orders, tracking, fees, and payouts.  
- `backend/services/order_management_service.py` reserves inventory, creates seller orders, and writes escrow records; `backend/services/paystack_service.py` processes payouts; `backend/services/fee_service.py` and `backend/services/monthly_trading_statements_service.py` compute platform fees and statements. Admin endpoints (`/admin/payments/escrows`, `/admin/payouts`) expose the same transactional data.

## 5. Seller Analytics & Growth
- Growth dashboards like `frontend/src/components/seller/SellerAnalytics.jsx`, `frontend/src/components/seller/SellerCampaigns.jsx`, and `frontend/src/components/seller/SellerOffers.jsx` call `frontend/src/store/api/seller.api.js` and `frontend/src/store/api/analytics.api.js` (`/analytics/seller/{id}`, `/analytics/market-intelligence`, `/analytics/platform-overview`).  
- The backend aggregates (views, conversions, earnings) are assembled by `backend/services/business_intelligence_service.py`, `backend/services/analytics_service.py`, and `backend/services/monthly_trading_statements_service.py`, combining listings, orders, and referral events for report generation.

## 6. Supporting Services & Integrations
- Role and KYC moderation is supported by `frontend/src/components/admin/UserModeration.jsx` accessing `frontend/src/store/api/admin.api.js` (`/admin/users`, `/admin/kyc/*`).  
- `backend/services/kyc_service.py`, `backend/services/admin_moderation_service.py`, and `backend/services/review_service.py` keep seller compliance, disease zones, and review ecosystems healthy while updating feature flags or fee configs stored in Mongo.

