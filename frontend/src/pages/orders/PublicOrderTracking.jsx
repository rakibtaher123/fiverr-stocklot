import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { 
  MapPin, Truck, Clock, CheckCircle, Package, Phone, 
  Calendar, User, Search, ArrowLeft, Loader2
} from 'lucide-react';
import { useLazyGetPublicOrderTrackingQuery, useLazyGetSampleTrackingNumberQuery } from '../../store/api/orders.api';
import { useToast } from '../../hooks/use-toast';
import Header from '@/components/ui/common/Header';
import Footer from '@/components/ui/common/Footer';

const PublicOrderTracking = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [trackingNumber, setTrackingNumber] = useState(id || '');
  const [getOrderTracking, { data: trackingData, isLoading, error }] = useLazyGetPublicOrderTrackingQuery();
  const [getSampleTracking, { data: sampleData, isLoading: loadingSample }] = useLazyGetSampleTrackingNumberQuery();

  useEffect(() => {
    // If tracking number is in URL, automatically track it
    if (id && id.trim()) {
      const trackingNumToTrack = id.trim().toUpperCase();
      getOrderTracking(trackingNumToTrack);
    }
  }, [id, getOrderTracking]);

  const handleTrack = (trackNum = null) => {
    const trackingNumToTrack = trackNum || trackingNumber.trim();
    if (!trackingNumToTrack) {
      toast({
        title: "Tracking Number Required",
        description: "Please enter a tracking number to track your order",
        variant: "destructive"
      });
      return;
    }
    
    getOrderTracking(trackingNumToTrack);
  };

  const handleGetSample = async () => {
    try {
      const result = await getSampleTracking().unwrap();
      if (result.sample_tracking_number) {
        setTrackingNumber(result.sample_tracking_number);
        toast({
          title: "Sample Tracking Number Loaded",
          description: `Using tracking number: ${result.sample_tracking_number}`,
        });
        // Automatically track it
        setTimeout(() => {
          handleTrack(result.sample_tracking_number);
        }, 500);
      } else {
        toast({
          title: "No Orders Found",
          description: result.message || "No orders with tracking numbers found in database",
          variant: "destructive"
        });
      }
    } catch (err) {
      toast({
        title: "Error",
        description: "Failed to fetch sample tracking number",
        variant: "destructive"
      });
    }
  };

  // Helper function to convert order status to tracking step
  function getStepFromStatus(status) {
    const statusMap = {
      'pending': 1,
      'pending_payment': 1,
      'confirmed': 2,
      'preparing': 3,
      'shipped': 4,
      'in_transit': 4,
      'delivered': 5,
      'completed': 5,
      'cancelled': 0
    };
    return statusMap[status?.toLowerCase()] || 1;
  }

  const trackingSteps = [
    { id: 1, title: 'Order Placed', icon: Package, description: 'Your order has been received' },
    { id: 2, title: 'Order Confirmed', icon: CheckCircle, description: 'Seller has confirmed your order' },
    { id: 3, title: 'Preparing for Shipment', icon: Clock, description: 'Order is being prepared' },
    { id: 4, title: 'In Transit', icon: Truck, description: 'Order is on the way' },
    { id: 5, title: 'Delivered', icon: MapPin, description: 'Order has been delivered' }
  ];

  const getStatusColor = (status) => {
    const statusColors = {
      'pending': 'bg-yellow-100 text-yellow-800 border-yellow-200',
      'pending_payment': 'bg-orange-100 text-orange-800 border-orange-200',
      'confirmed': 'bg-blue-100 text-blue-800 border-blue-200',
      'preparing': 'bg-purple-100 text-purple-800 border-purple-200',
      'shipped': 'bg-indigo-100 text-indigo-800 border-indigo-200',
      'in_transit': 'bg-indigo-100 text-indigo-800 border-indigo-200',
      'delivered': 'bg-emerald-100 text-emerald-800 border-emerald-200',
      'completed': 'bg-emerald-100 text-emerald-800 border-emerald-200',
      'cancelled': 'bg-red-100 text-red-800 border-red-200'
    };
    return statusColors[status?.toLowerCase()] || 'bg-gray-100 text-gray-800 border-gray-200';
  };

  const getStatusIcon = (status) => {
    const statusIcons = {
      'pending': Package,
      'pending_payment': Clock,
      'confirmed': CheckCircle,
      'preparing': Clock,
      'shipped': Truck,
      'in_transit': Truck,
      'delivered': MapPin,
      'completed': CheckCircle,
      'cancelled': Package
    };
    return statusIcons[status?.toLowerCase()] || Package;
  };

  const currentStep = trackingData ? getStepFromStatus(trackingData.status) : 0;
  const StatusIcon = trackingData ? getStatusIcon(trackingData.status) : Package;

  return (
    <>
    <Header />
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-emerald-900 mb-2">Track Your Order</h1>
            <p className="text-emerald-700">Enter your tracking number to track your livestock order delivery</p>
          </div>
          <Button
            variant="outline"
            onClick={() => navigate('/')}
            className="flex items-center gap-2"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Home
          </Button>
        </div>

        {/* Tracking Input */}
        <Card>
          <CardHeader>
            <CardTitle>Enter Tracking Number</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div className="flex gap-4">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-3 h-4 w-4 text-gray-400" />
                  <Input
                    placeholder="Enter your tracking number (e.g., TRK1234567890ABCDEF)"
                    value={trackingNumber}
                    onChange={(e) => setTrackingNumber(e.target.value.toUpperCase())}
                    className="pl-10 font-mono"
                    onKeyPress={(e) => e.key === 'Enter' && handleTrack()}
                  />
                </div>
                <Button 
                  onClick={() => handleTrack()}
                  disabled={isLoading || !trackingNumber.trim()}
                  className="bg-emerald-600 hover:bg-emerald-700"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Tracking...
                    </>
                  ) : (
                    <>
                      <Search className="h-4 w-4 mr-2" />
                      Track Order
                    </>
                  )}
                </Button>
              </div>
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <span>Don't have a tracking number?</span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleGetSample}
                  disabled={loadingSample}
                  className="text-xs"
                >
                  {loadingSample ? (
                    <>
                      <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                      Loading...
                    </>
                  ) : (
                    "Get Sample Tracking Number"
                  )}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Loading State */}
        {isLoading && (
          <Card>
            <CardContent className="text-center py-12">
              <Loader2 className="h-12 w-12 text-emerald-600 mx-auto mb-4 animate-spin" />
              <p className="text-gray-600">Loading order information...</p>
            </CardContent>
          </Card>
        )}

        {/* Error State */}
        {error && !isLoading && (
          <Card className="border-red-200">
            <CardContent className="text-center py-8">
              <Package className="h-12 w-12 text-red-400 mx-auto mb-4" />
              <h3 className="text-lg font-semibold text-red-800 mb-2">Order Not Found</h3>
              <p className="text-red-600 mb-4">
                {error?.data?.detail || error?.message || 'The order ID you entered could not be found. Please check and try again.'}
              </p>
              <Button
                variant="outline"
                onClick={() => {
                  setTrackingNumber('');
                  navigate('/track-order');
                }}
              >
                Try Another Tracking Number
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Tracking Results */}
        {trackingData && !isLoading && !error && (
          <>
            {/* Order Info */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Order Information</CardTitle>
                  <Badge className={getStatusColor(trackingData.status)}>
                    <StatusIcon className="h-4 w-4 mr-2" />
                    {trackingData.status || 'Unknown'}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <p className="text-sm text-gray-600">Tracking Number</p>
                    <p className="font-medium font-mono text-sm">{trackingData.tracking_number || trackingData.id}</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-600">Order Date</p>
                    <p className="font-medium">
                      {trackingData.created_at 
                        ? new Date(trackingData.created_at).toLocaleDateString('en-US', {
                            year: 'numeric',
                            month: 'long',
                            day: 'numeric'
                          })
                        : 'N/A'}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-600">Total Items</p>
                    <p className="font-medium">{trackingData.items_count || 0} items</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Tracking Progress */}
            <Card>
              <CardHeader>
                <CardTitle>Delivery Progress</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-6">
                  {trackingSteps.map((step) => {
                    const isCompleted = step.id <= currentStep;
                    const isCurrent = step.id === currentStep;
                    const IconComponent = step.icon;

                    return (
                      <div key={step.id} className="flex items-center space-x-4">
                        <div className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${
                          isCompleted 
                            ? 'bg-emerald-100 text-emerald-600' 
                            : 'bg-gray-100 text-gray-400'
                        }`}>
                          <IconComponent className="h-5 w-5" />
                        </div>
                        
                        <div className="flex-1">
                          <div className="flex items-center justify-between">
                            <h3 className={`font-medium ${
                              isCompleted ? 'text-emerald-900' : 'text-gray-500'
                            }`}>
                              {step.title}
                            </h3>
                            {isCurrent && (
                              <Badge className="bg-emerald-100 text-emerald-800 border-emerald-200">
                                Current
                              </Badge>
                            )}
                          </div>
                          <p className={`text-sm ${
                            isCompleted ? 'text-emerald-700' : 'text-gray-400'
                          }`}>
                            {step.description}
                          </p>
                        </div>
                        
                        {isCompleted && (
                          <CheckCircle className="h-5 w-5 text-emerald-600" />
                        )}
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>

            {/* Order Items */}
            {trackingData.orders && trackingData.orders.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Order Items</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    {trackingData.orders.map((order) => (
                      <div key={order.id} className="border rounded-lg p-4">
                        <div className="flex items-center justify-between mb-3">
                          <div>
                            <p className="font-medium">Seller: {order.seller_name}</p>
                            <Badge className={getStatusColor(order.delivery_status || order.status)}>
                              {order.delivery_status || order.status}
                            </Badge>
                          </div>
                        </div>
                        <div className="space-y-2">
                          {order.items && order.items.map((item, idx) => (
                            <div key={idx} className="flex items-center justify-between text-sm">
                              <span className="text-gray-700">{item.title}</span>
                              <span className="text-gray-600">
                                {item.quantity} {item.unit}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Shipping Address */}
            {trackingData.shipping_address && (
              <Card>
                <CardHeader>
                  <CardTitle>Shipping Address</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex items-start gap-3">
                    <MapPin className="h-5 w-5 text-emerald-600 mt-1" />
                    <div className="text-sm text-gray-700">
                      {trackingData.shipping_address.street && (
                        <p>{trackingData.shipping_address.street}</p>
                      )}
                      {trackingData.shipping_address.city && (
                        <p>{trackingData.shipping_address.city}</p>
                      )}
                      {trackingData.shipping_address.state && (
                        <p>{trackingData.shipping_address.state}</p>
                      )}
                      {trackingData.shipping_address.country && (
                        <p>{trackingData.shipping_address.country}</p>
                      )}
                      {trackingData.shipping_address.postal_code && (
                        <p className="font-medium mt-1">
                          {trackingData.shipping_address.postal_code}
                        </p>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Contact Info */}
            <Card>
              <CardHeader>
                <CardTitle>Need Help?</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center gap-3">
                  <Phone className="h-5 w-5 text-emerald-600" />
                  <span>Support: Contact us through the website</span>
                </div>
                <p className="text-sm text-gray-600 mt-4">
                  If you have questions about your order, please contact our support team or reach out to the seller directly.
                </p>
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </div>
    <Footer />
    </>
   
  );
};

export default PublicOrderTracking;

