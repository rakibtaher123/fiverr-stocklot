import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { useDispatch } from 'react-redux';
import ImageGallery from './ImageGallery';
import SellerCard from './SellerCard';
import RatingSummary from './RatingSummary';
import Certificates from './Certificates';
import GeofenceBanner from './GeofenceBanner';
import ReviewsList from './ReviewsList';
import RelatedGrid from './RelatedGrid';
import AskQuestionButton from './AskQuestionButton';
import GroupBuyWidget from '../features/GroupBuyWidget';
import AuctionWidget from '../features/AuctionWidget';
import TrustScoreDisplay from '../features/TrustScoreDisplay';
import { IfFlag } from '../../providers/FeatureFlagsProvider';
import { useAuth } from '../../auth/AuthProvider';
import { useToast } from '../../hooks/use-toast';
// import apifrom '../../api/client'; // Use centralized API client
import { useGetListingPDPQuery } from '../../store/api/listings.api';
import { useTrackAnalyticsMutation, useGetABTestConfigQuery, useTrackABEventMutation } from '../../store/api/admin.api';
import { useAddToCartMutation, useLazyGetCartQuery } from '../../store/api/cart.api';
import { addItem as addItemToCart, setCart } from '../../store/cartSlice';
import Header from '../ui/common/Header';
import Footer from '../ui/common/Footer';

const ListingPDP = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const dispatch = useDispatch();
  const { user, isAuthenticated } = useAuth();
  const { toast } = useToast();
  const [qty, setQty] = useState(1);
  const [addingToCart, setAddingToCart] = useState(false);
  
  // Use Redux RTK Query hooks
  const { data: responseData, isLoading: loading, error: queryError } = useGetListingPDPQuery(id);
  const { data: abConfigData } = useGetABTestConfigQuery(id, {
    skip: !id, // Skip if no id
  });
  const [trackAnalytics] = useTrackAnalyticsMutation();
  const [trackABEvent] = useTrackABEventMutation();
  // Only use cart mutation for authenticated users - use skip option
  const [addToCart, { isLoading: isAddingToCart }] = useAddToCartMutation();
  const [refetchCart] = useLazyGetCartQuery();
  
  // Get token to verify authentication status
  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  // Strict check: user must be authenticated, have user object with id, AND have a valid token
  const isUserAuthenticated = Boolean(
    isAuthenticated && 
    user && 
    user.id && 
    token && 
    token.trim() !== ''
  );

  // Extract data from response - handle both wrapped and direct responses
  const data = responseData?.data || responseData;
  const abConfig = abConfigData?.data || abConfigData || { layout: 'default', experiment_tracking: [] };
  const error = queryError ? (queryError.status === 404 ? 'Listing not found' : 'Error loading listing details') : null;

  // Normalize data with fallbacks
  const normalizedData = useMemo(() => {
    if (!data) return null;
    
    return {
      ...data,
      species: data.species || data.species_name || 'Livestock',
      breed: data.breed || data.breed_name || data.species || 'General',
      category_group: data.category_group || data.category || 'Livestock',
      category_group_id: data.category_group_id,
      product_type: data.product_type || data.category || 'Livestock',
      title: data.title || 'Untitled Listing',
      price: data.price || data.price_per_unit || 0,
      qty_available: data.qty_available || data.quantity || 0,
      unit: data.unit || 'head',
      description: data.description || '',
      media: data.media || data.images || [],
      location: data.location || {
        city: data.city || '',
        province: data.province || data.region || '',
        lat: data.lat || data.latitude || 0,
        lng: data.lng || data.longitude || 0
      },
      seller: data.seller || {},
      attributes: data.attributes || {},
      certificates: data.certificates || {},
      reviewSummary: data.reviewSummary || { average: 0, count: 0, breakdown: {} },
      similar: data.similar || []
    };
  }, [data]);

  const priceFmt = useMemo(() => 
    new Intl.NumberFormat('en-ZA', { style: 'currency', currency: 'ZAR' }), []
  );

  const handleTrackAnalytics = useCallback(async (eventType, eventData = {}) => {
    try {
      await trackAnalytics({
        event_type: eventType,
        listing_id: normalizedData?.id,
        user_id: normalizedData?.currentUserId || 'anonymous',
        metadata: eventData,
        timestamp: new Date().toISOString()
      }).unwrap();
    } catch (err) {
      console.error('Analytics error:', err);
      // Don't block user experience for analytics failures
    }
  }, [normalizedData, trackAnalytics]);

  const handleTrackABEvents = useCallback(async (eventType) => {
    if (!abConfig?.experiment_tracking?.length) return;
    
    try {
      for (const experiment of abConfig.experiment_tracking) {
        await trackABEvent({
          experiment_id: experiment.experiment_id,
          variant: experiment.variant,
          event_type: eventType,
          listing_id: normalizedData?.id,
          user_id: normalizedData?.currentUserId || 'anonymous',
          timestamp: new Date().toISOString()
        }).unwrap();
      }
    } catch (err) {
      console.error('A/B tracking error:', err);
      // Don't block user experience for tracking failures
    }
  }, [abConfig, normalizedData, trackABEvent]);

  useEffect(() => {
    // Track PDP view
    if (normalizedData) {
      handleTrackAnalytics('pdp_view', { listing_id: normalizedData.id });
      handleTrackABEvents('view');
    }
  }, [normalizedData, handleTrackAnalytics, handleTrackABEvents]);

  const handleAddToCart = useCallback(async (qtyParam = qty) => {
    if (!normalizedData) return;
    
    // Validate quantity
    if (qtyParam < 1 || qtyParam > normalizedData.qty_available) {
      toast({
        title: "Invalid Quantity",
        description: `Please enter a quantity between 1 and ${normalizedData.qty_available}`,
        variant: "destructive",
      });
      return;
    }
    
    setAddingToCart(true);
    
    try {
      // CRITICAL: Strict authentication check - must have user, auth status, AND valid token
      // This check MUST prevent API calls for guest users
      const hasValidAuth = Boolean(
        isAuthenticated && 
        user && 
        user.id && 
        token && 
        token.trim() !== '' &&
        token !== 'null' &&
        token !== 'undefined'
      );
      
      // Only call API if user is fully authenticated
      // Double-check: Never call API without valid token
      if (hasValidAuth && token && token.trim() !== '') {
        // Authenticated user - add to backend cart via API
        try {
          // Final safety check before API call
          const currentToken = localStorage.getItem('token');
          if (!currentToken || currentToken.trim() === '') {
            throw new Error('No token available');
          }
          
          const response = await addToCart({
            listing_id: normalizedData.id,
            quantity: qtyParam,
            price_per_unit: normalizedData.price,
          }).unwrap();
          
          console.log('🛒 Cart API response:', response);
          
          // Trigger cart refetch for header update
          // Use both refetch and custom event for reliability
          try {
            await refetchCart();
          } catch (cartError) {
            // Silently handle cart refetch errors - non-critical
            if (cartError?.status !== 401 && cartError?.data?.status !== 401) {
              console.warn('Failed to refetch cart:', cartError);
            }
          }
          // Also dispatch event to trigger header refetch
          window.dispatchEvent(new CustomEvent('cartRefetch', {}));
          
          // Show success toast
          toast({
            title: "Added to Cart!",
            description: `${normalizedData.title} (${qtyParam} ${normalizedData.unit}) added successfully`,
          });
          
          // Track analytics
          handleTrackAnalytics('add_to_cart', { 
            quantity: qtyParam, 
            price: normalizedData.price,
            listing_id: normalizedData.id,
            is_guest: false
          });
          handleTrackABEvents('conversion');
          
        } catch (apiError) {
          // If API call fails with 401 or any auth error, fall back to guest cart
          const is401 = apiError?.status === 401 || 
                       apiError?.data?.status === 401 || 
                       apiError?.error?.status === 401 ||
                       (apiError?.error && apiError.error.status === 401) ||
                       apiError?.message?.includes('401') ||
                       apiError?.message?.includes('Authentication') ||
                       apiError?.message?.includes('Unauthorized');
          
          if (is401 || apiError?.message === 'No token available') {
            console.log('🛒 API auth failed, using guest cart instead');
            // Fall through to guest cart logic - don't throw, just continue
          } else {
            // Re-throw non-401 errors to be handled below
            throw apiError;
          }
        }
      }
      
      // Guest user OR auth failed - add to Redux cart slice
      // This runs if user is not authenticated OR if API call failed with 401
      if (!hasValidAuth) {
        // Add to Redux cart slice (which syncs with localStorage)
        dispatch(addItemToCart({
          listing_id: normalizedData.id,
          title: normalizedData.title,
          price: normalizedData.price,
          qty: qtyParam,
          unit: normalizedData.unit || 'head',
          species: normalizedData.species,
          product_type: normalizedData.product_type,
          image: normalizedData.media?.[0]?.url || normalizedData.images?.[0],
          seller_id: normalizedData.seller_id || normalizedData.seller?.id,
          location: normalizedData.location?.province,
        }));
        
        // Update header cart count by dispatching a custom event
        window.dispatchEvent(new CustomEvent('cartUpdated', {}));
        
        // Show success toast for guest cart
        toast({
          title: "Added to Cart!",
          description: `${normalizedData.title} (${qtyParam} ${normalizedData.unit}) added successfully`,
        });
        
        // Track analytics for guest
        handleTrackAnalytics('add_to_cart', { 
          quantity: qtyParam, 
          price: normalizedData.price,
          listing_id: normalizedData.id,
          is_guest: true
        });
        handleTrackABEvents('conversion');
      }
    } catch (err) {
      // Handle errors - but guest cart operations should never throw errors
      const is401 = err?.status === 401 || err?.data?.status === 401 || 
                    err?.error?.status === 401 || err?.message?.includes('401');
      
      // Only log non-401 errors
      if (!is401) {
        console.error('🚨 Cart error:', err);
      }
      
      // Handle different error types
      let errorMessage = 'Failed to add item to cart. Please try again.';
      
      if (err?.status === 404 || err?.data?.status === 404 || err?.error?.status === 404) {
        errorMessage = 'Listing not found or no longer available';
      } else if (err?.status === 400 || err?.data?.status === 400 || err?.error?.status === 400) {
        errorMessage = err?.data?.detail || err?.error?.data?.detail || 'Invalid request. Please check your input.';
      } else if (err?.data?.detail) {
        errorMessage = err.data.detail;
      } else if (err?.error?.data?.detail) {
        errorMessage = err.error.data.detail;
      }
      
      // Only show error toast for non-401 errors
      // 401 errors are handled by falling back to guest cart
      if (!is401) {
        toast({
          title: "Error",
          description: errorMessage,
          variant: "destructive",
        });
      } else {
        // For 401, silently use guest cart (already handled above)
        console.log('🛒 Using guest cart due to authentication issue');
      }
    } finally {
      setAddingToCart(false);
    }
  }, [normalizedData, qty, addToCart, handleTrackAnalytics, handleTrackABEvents, isAuthenticated, user, token, toast, refetchCart, dispatch]);

  const buyNow = async () => {
    if (!normalizedData) return;
    
    console.log('🛒 PDP BUY NOW: Using proper checkout flow with fees');
    
    try {
      // Get token to check authentication
      const currentToken = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
      
      // Check authentication status
      const hasValidAuth = Boolean(
        isAuthenticated && 
        user && 
        user.id && 
        currentToken && 
        currentToken.trim() !== '' &&
        currentToken !== 'null' &&
        currentToken !== 'undefined'
      );
      
      // Create cart item
      const cartItem = {
        listing_id: normalizedData.id,
        title: normalizedData.title,
        price: parseFloat(normalizedData.price) || 0,
        qty: qty,
        unit: normalizedData.unit || 'head',
        species: normalizedData.species || 'livestock',
        product_type: normalizedData.product_type || 'animal',
        image: normalizedData.media?.[0]?.url || normalizedData.images?.[0],
        seller_id: normalizedData.seller_id || normalizedData.seller?.id,
        location: normalizedData.location?.province,
      };
      
      // Clear existing cart items with same listing_id and add new one
      // First, remove existing item from Redux if it exists
      const currentCartItems = JSON.parse(localStorage.getItem('cart') || '{"items":[]}');
      const filteredItems = (currentCartItems.items || []).filter(
        item => item.listing_id !== normalizedData.id
      );
      
      // Create new cart with only this item
      const newCart = { items: [cartItem] };
      localStorage.setItem('cart', JSON.stringify(newCart));
      
      // Update Redux cart - clear and add new item
      // We need to set the entire cart to just this one item
      dispatch(setCart({ items: [cartItem] }));
      
      console.log('🛒 Updated cart for buy now:', cartItem);
      
      // Navigate based on authentication status
      if (hasValidAuth) {
        navigate('/checkout');
      } else {
        navigate('/checkout/guest');
      }
      
      // Track analytics
      handleTrackAnalytics('buy_now_click', { 
        quantity: qty, 
        price: normalizedData.price,
        total_before_fees: normalizedData.price * qty,
        is_guest: !hasValidAuth
      });
      handleTrackABEvents('conversion');
      
    } catch (error) {
      console.error('🚨 Buy Now error:', error);
      
      toast({
        title: "Buy Now Error",
        description: `There was an issue processing your request. Please try again or add to cart first.`,
        variant: "destructive",
      });
    }
  };

  const requestDeliveryQuote = async () => {
    if (!normalizedData) return;
    
    try {
      handleTrackAnalytics('delivery_quote_request', { quantity: qty });
      
      const backendUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8001';
      await fetch(`${backendUrl}/api/logistics/rfq`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ listing_id: normalizedData.id, qty })
      });
      alert('Delivery quote request sent to transporters.');
    } catch (err) {
      console.error('Error requesting quote:', err);
      alert('Failed to send quote request');
    }
  };

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-6">
        <div className="animate-pulse">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-6">
              <div className="aspect-square bg-gray-200 rounded"></div>
            </div>
            <div className="lg:col-span-6 space-y-4">
              <div className="h-8 bg-gray-200 rounded w-3/4"></div>
              <div className="h-4 bg-gray-200 rounded w-1/2"></div>
              <div className="h-12 bg-gray-200 rounded w-1/4"></div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container mx-auto px-4 py-6">
        <div className="text-center py-12">
          <h1 className="text-2xl font-bold text-gray-800 mb-4">Listing Not Found</h1>
          <p className="text-gray-600 mb-6">{error}</p>
          <button 
            onClick={() => navigate('/marketplace')}
            className="px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700"
          >
            Back to Marketplace
          </button>
        </div>
      </div>
    );
  }

  if (!normalizedData) return null;

  const seoTitle = `${normalizedData.title} | ${normalizedData.category_group} · ${normalizedData.species} · ${normalizedData.location?.province} | StockLot`;

  // Breadcrumb navigation - Marketplace > Category > Listing Name
  const showCategoryBreadcrumb = normalizedData.category_group && normalizedData.category_group !== 'Livestock';

  return (
    <>
      <Header />
     
    <main className="container mx-auto px-4 py-6">
      {/* SEO Meta */}
      <title>{seoTitle}</title>
      
      {/* Breadcrumbs */}
      <nav className="text-sm text-gray-600 mb-4 flex items-center flex-wrap pt-4">
        <button 
          onClick={() => navigate('/marketplace')}
          className="hover:underline text-emerald-600 hover:text-emerald-700"
        >
          Marketplace
        </button>
        {showCategoryBreadcrumb && (
          <>
            <span className="mx-2 text-gray-400">›</span>
            <button 
              onClick={() => navigate(`/marketplace?category_group_id=${encodeURIComponent(normalizedData.category_group_id || '')}`)}
              className="hover:underline text-emerald-600 hover:text-emerald-700"
            >
              {normalizedData.category_group}
            </button>
          </>
        )}
        <span className="mx-2 text-gray-400">›</span>
        <span className="text-gray-900 font-medium line-clamp-1">{normalizedData.title}</span>
      </nav>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 lg:gap-6">
        {/* Gallery */}
        <div className="lg:col-span-6">
          <ImageGallery 
            media={normalizedData.media || []} 
            species={normalizedData.species}
            title={normalizedData.title}
          />
        </div>

        {/* Summary / CTA */}
        <div className="lg:col-span-6 space-y-3 lg:space-y-4">
          <h1 className="text-3xl font-bold text-gray-900">{normalizedData.title}</h1>
          
          <div className="text-sm text-gray-600">
            {normalizedData.species} {normalizedData.breed && normalizedData.breed !== normalizedData.species && `• ${normalizedData.breed}`} • {normalizedData.product_type}
          </div>

          <div className="flex items-end gap-3">
            <div className="text-4xl font-bold text-green-600">
              {priceFmt.format(normalizedData.price)}
            </div>
            <div className="text-lg text-gray-600">per {normalizedData.unit}</div>
          </div>

          <GeofenceBanner 
            inRange={normalizedData.in_range} 
            province={normalizedData.location?.province} 
          />

          <div className="flex items-center gap-3 py-2">
            <label className="text-sm font-medium">Quantity:</label>
            <input 
              type="number" 
              min={1} 
              max={normalizedData.qty_available} 
              value={qty}
              onChange={(e) => setQty(parseInt(e.target.value) || 1)}
              className="w-20 border border-gray-300 rounded px-3 py-1"
            />
            <div className="text-sm text-gray-600">
              {normalizedData.qty_available} available
            </div>
          </div>

          {/* Mobile-optimized action buttons with A/B testing support */}
          <div className={`grid gap-3 pt-4 ${
            abConfig?.cta_placement === 'bottom' 
              ? 'grid-cols-1' 
              : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-2'
          }`}>
            <button 
              onClick={() => handleAddToCart()}
              disabled={addingToCart || isAddingToCart || !normalizedData.qty_available}
              className={`px-4 sm:px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                abConfig?.cta_style === 'large' ? 'text-lg py-4' : ''
              }`}
            >
              {addingToCart || isAddingToCart ? 'Adding...' : 'Add to Cart'}
            </button>
            <button 
              onClick={buyNow}
              className="px-4 sm:px-6 py-3 border border-green-600 text-green-600 rounded-lg hover:bg-green-50 font-medium transition-colors"
            >
              Buy Now
            </button>
            <button 
              onClick={requestDeliveryQuote}
              className="px-4 sm:px-6 py-3 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 font-medium transition-colors sm:col-span-1"
            >
              Request Quote
            </button>
            <div className="sm:col-span-1">
              <AskQuestionButton listingId={normalizedData.id} />
            </div>
          </div>

          {/* StockLot Differentiator Features */}
          <div className="mt-6 space-y-4">
            {/* Group Buying Widget - Only show if feature is enabled */}
            <IfFlag flag="ff.group_buy">
              <GroupBuyWidget 
                listingId={normalizedData.id}
                sellerId={normalizedData.seller_id || normalizedData.seller?.id}
                targetCents={Math.round(normalizedData.price * 100)}
                onUpdate={(status) => {
                  // Silently handle updates
                }}
              />
            </IfFlag>
            
            {/* Auction Widget - Only show if feature is enabled */}
            <IfFlag flag="ff.auction">
              <AuctionWidget 
                listingId={normalizedData.id}
                sellerId={normalizedData.seller_id || normalizedData.seller?.id}
                startPrice={normalizedData.price}
                currentUserId={normalizedData.currentUserId}
                onUpdate={(status) => {
                  // Silently handle updates
                }}
              />
            </IfFlag>
          </div>

          {/* Seller */}
          <SellerCard seller={normalizedData.seller} listingId={normalizedData.id} />

          {/* Key attributes - Mobile optimized */}
          <section className="mt-4 lg:mt-6">
            <h2 className="text-lg lg:text-xl font-semibold mb-3">Key Details</h2>
            <div className="grid grid-cols-1 gap-2 lg:gap-4">
              {Object.entries(normalizedData.attributes || {}).map(([key, value]) => (
                <div key={key} className="flex justify-between items-center py-2 border-b border-gray-100 text-sm lg:text-base">
                  <span className="text-gray-600 font-medium">{key}:</span>
                  <span className="text-gray-900 text-right">{String(value)}</span>
                </div>
              ))}
            </div>
          </section>

          {/* Certificates */}
          <Certificates certs={normalizedData.certificates} />
        </div>
      </div>

      {/* Description & Reviews - Mobile optimized */}
      <section className="mt-8 lg:mt-12 grid grid-cols-1 lg:grid-cols-12 gap-4 lg:gap-6">
        <div className="lg:col-span-8">
          <div className="bg-white rounded-lg border p-4 lg:p-6 mb-6 lg:mb-8">
            <h2 className="text-xl lg:text-2xl font-semibold mb-3 lg:mb-4">Description</h2>
            <div className="prose prose-gray prose-sm lg:prose-base max-w-none">
              <p className="whitespace-pre-wrap text-sm lg:text-base leading-relaxed">{normalizedData.description}</p>
            </div>
          </div>

          {/* Reviews */}
          <div className="bg-white rounded-lg border p-4 lg:p-6 mb-4">
            <RatingSummary summary={normalizedData.reviewSummary} />
            <ReviewsList listingId={normalizedData.id} sellerId={normalizedData.seller?.id} />
          </div>
        </div>

        {/* Sidebar - Mobile responsive */}
        <aside className="lg:col-span-4 space-y-4 lg:space-y-6">
          <RelatedGrid items={normalizedData.similar || []} />
          
          {/* Trust Badge */}
          <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">
            <div className="flex items-center mb-2">
              <svg className="w-5 h-5 text-green-600 mr-2" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M2.166 4.999A11.954 11.954 0 0010 1.944 11.954 11.954 0 0017.834 5c.11.65.166 1.32.166 2.001 0 5.225-3.34 9.67-8 11.317C5.34 16.67 2 12.225 2 7c0-.682.057-1.35.166-2.001zm11.541 3.708a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              <span className="font-semibold text-green-800">StockLot Escrow</span>
            </div>
            <p className="text-sm text-green-700">
              Your payment is held securely and only released to the seller after you confirm delivery.
            </p>
          </div>
        </aside>
      </section>

      {/* JSON-LD for SEO */}
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            '@context': 'https://schema.org',
            '@type': 'Product',
            name: normalizedData.title,
            category: `${normalizedData.species} > ${normalizedData.breed} > ${normalizedData.product_type}`,
            image: (normalizedData.media || []).filter(m => m.type === 'image').map(m => m.url),
            offers: {
              '@type': 'Offer',
              priceCurrency: 'ZAR',
              price: normalizedData.price,
              availability: normalizedData.qty_available > 0 ? 'https://schema.org/InStock' : 'https://schema.org/OutOfStock',
              url: `https://stocklot.farm/listing/${normalizedData.id}`
            },
            aggregateRating: normalizedData.reviewSummary?.count ? {
              '@type': 'AggregateRating',
              ratingValue: normalizedData.reviewSummary.average,
              reviewCount: normalizedData.reviewSummary.count
            } : undefined,
            brand: {
              '@type': 'Organization',
              name: normalizedData.seller?.name
            }
          })
        }}
      />
    </main>
    <Footer />
    </>
  );
};

export default ListingPDP;