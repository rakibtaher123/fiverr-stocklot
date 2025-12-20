import { baseApi } from './baseApi';

export const ordersApi = baseApi.injectEndpoints({
  endpoints: (builder) => ({
    getUserOrders: builder.query({
      query: (params = {}) => ({
        url: '/orders/user',
        params,
      }),
      providesTags: ['Order'],
    }),

    getOrders: builder.query({
  query: (params = {}) => ({
    url: params.isAuth ? '/orders' : '/checkout/guest/order',
    params,
    headers: params.isAuth ? {
      Authorization: `Bearer ${localStorage.getItem('token')}`
    } : {}
  }),
  providesTags: ['Order'],
}),

    getOrderById: builder.query({
      query: (orderId) => `/orders/${orderId}`,
      providesTags: (result, error, orderId) => [{ type: 'Order', id: orderId }],
    }),

    getOrderGroup: builder.query({
      query: ({ order_group_id, token }) => {
        const headers = {};
        if (token) {
          headers['Authorization'] = `Bearer ${token}`;
        }
        return {
          url: `/orders/${order_group_id}`,
          headers,
        };
      },
      providesTags: (result, error, { order_group_id }) => [{ type: 'Order', id: order_group_id }],
    }),

    getOrderStatus: builder.query({
      query: (order_group_id) => `/orders/${order_group_id}/status`,
      providesTags: (result, error, order_group_id) => [{ type: 'Order', id: order_group_id }],
    }),

    updateOrderStatus: builder.mutation({
      query: ({ orderId, ...data }) => ({
        url: `/orders/${orderId}/status`,
        method: 'PUT',
        body: data,
      }),
      invalidatesTags: (result, error, { orderId }) => [{ type: 'Order', id: orderId }, 'Order'],
    }),

    confirmDelivery: builder.mutation({
      query: (orderId) => ({
        url: `/orders/${orderId}/confirm-delivery`,
        method: 'POST',
      }),
      invalidatesTags: (result, error, orderId) => [{ type: 'Order', id: orderId }, 'Order'],
    }),

    cancelOrder: builder.mutation({
      query: (orderGroupId) => ({
        url: `/orders/${orderGroupId}/cancel`,
        method: 'POST',
      }),
      invalidatesTags: (result, error, orderGroupId) => [{ type: 'Order', id: orderGroupId }, 'Order'],
    }),

    refreshOrderLock: builder.mutation({
      query: (orderGroupId) => ({
        url: `/orders/${orderGroupId}/refresh-lock`,
        method: 'POST',
      }),
      invalidatesTags: (result, error, orderGroupId) => [{ type: 'Order', id: orderGroupId }, 'Order'],
    }),

    finalizeOrderFees: builder.mutation({
      query: ({ orderGroupId, ...data }) => ({
        url: `/orders/${orderGroupId}/fees/finalize`,
        method: 'POST',
        body: data,
      }),
      invalidatesTags: (result, error, { orderGroupId }) => [{ type: 'Order', id: orderGroupId }, 'Order'],
    }),

    createOrder: builder.mutation({
      query: (args = {}) => {
      const body = args?.data || args;
        const customHeaders = args?.headers || {};
        const orgContext =
          customHeaders['X-Org-Context'] ||
          localStorage.getItem('currentContext') ||
          'user';
        const token = localStorage.getItem('token');

      return {
        url: '/checkout/order',
        method: 'POST',
          body,
          headers: {
            'X-Org-Context': orgContext,
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...customHeaders,
        },
      };
     },
      invalidatesTags: ['Order', 'Cart'],
    }),

    getOrderTracking: builder.query({
      query: (orderId) => `/orders/${orderId}/tracking`,
      providesTags: (result, error, orderId) => [{ type: 'Order', id: orderId }],
    }),

    getOrderHistory: builder.query({
      query: (params = {}) => ({
        url: '/orders/history',
        params,
      }),
      providesTags: ['Order'],
    }),

    getPublicOrderTracking: builder.query({
      query: (tracking_number) => ({
        url: `/public/orders/track/${tracking_number}`,
      }),
      providesTags: (result, error, tracking_number) => [{ type: 'Order', id: tracking_number }],
    }),

    getSampleTrackingNumber: builder.query({
      query: () => ({
        url: '/public/orders/sample-tracking',
      }),
    }),
  }),
  overrideExisting: false,
});

export const {
  useGetUserOrdersQuery,
  useLazyGetUserOrdersQuery,
  useGetOrdersQuery,
  useLazyGetOrdersQuery,
  useGetOrderByIdQuery,
  useLazyGetOrderByIdQuery,
  useGetOrderGroupQuery,
  useLazyGetOrderGroupQuery,
  useGetOrderStatusQuery,
  useLazyGetOrderStatusQuery,
  useUpdateOrderStatusMutation,
  useConfirmDeliveryMutation,
  useCancelOrderMutation,
  useRefreshOrderLockMutation,
  useFinalizeOrderFeesMutation,
  useCreateOrderMutation,
  useGetOrderTrackingQuery,
  useLazyGetOrderTrackingQuery,
  useGetOrderHistoryQuery,
  useLazyGetOrderHistoryQuery,
  useGetPublicOrderTrackingQuery,
  useLazyGetPublicOrderTrackingQuery,
  useGetSampleTrackingNumberQuery,
  useLazyGetSampleTrackingNumberQuery,
} = ordersApi;
