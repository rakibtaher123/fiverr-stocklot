import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui';
import { Button } from '@/components/ui';
import { Input } from '@/components/ui';
import { 
  ShoppingCart, Trash2, Plus, Minus, ArrowRight, 
  MapPin, Package, AlertCircle, CheckCircle
} from 'lucide-react';
import { useAuth } from '../auth/AuthProvider';
import {
  useGetCartQuery,
  useUpdateCartItemMutation,
  useRemoveFromCartMutation
} from '../store/api/cart.api';
import { 
  selectCartItems, 
  removeItem, 
  updateItemQuantity, 
  syncFromAPI 
} from '../store/cartSlice';
import Header from '@/components/ui/common/Header';
import Footer from '@/components/ui/common/Footer';

function CartPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const dispatch = useDispatch();
  const [updating, setUpdating] = useState({});
  
  // Get cart items from Redux store
  const reduxCartItems = useSelector(selectCartItems);
  
  // Use Redux RTK Query hooks for authenticated users (to sync with backend)
  const { data: cartData, isLoading: loading, isError: cartError, refetch } = useGetCartQuery(undefined, {
    skip: !user, // Skip query if user is not authenticated
  });
  
  // Sync Redux cart with API cart when authenticated user's cart is loaded
  useEffect(() => {
    if (user && cartData?.items) {
      dispatch(syncFromAPI(cartData));
    }
  }, [user, cartData, dispatch]);
  
  console.log('cartData', cartData);  
  
  const [updateCartItem] = useUpdateCartItemMutation();
  const [removeFromCartAPI] = useRemoveFromCartMutation();
  
  // Refresh authenticated user's cart when component mounts, user changes, or location changes
  useEffect(() => {
    if (user && refetch) {
      refetch();
    }
  }, [user, refetch, location.pathname]);
  
  // Listen for cart refetch events for authenticated users
  useEffect(() => {
    if (user) {
      const handleCartRefetch = () => {
        if (refetch) {
          refetch();
        }
      };
      
      window.addEventListener('cartRefetch', handleCartRefetch);
      
      return () => {
        window.removeEventListener('cartRefetch', handleCartRefetch);
      };
    }
  }, [user, refetch]);

  // Normalize cart items from Redux store
  const cartItems = useMemo(() => {
    return reduxCartItems.map(item => ({
      id: item.id || item.listing_id,
      listing_id: item.listing_id,
      title: item.title || 'Unknown Item',
      price: item.price || item.price_per_unit || 0,
      quantity: item.qty || item.quantity || 1,
      qty: item.qty || item.quantity || 1,
      image: item.image,
      location: item.location,
      seller_name: item.seller_name,
    }));
  }, [reduxCartItems]);
  
  // Debug log
  useEffect(() => {
    console.log('🛒 CartPage: Final cartItems:', cartItems);
    console.log('🛒 CartPage: cartItems.length:', cartItems.length);
  }, [cartItems]);
  
  // Listen for cart updates from other components
  useEffect(() => {
    const handleCartUpdate = () => {
      // Cart is already in Redux, no need to reload
      console.log('🛒 CartPage: Cart updated event received');
    };
    
    window.addEventListener('cartUpdated', handleCartUpdate);
    window.addEventListener('cartRefetch', () => {
      if (user && refetch) {
        refetch();
      }
    });
    
    return () => {
      window.removeEventListener('cartUpdated', handleCartUpdate);
    };
  }, [user, refetch]);

  const updateQuantity = async (itemId, newQuantity) => {
    if (newQuantity < 1) return;

    setUpdating(prev => ({ ...prev, [itemId]: true }));
    
    try {
      // Update Redux cart slice
      dispatch(updateItemQuantity({ itemId, quantity: newQuantity }));
      
      // If authenticated, also sync with backend
      if (user) {
        try {
          await updateCartItem({ itemId, quantity: newQuantity }).unwrap();
          refetch();
          // Trigger header cart update
          window.dispatchEvent(new CustomEvent('cartRefetch', {}));
        } catch (apiError) {
          console.error('Error updating cart on backend:', apiError);
          // Continue with local update even if API fails
        }
      } else {
        // Update header cart count for guest
        window.dispatchEvent(new CustomEvent('cartUpdated', {}));
      }
    } catch (error) {
      console.error('Error updating quantity:', error);
    } finally {
      setUpdating(prev => ({ ...prev, [itemId]: false }));
    }
  };

  const handleRemoveItem = async (itemId) => {
    try {
      // Remove from Redux cart slice
      dispatch(removeItem(itemId));
      
      // If authenticated, also sync with backend
      if (user) {
        try {
          await removeFromCartAPI(itemId).unwrap();
          refetch();
          // Trigger header cart update
          window.dispatchEvent(new CustomEvent('cartRefetch', {}));
        } catch (apiError) {
          console.error('Error removing item from backend:', apiError);
          // Continue with local removal even if API fails
        }
      } else {
        // Update header cart count for guest
        window.dispatchEvent(new CustomEvent('cartUpdated', {}));
      }
    } catch (error) {
      console.error('Error removing item:', error);
    }
  };

  const calculateTotal = () => {
    return cartItems.reduce((total, item) => {
      const price = item.price || item.price_per_unit || 0;
      const quantity = item.quantity || item.qty || 1;
      return total + (price * quantity);
    }, 0);
  };

  const proceedToCheckout = () => {
    if (user) {
      navigate('/checkout');
    } else {
      navigate('/checkout/guest');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-600"></div>
      </div>
    );
  }

  // Show empty state only if we're sure there are no items
  if (cartItems.length === 0 && !loading) {
    return (
      <div className="min-h-screen bg-gray-50 py-8">
        <div className="max-w-4xl mx-auto px-4">
          <Card>
            <CardContent className="text-center py-16">
              <ShoppingCart className="h-16 w-16 text-gray-400 mx-auto mb-4" />
              <h2 className="text-2xl font-bold text-gray-900 mb-2">Your cart is empty</h2>
              <p className="text-gray-600 mb-6">Browse our marketplace to find livestock for your farm.</p>
              <Button 
                onClick={() => navigate('/marketplace')}
                className="bg-emerald-600 hover:bg-emerald-700"
              >
                Browse Marketplace
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <>
    <Header />
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="max-w-6xl mx-auto px-4">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Cart Items */}
          <div className="lg:col-span-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <ShoppingCart className="h-5 w-5" />
                  Shopping Cart ({cartItems.length} {cartItems.length === 1 ? 'item' : 'items'})
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {cartItems.map((item) => {
                  const itemId = item.id || item.listing_id || item.item_id;
                  const price = item.price || item.price_per_unit || 0;
                  const quantity = item.quantity || item.qty || 1;
                  const title = item.title || item.listing_title || item.name || 'Unknown Item';
                  const location = item.location || item.province || item.seller_location || '';
                  const imageUrl = item.image_url || item.image || (item.images && item.images[0]);
                  
                  return (
                    <div key={itemId} className="border border-gray-200 rounded-lg p-4">
                      <div className="flex flex-col sm:flex-row gap-4">
                        {/* Item Image */}
                        <div className="w-full sm:w-24 h-24 bg-gray-200 rounded-lg flex items-center justify-center">
                          {imageUrl ? (
                            <img 
                              src={imageUrl} 
                              alt={title}
                              className="w-full h-full object-cover rounded-lg"
                            />
                          ) : (
                            <Package className="h-8 w-8 text-gray-400" />
                          )}
                        </div>

                        {/* Item Details */}
                        <div className="flex-1">
                          <h3 className="font-semibold text-gray-900">{title}</h3>
                          {location && (
                            <p className="text-sm text-gray-600 flex items-center gap-1 mt-1">
                              <MapPin className="h-3 w-3" />
                              {location}
                            </p>
                          )}
                          <p className="text-lg font-bold text-emerald-600 mt-2">
                            R{price.toLocaleString()} each
                          </p>
                        </div>

                        {/* Quantity Controls - Enhanced for visibility */}
                        <div className="flex items-center gap-3 bg-gray-50 p-2 rounded-lg">
                          <span className="text-sm text-gray-600 font-medium">Qty:</span>
                          <div className="flex items-center border-2 border-emerald-300 rounded-lg bg-white">
                            <button
                              onClick={() => updateQuantity(itemId, quantity - 1)}
                              disabled={quantity <= 1 || updating[itemId]}
                              className="px-3 py-2 text-emerald-600 hover:bg-emerald-50 disabled:opacity-50 disabled:cursor-not-allowed rounded-l-lg border-r border-emerald-200 font-bold text-lg"
                              type="button"
                              aria-label="Decrease quantity"
                            >
                              −
                            </button>
                            
                            <input
                              type="number"
                              value={quantity}
                              onChange={(e) => {
                                const newQty = parseInt(e.target.value) || 1;
                                if (newQty >= 1) {
                                  updateQuantity(itemId, newQty);
                                }
                              }}
                              className="w-16 text-center py-2 border-0 focus:ring-0 text-gray-900 font-semibold"
                              min="1"
                              aria-label="Quantity"
                            />
                            
                            <button
                              onClick={() => updateQuantity(itemId, quantity + 1)}
                              disabled={updating[itemId]}
                              className="px-3 py-2 text-emerald-600 hover:bg-emerald-50 disabled:opacity-50 rounded-r-lg border-l border-emerald-200 font-bold text-lg"
                              type="button"
                              aria-label="Increase quantity"
                            >
                              +
                            </button>
                          </div>

                          {/* Remove Button - Enhanced visibility */}
                          <button
                            onClick={() => handleRemoveItem(itemId)}
                            className="px-3 py-2 text-red-600 hover:bg-red-50 rounded-lg border border-red-200 hover:border-red-300 transition-colors"
                            type="button"
                            title="Remove item"
                            aria-label="Remove item from cart"
                          >
                            <Trash2 className="h-5 w-5" />
                          </button>
                        </div>
                      </div>

                      {/* Item Total */}
                      <div className="mt-3 pt-3 border-t border-gray-100">
                        <div className="flex justify-between items-center">
                          <span className="text-sm text-gray-600">Subtotal for this item:</span>
                          <span className="font-semibold text-gray-900">
                            R{(price * quantity).toLocaleString()}
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          </div>

          {/* Order Summary */}
          <div className="lg:col-span-1">
            <Card className="sticky top-4">
              <CardHeader>
                <CardTitle>Order Summary</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Subtotal:</span>
                    <span className="font-semibold">R{calculateTotal().toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between text-sm text-gray-500">
                    <span>Delivery:</span>
                    <span>Calculated at checkout</span>
                  </div>
                  <div className="flex justify-between text-sm text-gray-500">
                    <span>Processing Fee (1.5%):</span>
                    <span>Calculated at checkout</span>
                  </div>
                  <div className="border-t pt-2">
                    <div className="flex justify-between text-lg font-bold">
                      <span>Total:</span>
                      <span>R{calculateTotal().toLocaleString()}+</span>
                    </div>
                    <p className="text-xs text-gray-500 mt-1">Final total calculated at checkout</p>
                  </div>
                </div>

                <Button 
                  onClick={proceedToCheckout}
                  className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-3 text-lg"
                  disabled={cartItems.length === 0}
                >
                  Proceed to Checkout
                  <ArrowRight className="h-5 w-5 ml-2" />
                </Button>

                {!user && (
                  <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                    <div className="flex items-start gap-2">
                      <AlertCircle className="h-4 w-4 text-blue-600 mt-0.5" />
                      <div className="text-sm">
                        <p className="text-blue-800 font-medium">Guest Checkout</p>
                        <p className="text-blue-600">You can complete your purchase as a guest or login for a faster checkout experience.</p>
                      </div>
                    </div>
                  </div>
                )}

                <div className="text-xs text-gray-500 space-y-1">
                  <div className="flex items-center gap-1">
                    <CheckCircle className="h-3 w-3 text-green-600" />
                    <span>Secure checkout with escrow protection</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <CheckCircle className="h-3 w-3 text-green-600" />
                    <span>Direct contact with sellers after purchase</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <CheckCircle className="h-3 w-3 text-green-600" />
                    <span>Delivery or collection arrangements</span>
                  </div>
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
}

export default CartPage;