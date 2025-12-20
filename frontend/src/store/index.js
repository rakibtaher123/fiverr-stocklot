import { configureStore } from '@reduxjs/toolkit';
import { baseApi } from './api/baseApi';
import authReducer from './authSlice';
import cartReducer from './cartSlice';

// Import all API slices to ensure they inject their endpoints
import './api/auth.api';
import './api/user.api';
import './api/listings.api';
import './api/cart.api';
import './api/checkout.api';
import './api/orders.api';
import './api/buyRequests.api';
import './api/messaging.api';
import './api/notifications.api';
import './api/admin.api';
import './api/search.api';
import './api/uploads.api';
import './api/seller.api';
import './api/kyc.api';
import './api/taxonomy.api';
import './api/profile.api';
import './api/wishlist.api';
import './api/reviews.api';
import './api/payments.api';
import './api/ml.api';
import './api/organizations.api';
import './api/blog.api';
import './api/referrals.api';
import './api/email.api';
import './api/delivery.api';
import './api/analytics.api';
import './api/platform.api';
import './api/suggestions.api';
import './api/contact.api';
import './api/marketing.api';
import './api/cron.api';
import './api/webhooks.api';

export const store = configureStore({
  reducer: {
    auth: authReducer,
    cart: cartReducer,
    [baseApi.reducerPath]: baseApi.reducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: {
        // Ignore these action types for serialization check
        ignoredActions: [
          'api/executeQuery/fulfilled',
          'api/executeQuery/pending',
          'api/executeQuery/rejected',
        ],
      },
    }).concat(baseApi.middleware),
});

// Types for TypeScript support (if using TypeScript)
// Uncomment these if you're using TypeScript:
// export type RootState = ReturnType<typeof store.getState>;
// export type AppDispatch = typeof store.dispatch;

