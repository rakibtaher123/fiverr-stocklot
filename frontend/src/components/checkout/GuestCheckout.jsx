'use client';

import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Badge } from '../ui/badge';
import { Separator } from '../ui/separator';
import { Alert, AlertDescription } from '../ui/alert';
import { 
  ShoppingCart, MapPin, Phone, Mail, User, 
  Shield, AlertTriangle, CheckCircle, Loader2,
  Package, CreditCard
} from 'lucide-react';
import LocationPicker from '../location/CheckoutLocationPicker';
import { assessRisk, RISK_CATEGORIES, getRiskCategory } from '../../lib/risk/riskRules';
import api from '../../utils/apiHelper';
import { handleAPIError } from '../../services/api';
import { useToast } from '../../hooks/use-toast';
import { useAuth } from '../../auth/AuthProvider';
import { selectCartItems } from '../../store/cartSlice';
import Header from '@/components/ui/common/Header';
import Footer from '@/components/ui/common/Footer';
import { useCreateOrderMutation } from '@/store/api/orders.api';
import CheckoutAuthModal from './CheckoutAuthModal';

export default function GuestCheckout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { toast } = useToast();
  const { user, isAuthenticated } = useAuth();
  const [addresses, setAddresses] = useState([]);
  
  // Get cart items from Redux store
  const reduxCartItems = useSelector(selectCartItems);

  const [items, setItems] = useState([]);
  const [shipTo, setShipTo] = useState(null);
  const [contact, setContact] = useState({ email: '', phone: '', full_name: '' });
  const [quote, setQuote] = useState(null);
  const [risk, setRisk] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [step, setStep] = useState('details'); // details, quote, payment
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [hasShownAuthModal, setHasShownAuthModal] = useState(false);
  
  const [createOrderMutation, {isSuccess, isLoading, isError}] = useCreateOrderMutation();
  
  // Check if user is accessing wrong route and redirect
  useEffect(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
    const hasValidAuth = Boolean(
      isAuthenticated && 
      user && 
      user.id && 
      token && 
      token.trim() !== '' &&
      token !== 'null' &&
      token !== 'undefined'
    );
    
    // If authenticated user is on /checkout/guest, redirect to /checkout
    if (hasValidAuth && location.pathname === '/checkout/guest') {
      navigate('/checkout', { replace: true });
    }
    // If guest user is on /checkout, redirect to /checkout/guest
    else if (!hasValidAuth && location.pathname === '/checkout') {
      navigate('/checkout/guest', { replace: true });
    }
  }, [isAuthenticated, user, location.pathname, navigate]);
  
  // Show auth modal for guest users on first visit to checkout
  useEffect(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
    const hasValidAuth = Boolean(
      isAuthenticated && 
      user && 
      user.id && 
      token && 
      token.trim() !== '' &&
      token !== 'null' &&
      token !== 'undefined'
    );
    
    // Show auth modal for guest users if not already shown and cart has items
    if (!hasValidAuth && !hasShownAuthModal && reduxCartItems.length > 0) {
      setShowAuthModal(true);
      setHasShownAuthModal(true);
    }
  }, [isAuthenticated, user, reduxCartItems.length, hasShownAuthModal]);

  // Pre-fill contact info for authenticated users
  useEffect(() => {
    if (isAuthenticated && user) {
      setContact({
        email: user.email || '',
        phone: user.phone || '',
        full_name: user.full_name || user.name || ''
      });

      if (user.address || user.default_address) {
        const address = user.address || user.default_address;
        setShipTo({
          province: address.province || user.province || '',
          city: address.city || user.city || '',
          postal_code: address.postal_code || address.postalCode || '',
          address_line_1: address.address_line_1 || address.addressLine1 || address.street || '',
          address_line_2: address.address_line_2 || address.addressLine2 || ''
        });
      }
    }
  }, [isAuthenticated, user]);
  
  // Handle auth success - redirect to authenticated checkout
  const handleAuthSuccess = () => {
    // User logged in, redirect to authenticated checkout
    navigate('/checkout', { replace: true });
  };
  
  // Handle continue as guest
  const handleContinueAsGuest = () => {
    // User chose to continue as guest, just close modal
    setShowAuthModal(false);
  };

  // Load cart items from Redux store
  useEffect(() => {
    // Load from Redux cart slice (which syncs with localStorage)
    const formattedItems = reduxCartItems.map(item => ({
      listing_id: item.listing_id || item.id,
      title: item.title,
      price: item.price || item.price_per_unit || 0,
      qty: item.qty || item.quantity || 1,
      species: item.species || 'livestock',
      product_type: item.product_type || 'animal'
    }));

    setItems(formattedItems);
    
    // If cart is empty, redirect to cart page
    if (formattedItems.length === 0 && location.pathname !== '/cart') {
      toast({
        title: "Cart is empty",
        description: "Please add items to your cart before checkout",
        variant: "destructive",
      });
      navigate('/cart');
      return;
    }
    
    setQuote(null);
    setRisk(null);
    setStep('details');
  }, [location.key, reduxCartItems, navigate, toast, location.pathname]);

  // Fetch quote
  const getQuote = async () => {
    if (!shipTo || !items.length) return;

    setLoading(true);
    setError('');

    try {
      const endpoint = isAuthenticated ? '/checkout/quote' : '/checkout/guest/quote';
      const quoteData = await api.post(endpoint, { items, ship_to: shipTo });

      setQuote(quoteData);
      setRisk(quoteData.risk);
      setStep('quote');
    } catch (error) {
      console.error('Quote error:', error);
      setError(handleAPIError(error, false));
    } finally {
      setLoading(false);
    }
  };

 
  // Load cart items from Redux store
  useEffect(() => {
    // Load from Redux cart slice (which syncs with localStorage)
    const formattedItems = reduxCartItems.map(item => ({
      listing_id: item.listing_id || item.id,
      title: item.title,
      price: item.price || item.price_per_unit || 0,
      qty: item.qty || item.quantity || 1,
      species: item.species || 'livestock',
      product_type: item.product_type || 'animal'
    }));

    setItems(formattedItems);
    
    // If cart is empty, redirect to cart page
    if (formattedItems.length === 0 && location.pathname !== '/cart') {
      toast({
        title: "Cart is empty",
        description: "Please add items to your cart before checkout",
        variant: "destructive",
      });
      navigate('/cart');
      return;
    }
    
    setQuote(null);
    setRisk(null);
    setStep('details');
  }, [location.key, reduxCartItems, navigate, toast, location.pathname]);

  const createOrder = async () => {
  setError('');
  
  // 1️⃣ Check cart
  if (!items || items.length === 0) {
    return setError('Cart is empty');
  }

  // 2️⃣ Check quote
  if (!quote) {
    return setError('Please get quote first');
  }

  // 3️⃣ Validate shipTo
  if (
    !shipTo ||
    !shipTo.address_line_1 ||
    !shipTo.city ||
    !shipTo.province ||       // added province check
    shipTo.lat == null ||
    shipTo.lng == null
  ) {
    return setError('Delivery address is incomplete');
  }

  // 4️⃣ Normalize items
 const normalizedItems = items.map(item => ({
  listing_id: item.listing_id,
  qty: item.qty || 1,
  species: item.species || 'livestock',
  product_type: item.product_type || 'animal',
  line_total: (item.price || 0) * (item.qty || 1)  // ✅ never None
}));


  // 5️⃣ Build payload
  const payload = isAuthenticated
    ? {
        ship_to: {
          address_line_1: shipTo.address_line_1,
          address_line_2: shipTo.address_line_2 || '',
          city: shipTo.city,
          province: shipTo.province,
          postal_code: shipTo.postal_code || '',
          lat: shipTo.lat,
          lng: shipTo.lng
        },
        items: normalizedItems,
        quote
      }
    : {
        contact: {
          full_name: contact.full_name,
          email: contact.email,
          phone: contact.phone
        },
        ship_to: {
          address_line_1: shipTo.address_line_1,
          address_line_2: shipTo.address_line_2 || '',
          city: shipTo.city,
          province: shipTo.province,
          postal_code: shipTo.postal_code || '',
          lat: shipTo.lat,
          lng: shipTo.lng
        },
        items: normalizedItems,
        quote
      };

  console.log('FINAL ORDER PAYLOAD', payload); // ✅ check before sending

  // 🧪 TEST MODE: Bypass payment for testing
  const TEST_MODE = true; // Set to false to enable real payments
  
  // 6️⃣ Send order
  setLoading(true);
  try {
    const result = await createOrderMutation(payload).unwrap();
    console.log('ORDER SUCCESS', result);

    // 🧪 TEST MODE: Skip payment redirect and show success
    if (TEST_MODE) {
      toast({
        title: "✅ Order Created Successfully (Test Mode)",
        description: `Order ${result?.order_group_id || result?.id || 'created'} has been created. Payment bypassed for testing.`,
      });
      
      // Redirect to order confirmation or orders page
      setTimeout(() => {
        if (result?.order_group_id) {
          navigate(`/orders/${result.order_group_id}`, { replace: true });
        } else if (result?.id) {
          navigate(`/orders/${result.id}`, { replace: true });
        } else {
          navigate('/orders', { replace: true });
        }
      }, 2000);
      
      return;
    }

    // Production mode: Handle payment redirect
    if (result?.authorization_url) {
      console.log('Redirecting to payment:', result.authorization_url);
      window.location.href = result.authorization_url;
    } else {
      // If no payment URL, assume order is complete
      toast({
        title: "Order Created Successfully",
        description: "Your order has been placed successfully.",
      });
      navigate('/orders', { replace: true });
    }
  } catch (err) {
    console.error('ORDER ERROR', err);
    setError(handleAPIError(err, false));
  } finally {
    setLoading(false);
  }
};



  // Risk Badge

//  onChange={async (newLocation) => {
//   setShipTo(newLocation);
//   setAddresses(prev => [...prev, newLocation]);

//   try {
//     await addAddress(newLocation).unwrap(); // API call
//   } catch (err) {
//     console.error('Error saving address:', err);
//   }
// }}

// const handleLocationChange = async (newLocation) => {
//   setShipTo(newLocation);
//   setAddresses(prev => [...prev, newLocation]);

//   if (addAddress) {
//     try {
//       await addAddress(newLocation).unwrap(); // Ensure addAddress exists
//     } catch (err) {
//       console.error('Error saving address:', err);
//     }
//   }
// };

 // 🔥 FIXED function for live location + localStorage + API save
const handleLocationChange = (newLocation) => {
  const normalized = {
    id: Date.now(), // 🔑 unique id for edit/delete
    address_line_1: newLocation.address || newLocation.address_line_1 || '',
    address_line_2: newLocation.address_line_2 || '',
    city:
      newLocation.admin_area_2 ||
      newLocation.locality ||
      newLocation.town ||
      (newLocation.address?.split(',')[0] || ''),
    province:
      newLocation.administrative_area_level_1 ||
      newLocation.province ||
      newLocation.state ||
      '',
    postal_code: newLocation.postal_code || '',
    lat: newLocation.lat,
    lng: newLocation.lng,
    is_default: true
  };

  // ✅ set to state (checkout use)
  setShipTo(normalized);

  // ✅ save to localStorage (address page use)
  const existing = JSON.parse(localStorage.getItem('addresses') || '[]');

  const updated = [
    normalized,
    ...existing.filter(a => a.address_line_1 !== normalized.address_line_1)
  ];

  localStorage.setItem('addresses', JSON.stringify(updated));

  console.log('Saved address', normalized);
};

  const getRiskBadge = (riskData) => {
    if (!riskData) return null;
    const category = getRiskCategory(riskData.score);
    const riskInfo = RISK_CATEGORIES[category];
    return <Badge className={riskInfo.color}>{riskInfo.label}</Badge>;
  };


  return (
      <div className="min-h-screen bg-gradient-to-br from-emerald-50 via-green-50 to-emerald-100">
      <Header />
      <div className="container mx-auto px-4 py-8">
        <div className="max-w-6xl mx-auto">
          <LocationPicker value={shipTo} onChange={handleLocationChange} />
          {/* Header */}
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold text-gray-900 mb-2">
              {isAuthenticated ? 'Checkout' : 'Guest Checkout'}
            </h1>
            <p className="text-gray-600">
              {isAuthenticated 
                ? 'Review your order and complete your purchase'
                : 'Complete your livestock purchase without creating an account'}
            </p>
            <div className="flex items-center justify-center space-x-2 mt-4">
              <Badge variant="outline" className="text-emerald-600">🔒 Secure Escrow</Badge>
              {isAuthenticated ? (
                <Badge variant="outline" className="text-emerald-600">⚡ Quick Checkout</Badge>
              ) : (
                <>
                  <Badge variant="outline" className="text-emerald-600">📱 No Account Needed</Badge>
                  <Badge variant="outline" className="text-emerald-600">⚡ Quick Checkout</Badge>
                </>
              )}
            </div>
          </div>

          {error && (
            <Alert className="mb-6 border-red-200 bg-red-50">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription className="text-red-700">{error}</AlertDescription>
            </Alert>
          )}

          <div className="grid lg:grid-cols-3 gap-8">
            {/* Main Checkout Form */}
            <div className="lg:col-span-2 space-y-6">
              
              {/* Step 1: Delivery & Contact Details */}
              <Card className={step === 'details' ? 'border-emerald-500 shadow-lg' : ''}>
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
                      step === 'details' ? 'bg-emerald-600 text-white' : 
                      shipTo && contact.email ? 'bg-green-600 text-white' : 'bg-gray-200'
                    }`}>
                      {shipTo && contact.email ? <CheckCircle className="h-5 w-5" /> : '1'}
                    </div>
                    <span>Delivery & Contact Information</span>
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-6">
                  {/* Delivery Address */}
                  <div>
                    <Label className="text-base font-semibold mb-3 flex items-center">
                      <MapPin className="h-4 w-4 mr-2" />
                      Delivery Address
                    </Label>
                    {/* <LocationPicker 
                      // value={shipTo}
                      // onChange={setShipTo}
                      // placeholder="Select your delivery location"
                      // className="w-full"

                      // value={shipTo}
                      //  onChange={(newLocation) => handleLocationChange(newLocation)}
                    /> */}

                    <LocationPicker
                      value={shipTo}
                      onChange={handleLocationChange}
                    />
                    <p className="text-xs text-gray-500 mt-2">
                      Your exact address is never shared with sellers until payment is confirmed
                    </p>
                  </div>

                  <Separator />

                  {/* Contact Information */}
                  <div>
                    <Label className="text-base font-semibold mb-3 flex items-center">
                      <User className="h-4 w-4 mr-2" />
                      Contact Information
                      {isAuthenticated && (
                        <Badge variant="outline" className="ml-2 text-xs">Pre-filled from your profile</Badge>
                      )}
                    </Label>
                    <div className="grid md:grid-cols-3 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor="full_name">Full Name {isAuthenticated && '(from profile)'}</Label>
                        <Input
                          id="full_name"
                          value={contact.full_name}
                          onChange={(e) => setContact(prev => ({ ...prev, full_name: e.target.value }))}
                          placeholder="John van der Merwe"
                          readOnly={isAuthenticated}
                          className={isAuthenticated ? 'bg-gray-50 cursor-not-allowed' : ''}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="email">Email * {isAuthenticated && '(from profile)'}</Label>
                        <Input
                          id="email"
                          type="email"
                          value={contact.email}
                          onChange={(e) => setContact(prev => ({ ...prev, email: e.target.value }))}
                          placeholder="john@example.com"
                          required
                          readOnly={isAuthenticated}
                          className={isAuthenticated ? 'bg-gray-50 cursor-not-allowed' : ''}
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="phone">Phone {isAuthenticated && '(from profile)'}</Label>
                        <Input
                          id="phone"
                          value={contact.phone}
                          onChange={(e) => setContact(prev => ({ ...prev, phone: e.target.value }))}
                          placeholder="+27 12 345 6789"
                          readOnly={isAuthenticated}
                          className={isAuthenticated ? 'bg-gray-50 cursor-not-allowed' : ''}
                        />
                      </div>
                    </div>
                    {isAuthenticated && (
                      <p className="text-xs text-gray-500 mt-2">
                        To update your contact information, please visit your{' '}
                        <a href="/profile" className="text-emerald-600 hover:underline">profile page</a>
                      </p>
                    )}
                  </div>

                  <Button 
                    onClick={getQuote}
                    disabled={!shipTo || (!isAuthenticated && !contact.email) || loading}
                    className="w-full bg-emerald-600 hover:bg-emerald-700"
                  >
                    {loading ? (
                      <>
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        Getting Quote...
                      </>
                    ) : (
                      'Get Quote & Continue'
                    )}
                  </Button>
                </CardContent>
              </Card>

              {/* Step 2: Order Review & Risk Assessment */}
              {quote && (
                <Card className={step === 'quote' ? 'border-emerald-500 shadow-lg' : ''}>
                  <CardHeader>
                    <CardTitle className="flex items-center space-x-2">
                      <div className="w-8 h-8 rounded-full bg-emerald-600 text-white flex items-center justify-center">
                        2
                      </div>
                      <span>Order Review</span>
                      {risk && getRiskBadge(risk)}
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {/* Risk Assessment Display */}
                    {risk && (
                      <div className={`p-4 rounded-lg border ${
                        risk.gate === 'BLOCK' ? 'bg-red-50 border-red-200' :
                        risk.gate === 'STEPUP' ? 'bg-yellow-50 border-yellow-200' :
                        'bg-green-50 border-green-200'
                      }`}>
                        <div className="flex items-start space-x-3">
                          <Shield className={`h-5 w-5 mt-0.5 ${
                            risk.gate === 'BLOCK' ? 'text-red-600' :
                            risk.gate === 'STEPUP' ? 'text-yellow-600' :
                            'text-green-600'
                          }`} />
                          <div>
                            <h4 className={`font-semibold ${
                              risk.gate === 'BLOCK' ? 'text-red-900' :
                              risk.gate === 'STEPUP' ? 'text-yellow-900' :
                              'text-green-900'
                            }`}>
                              {risk.gate === 'BLOCK' ? 'KYC Verification Required' :
                               risk.gate === 'STEPUP' ? 'Additional Verification May Be Required' :
                               'Order Approved for Guest Checkout'}
                            </h4>
                            <div className="text-sm mt-1 space-y-1">
                              {risk.reasons.map((reason, index) => (
                                <div key={index} className="flex items-center space-x-2">
                                  <div className="w-1 h-1 bg-current rounded-full"></div>
                                  <span>{reason}</span>
                                </div>
                              ))}
                            </div>
                            {risk.gate === 'STEPUP' && (
                              <p className="text-xs mt-2 opacity-80">
                                You can complete this purchase now. Additional verification may be requested before delivery.
                              </p>
                            )}
                            {risk.gate === 'BLOCK' && (
                              <p className="text-xs mt-2 opacity-80">
                                These items require full account verification. Please create an account to continue.
                              </p>
                            )}
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Order Summary */}
                    <div className="space-y-4">
                      {quote.sellers.map((seller, index) => (
                        <div key={index} className="border rounded-lg p-4">
                          <div className="flex items-center justify-between mb-3">
                            <h4 className="font-semibold">Seller {seller.seller_id.substring(0, 8)}...</h4>
                            <Badge variant="outline">
                              {seller.items.length} item{seller.items.length !== 1 ? 's' : ''}
                            </Badge>
                          </div>
                          
                          <div className="space-y-2">
                            {seller.items.map((item, itemIndex) => (
                              <div key={itemIndex} className="flex items-center justify-between text-sm">
                                <div>
                                  <span className="font-medium">{item.title}</span>
                                  <span className="text-gray-500 ml-2">× {item.qty}</span>
                                </div>
                                <span className="font-medium">R{Number(item.line_total).toFixed(2)}</span>
                              </div>
                            ))}
                          </div>
                          
                          <Separator className="my-3" />
                          <div className="flex items-center justify-between text-sm">
                            <span>Delivery:</span>
                            <span>R{Number(seller.delivery).toFixed(2)}</span>
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* Payment Summary with Full Fee Breakdown */}
                    <div className="bg-gray-50 p-4 rounded-lg">
                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <span>Subtotal:</span>
                          <span>R{Number(quote.summary.subtotal).toFixed(2)}</span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span>Delivery:</span>
                          <span>R{Number(quote.summary.delivery_total || 0).toFixed(2)}</span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span>Processing Fee (1.5%):</span>
                          <span>R{Number(quote.summary.buyer_processing_fee || (quote.summary.subtotal * 0.015)).toFixed(2)}</span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span>Escrow Service Fee:</span>
                          <span>R{Number(quote.summary.escrow_service_fee || 25.00).toFixed(2)}</span>
                        </div>
                        <Separator />
                        <div className="flex items-center justify-between text-lg font-semibold">
                          <span>Total:</span>
                          <span>R{Number(quote.summary.grand_total).toFixed(2)}</span>
                        </div>
                      </div>
                    </div>

                    <Button 
                      onClick={createOrder}
                      disabled={loading || risk?.gate === 'BLOCK'}
                      className="w-full bg-gradient-to-r from-emerald-600 to-green-600 hover:from-emerald-700 hover:to-green-700"
                    >
                      {loading ? (
                        <>
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                          Creating Order...
                        </>
                      ) : (
                        <>
                          <CreditCard className="h-4 w-4 mr-2" />
                          Pay Securely with Escrow
                        </>
                      )}
                    </Button>
                  </CardContent>
                </Card>
              )}
            </div>

            {/* Sidebar */}
            <div className="space-y-6">
              {/* Cart Summary */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2">
                    <ShoppingCart className="h-5 w-5" />
                    <span>Cart Summary</span>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {items.length > 0 ? (
                    <div className="space-y-3">
                      {items.map((item) => (
                        <div key={item.listing_id} className="flex items-center justify-between text-sm">
                          <div>
                            <div className="font-medium">{item.title}</div>
                            <div className="text-gray-500">Qty: {item.qty}</div>
                          </div>
                          <div className="text-right">
                            <div className="font-medium">R{(item.price * item.qty).toFixed(2)}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-4 text-gray-500">
                      <Package className="h-8 w-8 mx-auto mb-2 text-gray-300" />
                      <p>Your cart is empty</p>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Security & Trust */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center space-x-2">
                    <Shield className="h-5 w-5" />
                    <span>Secure Checkout</span>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3 text-sm">
                    <div className="flex items-center space-x-2">
                      <CheckCircle className="h-4 w-4 text-green-600" />
                      <span>Escrow payment protection</span>
                    </div>
                    <div className="flex items-center space-x-2">
                      <CheckCircle className="h-4 w-4 text-green-600" />
                      <span>Seller details hidden until payment</span>
                    </div>
                    <div className="flex items-center space-x-2">
                      <CheckCircle className="h-4 w-4 text-green-600" />
                      <span>Automatic account creation</span>
                    </div>
                    <div className="flex items-center space-x-2">
                      <CheckCircle className="h-4 w-4 text-green-600" />
                      <span>Order tracking included</span>
                    </div>
                  </div>
                  
                  <div className="mt-4 p-3 bg-gray-50 rounded-md">
                    <p className="text-xs text-gray-600">
                      By continuing, you agree to our Terms of Service and Privacy Policy. 
                      An account will be automatically created for order tracking.
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      </div>
      <Footer />
      
      {/* Checkout Auth Modal */}
      <CheckoutAuthModal
        open={showAuthModal}
        onClose={() => setShowAuthModal(false)}
        onContinueAsGuest={handleContinueAsGuest}
        onAuthSuccess={handleAuthSuccess}
      />
    </div>
  );
}
