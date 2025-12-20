import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui';
import { Button } from '@/components/ui';
import { Badge } from '@/components/ui';
import { ShoppingBag, ShoppingCart } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useGetUserOrdersQuery, useConfirmDeliveryMutation } from '@/store/api/orders.api';

function UserOrders() {
  const { data: ordersData, isLoading: loading, error, refetch } = useGetUserOrdersQuery();
  const [confirmDeliveryMutation] = useConfirmDeliveryMutation();

  // Extract orders from API response
  const orders = Array.isArray(ordersData) ? ordersData : (ordersData?.orders || ordersData?.buyer_orders || []);

  const confirmDelivery = async (orderId) => {
    try {
      await confirmDeliveryMutation(orderId).unwrap();
      refetch(); // Refresh orders
    } catch (error) {
      console.error('Error confirming delivery:', error);
    }
  };

  const getStatusColor = (status) => {
    const statusColors = {
      'pending_payment': 'bg-yellow-100 text-yellow-700',
      'payment_confirmed': 'bg-blue-100 text-blue-700',
      'funds_held': 'bg-purple-100 text-purple-700',
      'delivery_confirmed': 'bg-green-100 text-green-700',
      'funds_released': 'bg-green-100 text-green-700'
    };
    return statusColors[status] || 'bg-gray-100 text-gray-700';
  };

  const getStatusText = (status) => {
    const statusText = {
      'pending_payment': 'Pending Payment',
      'payment_confirmed': 'Payment Confirmed',
      'funds_held': 'Awaiting Delivery',
      'delivery_confirmed': 'Delivered',
      'funds_released': 'Complete'
    };
    return statusText[status] || status;
  };

  if (loading) {
    return (
      <Card className="border-emerald-200">
        <CardContent className="p-6">
          <div className="text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-600 mx-auto mb-4"></div>
            <p className="text-emerald-600">Loading your orders...</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="border-red-200">
        <CardContent className="p-6">
          <div className="text-center text-red-600">
            <h3>Error loading orders</h3>
            <p className="text-sm">{error?.data?.detail || error?.message || 'Something went wrong.'}</p>
            <Button onClick={() => refetch()} className="mt-4 bg-emerald-600 hover:bg-emerald-700">Retry</Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (

      <Card className="border-emerald-200">
      <CardHeader>
        <CardTitle className="text-emerald-900">My Orders</CardTitle>
        <CardDescription>Track your livestock purchases</CardDescription>
      </CardHeader>
      <CardContent>
        {(orders || []).length === 0 ? (
          <div className="text-center py-8">
            <ShoppingCart className="h-12 w-12 text-emerald-400 mx-auto mb-4" />
            <p className="text-emerald-600 mb-4">No orders yet.</p>
            <Link to="/marketplace">
              <Button className="bg-gradient-to-r from-emerald-600 to-green-600 hover:from-emerald-700 hover:to-green-700 text-white">
                Browse Livestock
              </Button>
            </Link>
          </div>
        ) : (
          <div className="space-y-4">
            {(orders || []).map(order => (
              <Card key={order.id} className="border-emerald-100">
                <CardContent className="p-4">
                  <div className="flex justify-between items-start mb-3">
                    <div>
                      <h4 className="font-semibold text-emerald-900">Order #{order.id.slice(-8)}</h4>
                      <p className="text-sm text-emerald-600">
                        {new Date(order.created_at).toLocaleDateString()}
                      </p>
                      <p className="text-sm text-emerald-700">
                        <strong>Total:</strong> R{order.total_amount}
                      </p>
                    </div>
                    <div className="text-right">
                      {/* Order Status Badge */}
                      <div className="mb-2">
                        <Badge className={getStatusColor(order.delivery_status || order.status)}>
                          {getStatusText(order.delivery_status || order.status)}
                        </Badge>
                      </div>
                      
                      {/* Delivery Confirmation Button */}
                      {(order.delivery_status === 'delivered' || order.status === 'funds_held') && (
                        <Button
                          size="sm"
                          onClick={() => confirmDelivery(order.id)}
                          className="bg-green-600 hover:bg-green-700 text-white mb-2"
                        >
                          Confirm Delivery
                        </Button>
                      )}
                      
                      {/* Payment Button */}
                      {order.payment_url && (order.status === 'pending_payment' || order.payment_status === 'pending') && (
                        <Button
                          size="sm"
                          onClick={() => window.open(order.payment_url, '_blank')}
                          className="bg-gradient-to-r from-emerald-600 to-green-600 hover:from-emerald-700 hover:to-green-700 text-white"
                        >
                          Pay Now
                        </Button>
                      )}
                    </div>
                  </div>
                  
                  {/* Order Items */}
                  {order.items && order.items.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-emerald-100">
                      <p className="text-sm text-emerald-700 font-medium mb-2">Items:</p>
                      {order.items.map((item, index) => (
                        <div key={index} className="text-sm text-emerald-600 ml-2">
                          • {item.listing_title} (Qty: {item.quantity}) - R{item.item_total}
                        </div>
                      ))}
                    </div>
                  )}
                  
                  {/* Shipping Address */}
                  {order.shipping_address && (
                    <div className="mt-3 pt-3 border-t border-emerald-100">
                      <p className="text-sm text-emerald-700 font-medium">Shipping to:</p>
                      <p className="text-sm text-emerald-600">
                        {order.shipping_address.line1}, {order.shipping_address.city}, {order.shipping_address.province}
                      </p>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </CardContent>
    </Card>      


    // <div className="min-h-screen bg-gray-50">
    //   <div className="container mx-auto px-4 py-16">
    //     <div className="max-w-4xl mx-auto">
    //       <h1 className="text-4xl font-bold text-emerald-900 mb-8">My Orders</h1>
    //       <Card className="border-emerald-200">
    //         <CardContent className="p-8">
    //           <ShoppingBag className="h-12 w-12 text-emerald-600 mb-6" />
    //           <p className="text-emerald-700 mb-6">
    //             Order management. Please use the main App.js version for full features.
    //           </p>
    //           <Button 
    //             onClick={() => window.location.href = '/dashboard'}
    //             className="bg-emerald-600 hover:bg-emerald-700 text-white"
    //           >
    //             Go to Dashboard
    //           </Button>
    //         </CardContent>
    //       </Card>
    //     </div>
    //   </div>
    // </div>
  );
}

export default UserOrders;
