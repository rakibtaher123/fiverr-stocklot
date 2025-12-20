import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { 
  Package, ArrowLeft, Truck, MapPin, Calendar, DollarSign,
  CheckCircle, Clock, XCircle, AlertCircle, User, Phone, Mail
} from 'lucide-react';
import { useGetOrderGroupQuery } from '@/store/api/orders.api';
import { useAuth } from '@/auth/AuthProvider';
import Header from '@/components/ui/common/Header';
import Footer from '@/components/ui/common/Footer';

const OrderDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, isAuthenticated } = useAuth();
  const token = localStorage.getItem('token');

  const { data: orderGroup, isLoading, error, isError } = useGetOrderGroupQuery(
    { order_group_id: id, token },
    { skip: !id || !token || !isAuthenticated }
  );

  // Debug logging
  React.useEffect(() => {
    console.log('🔍 OrderDetail Debug:', {
      id,
      token: token ? 'exists' : 'missing',
      isAuthenticated,
      isLoading,
      isError,
      error,
      orderGroup
    });
  }, [id, token, isAuthenticated, isLoading, isError, error, orderGroup]);

  // Debug: Log the full order group structure (must be before early returns)
  React.useEffect(() => {
    if (orderGroup) {
      const orders = orderGroup.orders || [];
      const orderContact = orderGroup.order_contact || {};
      console.log('📦 Full Order Group Data:', JSON.stringify(orderGroup, null, 2));
      console.log('📦 Orders:', orders);
      console.log('📦 Order Contact:', orderContact);
    }
  }, [orderGroup]);

  const getStatusColor = (status) => {
    const statusLower = (status || '').toLowerCase();
    if (statusLower === 'completed' || statusLower === 'delivered') {
      return 'bg-green-100 text-green-800 border-green-300';
    }
    if (statusLower === 'pending' || statusLower === 'processing') {
      return 'bg-yellow-100 text-yellow-800 border-yellow-300';
    }
    if (statusLower === 'cancelled' || statusLower === 'refunded') {
      return 'bg-red-100 text-red-800 border-red-300';
    }
    if (statusLower === 'shipped') {
      return 'bg-blue-100 text-blue-800 border-blue-300';
    }
    return 'bg-gray-100 text-gray-800 border-gray-300';
  };

  const getStatusIcon = (status) => {
    const statusLower = (status || '').toLowerCase();
    if (statusLower === 'completed' || statusLower === 'delivered') {
      return CheckCircle;
    }
    if (statusLower === 'pending' || statusLower === 'processing') {
      return Clock;
    }
    if (statusLower === 'cancelled' || statusLower === 'refunded') {
      return XCircle;
    }
    if (statusLower === 'shipped') {
      return Truck;
    }
    return AlertCircle;
  };

  // Helper to format price (handle both cents and regular amounts)
  const formatPrice = (amount) => {
    if (!amount) return '0.00';
    // If amount is very large (likely in cents), divide by 100
    const price = amount > 10000 ? amount / 100 : amount;
    return price.toFixed(2);
  };

  if (isLoading) {
    return (
      <>
        <Header />
        <div className="min-h-screen bg-gray-50 py-8">
          <div className="max-w-6xl mx-auto px-4">
            <div className="animate-pulse">
              <div className="h-8 bg-gray-200 rounded w-1/4 mb-6"></div>
              <div className="h-64 bg-gray-200 rounded"></div>
            </div>
          </div>
        </div>
        <Footer />
      </>
    );
  }

  if (error) {
    return (
      <>
        <Header />
        <div className="min-h-screen bg-gray-50 py-8">
          <div className="max-w-6xl mx-auto px-4">
            <Card>
              <CardContent className="text-center py-16">
                <AlertCircle className="h-16 w-16 text-red-500 mx-auto mb-4" />
                <h2 className="text-2xl font-bold text-gray-900 mb-2">Order Not Found</h2>
                <p className="text-gray-600 mb-6">
                  {error?.data?.detail || error?.message || 'The order you are looking for could not be found.'}
                </p>
                <Button onClick={() => navigate('/orders')} className="bg-emerald-600 hover:bg-emerald-700">
                  Back to Orders
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
        <Footer />
      </>
    );
  }

  if (!orderGroup) {
    return (
      <>
        <Header />
        <div className="min-h-screen bg-gray-50 py-8">
          <div className="max-w-6xl mx-auto px-4">
            <Card>
              <CardContent className="text-center py-16">
                <Package className="h-16 w-16 text-gray-400 mx-auto mb-4" />
                <h2 className="text-2xl font-bold text-gray-900 mb-2">No Order Data</h2>
                <p className="text-gray-600 mb-6">Unable to load order details.</p>
                <Button onClick={() => navigate('/orders')} className="bg-emerald-600 hover:bg-emerald-700">
                  Back to Orders
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
        <Footer />
      </>
    );
  }

  const StatusIcon = getStatusIcon(orderGroup.status);
  const orders = orderGroup.orders || [];
  const orderContact = orderGroup.order_contact || {};

  return (
    <>
      <Header />
      <div className="min-h-screen bg-gray-50 py-8">
        <div className="max-w-6xl mx-auto px-4">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <Button
              variant="outline"
              onClick={() => navigate('/orders')}
              className="flex items-center gap-2"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Orders
            </Button>
          </div>

          {/* Order Summary Card */}
          <Card className="mb-6">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-2xl">Order #{orderGroup.id?.slice(-8) || 'N/A'}</CardTitle>
                  <p className="text-sm text-gray-600 mt-1">
                    Placed on {new Date(orderGroup.created_at).toLocaleDateString('en-ZA', {
                      year: 'numeric',
                      month: 'long',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit'
                    })}
                  </p>
                </div>
                <Badge className={getStatusColor(orderGroup.status)}>
                  <StatusIcon className="h-4 w-4 mr-2" />
                  {orderGroup.status || 'Unknown'}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="flex items-center gap-3">
                  <DollarSign className="h-5 w-5 text-emerald-600" />
                  <div>
                    <p className="text-sm text-gray-600">Total Amount</p>
                    <p className="text-xl font-bold text-emerald-900">
                      R{formatPrice(orderGroup.grand_total || 0)}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <Package className="h-5 w-5 text-emerald-600" />
                  <div>
                    <p className="text-sm text-gray-600">Items</p>
                    <p className="text-xl font-bold text-emerald-900">
                      {orderGroup.items_count || orders.reduce((sum, o) => sum + (o.items?.length || 0), 0)}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <Truck className="h-5 w-5 text-emerald-600" />
                  <div>
                    <p className="text-sm text-gray-600">Delivery</p>
                    <p className="text-xl font-bold text-emerald-900">
                      R{formatPrice(orderGroup.delivery_total || 0)}
                    </p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Orders List */}
            <div className="lg:col-span-2 space-y-4">
              <h2 className="text-xl font-bold text-gray-900 mb-4">Order Items</h2>
              {orders.length > 0 ? (
                orders.map((order, index) => (
                  <Card key={order.id || index} className="border-emerald-100">
                    <CardHeader>
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-lg">
                          Seller: {order.seller_name || 'Unknown Seller'}
                        </CardTitle>
                        <Badge className={getStatusColor(order.status || order.delivery_status)}>
                          {order.status || order.delivery_status || 'Pending'}
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-3">
                        {(order.items || []).map((item, itemIndex) => (
                          <div key={itemIndex} className="flex justify-between items-start p-3 bg-emerald-50 rounded-lg">
                            <div className="flex-1">
                              <p className="font-semibold text-gray-900">
                                {item.listing_title || item.title || 'Unknown Item'}
                              </p>
                              <div className="flex items-center gap-4 mt-1 text-sm text-gray-600">
                                <span>Quantity: {item.quantity || item.qty || 1}</span>
                                {item.unit && <span>Unit: {item.unit}</span>}
                              </div>
                              {item.species && (
                                <p className="text-xs text-gray-500 mt-1">
                                  {item.species} {item.product_type && `• ${item.product_type}`}
                                </p>
                              )}
                            </div>
                            <div className="text-right">
                              <p className="font-bold text-emerald-900">
                                R{formatPrice(item.item_total || item.price || 0)}
                              </p>
                              {(item.unit_price || item.price) && (
                                <p className="text-xs text-gray-500">
                                  R{formatPrice(item.unit_price || item.price || 0)} each
                                </p>
                              )}
                            </div>
                          </div>
                        ))}
                        <Separator />
                        <div className="flex justify-between items-center">
                          <span className="font-medium text-gray-700">Subtotal:</span>
                          <span className="font-bold text-emerald-900">
                            R{formatPrice(order.total_amount || order.subtotal || 0)}
                          </span>
                        </div>
                        {(order.delivery_cost || order.delivery) && (
                          <div className="flex justify-between items-center text-sm">
                            <span className="text-gray-600">Delivery:</span>
                            <span className="text-gray-700">
                              R{formatPrice(order.delivery_cost || order.delivery || 0)}
                            </span>
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                ))
              ) : (
                <Card>
                  <CardContent className="text-center py-8">
                    <Package className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                    <p className="text-gray-600">No order items found</p>
                  </CardContent>
                </Card>
              )}
            </div>

            {/* Order Info Sidebar */}
            <div className="space-y-4">
              {/* Contact Information */}
              {orderContact && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg flex items-center gap-2">
                      <User className="h-5 w-5" />
                      Contact Information
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {orderContact.full_name && (
                      <div className="flex items-center gap-2">
                        <User className="h-4 w-4 text-gray-400" />
                        <span className="text-sm">{orderContact.full_name}</span>
                      </div>
                    )}
                    {orderContact.email && (
                      <div className="flex items-center gap-2">
                        <Mail className="h-4 w-4 text-gray-400" />
                        <span className="text-sm">{orderContact.email}</span>
                      </div>
                    )}
                    {orderContact.phone && (
                      <div className="flex items-center gap-2">
                        <Phone className="h-4 w-4 text-gray-400" />
                        <span className="text-sm">{orderContact.phone}</span>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* Shipping Address */}
              {orderContact?.address_json && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg flex items-center gap-2">
                      <MapPin className="h-5 w-5" />
                      Shipping Address
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="text-sm text-gray-700 space-y-1">
                      {orderContact.address_json.address_line_1 && (
                        <p>{orderContact.address_json.address_line_1}</p>
                      )}
                      {orderContact.address_json.address_line_2 && (
                        <p>{orderContact.address_json.address_line_2}</p>
                      )}
                      <p>
                        {orderContact.address_json.city && `${orderContact.address_json.city}, `}
                        {orderContact.address_json.province && `${orderContact.address_json.province} `}
                        {orderContact.address_json.postal_code && orderContact.address_json.postal_code}
                      </p>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Order Summary */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Order Summary</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600">Subtotal:</span>
                    <span className="text-gray-900">
                      R{formatPrice((orderGroup.grand_total || 0) - (orderGroup.delivery_total || 0))}
                    </span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600">Delivery:</span>
                    <span className="text-gray-900">
                      R{formatPrice(orderGroup.delivery_total || 0)}
                    </span>
                  </div>
                  <Separator />
                  <div className="flex justify-between font-bold text-lg">
                    <span>Total:</span>
                    <span className="text-emerald-900">
                      R{formatPrice(orderGroup.grand_total || 0)}
                    </span>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      </div>
      <Footer />
    </>
  );
};

export default OrderDetail;

