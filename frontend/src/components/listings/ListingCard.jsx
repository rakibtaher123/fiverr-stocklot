import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, Button, Badge } from '../ui';
import { 
  MapPin, ShoppingCart, Gavel, Clock, Eye, Package, 
  Truck, Shield, Star, TrendingUp, DollarSign 
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useDispatch } from 'react-redux';
import { useAuth } from '@/auth/AuthProvider';
import { useAddToCartMutation, useLazyGetCartQuery } from '@/store/api/cart.api';
import { addItem as addItemToCart } from '@/store/cartSlice';
import { useToast } from '@/hooks/use-toast';

const ListingCard = ({ 
  listing, 
  onViewDetails, 
  onBidPlaced, 
  showNotification,
  onAddToCart 
}) => {
  const { user, isAuthenticated } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const [timeRemaining, setTimeRemaining] = useState(null);
  const [addingToCart, setAddingToCart] = useState(false);
  const [addToCart] = useAddToCartMutation();
  const [refetchCart] = useLazyGetCartQuery();

  // Calculate time remaining for auctions
  useEffect(() => {
    if (listing.listing_type === 'auction' || listing.listing_type === 'hybrid') {
      if (listing.auction_end_time) {
        const updateTimer = () => {
          const now = new Date();
          const endTime = new Date(listing.auction_end_time);
          const diff = endTime - now;

          if (diff > 0) {
            const days = Math.floor(diff / (1000 * 60 * 60 * 24));
            const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
            const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
            
            if (days > 0) {
              setTimeRemaining(`${days}d ${hours}h`);
            } else if (hours > 0) {
              setTimeRemaining(`${hours}h ${minutes}m`);
            } else {
              setTimeRemaining(`${minutes}m`);
            }
          } else {
            setTimeRemaining('Ended');
          }
        };

        updateTimer();
        const interval = setInterval(updateTimer, 60000); // Update every minute
        return () => clearInterval(interval);
      }
    }
  }, [listing.auction_end_time, listing.listing_type]);

  const handleViewDetails = () => {
    if (onViewDetails) {
      onViewDetails(listing);
    } else {
      navigate(`/listing/${listing.id}`);
    }
  };

  const handleAddToCart = async (e) => {
    e.stopPropagation();
    
    setAddingToCart(true);
    
    // Check authentication with token verification
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
    
    try {
      if (hasValidAuth) {
        // Authenticated user - add to backend cart via API
        try {
          const response = await addToCart({
            listing_id: listing.id,
            quantity: 1,
            price_per_unit: getPriceDisplay(),
          }).unwrap();
          
          // Trigger cart refetch for header update
          try {
            await refetchCart();
          } catch (cartError) {
            // Silently handle - non-critical
          }
          // Also dispatch event to trigger header refetch
          window.dispatchEvent(new CustomEvent('cartRefetch', {}));
          
          if (onAddToCart) {
            onAddToCart(listing, 1);
          }
          
          toast({
            title: "Added to Cart!",
            description: `${listing.title} added successfully`,
          });
          
          if (showNotification) {
            showNotification(`Added ${listing.title} to cart`, 'success');
          }
        } catch (apiError) {
          // If API fails with 401, fall back to guest cart
          const is401 = apiError?.status === 401 || 
                       apiError?.data?.status === 401 || 
                       apiError?.error?.status === 401;
          
          if (is401) {
            // Fall through to guest cart logic
          } else {
            throw apiError;
          }
        }
      }
      
      // Guest user OR auth failed - add to Redux cart slice
      if (!hasValidAuth) {
        // Add to Redux cart slice (which syncs with localStorage)
        dispatch(addItemToCart({
          listing_id: listing.id,
          title: listing.title,
          price: getPriceDisplay(),
          qty: 1,
          unit: listing.unit || 'head',
          species: listing.species,
          product_type: listing.product_type,
          image: mainImage,
          seller_id: listing.seller_id,
          location: listing.region,
        }));
        
        // Update header cart count by dispatching a custom event
        window.dispatchEvent(new CustomEvent('cartUpdated', {}));
        
        if (onAddToCart) {
          onAddToCart(listing, 1);
        }
        
        toast({
          title: "Added to Cart!",
          description: `${listing.title} added successfully`,
        });
        
        if (showNotification) {
          showNotification(`Added ${listing.title} to cart`, 'success');
        }
      }
    } catch (error) {
      console.error('Error adding to cart:', error);
      toast({
        title: "Error",
        description: 'Failed to add item to cart. Please try again.',
        variant: "destructive",
      });
      if (showNotification) {
        showNotification('Failed to add to cart', 'error');
      }
    } finally {
      setAddingToCart(false);
    }
  };

  const handlePlaceBid = (e) => {
    e.stopPropagation();
    if (onBidPlaced) {
      onBidPlaced(listing);
    }
  };

  const formatPrice = (price) => {
    return new Intl.NumberFormat('en-ZA', {
      style: 'currency',
      currency: 'ZAR',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(price);
  };

  const getListingTypeBadge = () => {
    switch (listing.listing_type) {
      case 'auction':
        return <Badge className="bg-orange-100 text-orange-800 border-orange-300">Auction</Badge>;
      case 'hybrid':
        return <Badge className="bg-purple-100 text-purple-800 border-purple-300">Hybrid</Badge>;
      default:
        return <Badge className="bg-blue-100 text-blue-800 border-blue-300">Buy Now</Badge>;
    }
  };

  const getPriceDisplay = () => {
    if (listing.listing_type === 'auction' || listing.listing_type === 'hybrid') {
      return listing.current_bid || listing.starting_price || listing.price_per_unit;
    }
    return listing.price_per_unit;
  };

  const getSpeciesIcon = (species, title) => {
    // Normalize input to lowercase for comparison
    const normalizedSpecies = (species || '').toLowerCase();
    const normalizedTitle = (title || '').toLowerCase();

    // Check species field first
    if (normalizedSpecies) {
      if (normalizedSpecies.includes('chicken') || normalizedSpecies.includes('poultry') || 
          normalizedSpecies.includes('broiler') || normalizedSpecies.includes('layer') ||
          normalizedSpecies.includes('chick') || normalizedSpecies.includes('hen') ||
          normalizedSpecies.includes('rooster') || normalizedSpecies.includes('cockerel')) {
        return '🐔';
      }
      if (normalizedSpecies.includes('cattle') || normalizedSpecies.includes('cow') || 
          normalizedSpecies.includes('bull') || normalizedSpecies.includes('heifer') ||
          normalizedSpecies.includes('steer') || normalizedSpecies.includes('beef') ||
          normalizedSpecies.includes('dairy')) {
        return '🐄';
      }
      if (normalizedSpecies.includes('goat')) {
        return '🐐';
      }
      if (normalizedSpecies.includes('sheep') || normalizedSpecies.includes('lamb') ||
          normalizedSpecies.includes('ewe') || normalizedSpecies.includes('ram')) {
        return '🐑';
      }
      if (normalizedSpecies.includes('pig') || normalizedSpecies.includes('swine') ||
          normalizedSpecies.includes('hog') || normalizedSpecies.includes('boar') ||
          normalizedSpecies.includes('sow')) {
        return '🐷';
      }
      if (normalizedSpecies.includes('duck') || normalizedSpecies.includes('duckling')) {
        return '🦆';
      }
      if (normalizedSpecies.includes('rabbit') || normalizedSpecies.includes('bunny')) {
        return '🐰';
      }
      if (normalizedSpecies.includes('fish') || normalizedSpecies.includes('aquaculture') ||
          normalizedSpecies.includes('tilapia') || normalizedSpecies.includes('fry') ||
          normalizedSpecies.includes('fingerling')) {
        return '🐟';
      }
      if (normalizedSpecies.includes('ostrich')) {
        return '🦃';
      }
      if (normalizedSpecies.includes('turkey')) {
        return '🦃';
      }
      if (normalizedSpecies.includes('goose') || normalizedSpecies.includes('geese')) {
        return '🦢';
      }
      if (normalizedSpecies.includes('quail')) {
        return '🐦';
      }
      if (normalizedSpecies.includes('guinea') && normalizedSpecies.includes('fowl')) {
        return '🐦';
      }
    }

    // Fallback to title-based detection if species is not available or not matched
    if (normalizedTitle) {
      if (normalizedTitle.includes('chicken') || normalizedTitle.includes('poultry') || 
          normalizedTitle.includes('broiler') || normalizedTitle.includes('layer') ||
          normalizedTitle.includes('chick') || normalizedTitle.includes('hen') ||
          normalizedTitle.includes('rooster') || normalizedTitle.includes('cockerel')) {
        return '🐔';
      }
      if (normalizedTitle.includes('cattle') || normalizedTitle.includes('cow') || 
          normalizedTitle.includes('bull') || normalizedTitle.includes('heifer') ||
          normalizedTitle.includes('steer') || normalizedTitle.includes('beef') ||
          normalizedTitle.includes('dairy') || normalizedTitle.includes('angus') ||
          normalizedTitle.includes('brahman') || normalizedTitle.includes('nguni')) {
        return '🐄';
      }
      if (normalizedTitle.includes('goat') || normalizedTitle.includes('boer')) {
        return '🐐';
      }
      if (normalizedTitle.includes('sheep') || normalizedTitle.includes('lamb') ||
          normalizedTitle.includes('dorper') || normalizedTitle.includes('merino')) {
        return '🐑';
      }
      if (normalizedTitle.includes('pig') || normalizedTitle.includes('swine') ||
          normalizedTitle.includes('hog') || normalizedTitle.includes('boar')) {
        return '🐷';
      }
      if (normalizedTitle.includes('duck') || normalizedTitle.includes('duckling')) {
        return '🦆';
      }
      if (normalizedTitle.includes('rabbit') || normalizedTitle.includes('bunny')) {
        return '🐰';
      }
      if (normalizedTitle.includes('fish') || normalizedTitle.includes('aquaculture') ||
          normalizedTitle.includes('tilapia') || normalizedTitle.includes('fry')) {
        return '🐟';
      }
      if (normalizedTitle.includes('ostrich')) {
        return '🦃';
      }
      if (normalizedTitle.includes('turkey')) {
        return '🦃';
      }
    }

    // Default fallback
    return '🐾';
  };

  const mainImage = listing.images?.[0]?.url || 
                    listing.media?.[0]?.url || 
                    listing.image_url ||
                    null;

  return (
    <Card 
      className="hover:shadow-lg transition-all duration-200 cursor-pointer border-emerald-200"
      onClick={handleViewDetails}
    >
      {/* Image */}
      <div className="relative h-48 bg-gradient-to-br from-emerald-50 to-green-50 overflow-hidden">
        {mainImage ? (
          <img 
            src={mainImage} 
            alt={listing.title}
            className="w-full h-full object-cover"
            onError={(e) => {
              e.target.style.display = 'none';
              const placeholder = e.target.nextSibling;
              if (placeholder) {
                placeholder.classList.remove('hidden');
                placeholder.classList.add('flex');
              }
            }}
          />
        ) : null}
        <div 
          className={`w-full h-full flex items-center justify-center ${mainImage ? 'hidden' : 'flex'}`}
        >
          <span className="text-6xl">
            {getSpeciesIcon(listing.species, listing.title)}
          </span>
        </div>
        
        {/* Badges */}
        <div className="absolute top-2 left-2 flex flex-col gap-2">
          {getListingTypeBadge()}
          {listing.delivery_available && (
            <Badge className="bg-green-100 text-green-800 border-green-300 text-xs">
              <Truck className="h-3 w-3 mr-1" />
              Delivery
            </Badge>
          )}
        </div>
        
        {/* Auction Timer */}
        {(listing.listing_type === 'auction' || listing.listing_type === 'hybrid') && timeRemaining && (
          <div className="absolute top-2 right-2">
            <Badge className="bg-orange-500 text-white border-orange-600">
              <Clock className="h-3 w-3 mr-1" />
              {timeRemaining}
            </Badge>
          </div>
        )}
      </div>

      <CardHeader className="pb-2">
        <CardTitle className="text-lg font-semibold text-emerald-900 line-clamp-2">
          {listing.title || 'Untitled Listing'}
        </CardTitle>
        <div className="flex items-center gap-2 text-sm text-emerald-700">
          {listing.species && (
            <span className="flex items-center gap-1">
              <Package className="h-3 w-3" />
              {listing.species}
            </span>
          )}
          {listing.breed && (
            <span className="text-emerald-600">• {listing.breed}</span>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {/* Description */}
        {listing.description && (
          <p className="text-sm text-gray-600 line-clamp-2">
            {listing.description}
          </p>
        )}

        {/* Location */}
        {listing.region && (
          <div className="flex items-center gap-1 text-sm text-gray-500">
            <MapPin className="h-4 w-4" />
            <span>{listing.region}{listing.city ? `, ${listing.city}` : ''}</span>
          </div>
        )}

        {/* Price and Quantity */}
        <div className="flex items-center justify-between">
          <div>
            <div className="text-2xl font-bold text-emerald-900">
              {formatPrice(getPriceDisplay())}
            </div>
            {listing.listing_type === 'auction' && listing.starting_price && (
              <div className="text-xs text-gray-500">
                Starting: {formatPrice(listing.starting_price)}
              </div>
            )}
            {listing.listing_type === 'hybrid' && listing.buy_now_price && (
              <div className="text-xs text-gray-500">
                Buy Now: {formatPrice(listing.buy_now_price)}
              </div>
            )}
          </div>
          {listing.quantity && (
            <div className="text-sm text-gray-600">
              Qty: {listing.quantity} {listing.unit || 'head'}
            </div>
          )}
        </div>

        {/* Auction Stats */}
        {(listing.listing_type === 'auction' || listing.listing_type === 'hybrid') && (
          <div className="flex items-center gap-4 text-xs text-gray-600">
            {listing.total_bids > 0 && (
              <div className="flex items-center gap-1">
                <TrendingUp className="h-3 w-3" />
                <span>{listing.total_bids} bids</span>
              </div>
            )}
            {listing.reserve_price && (
              <div className="flex items-center gap-1">
                <Shield className="h-3 w-3" />
                <span>Reserve met</span>
              </div>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2 pt-2">
          {listing.listing_type === 'buy_now' && (
            <Button
              onClick={handleAddToCart}
              disabled={addingToCart}
              className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white"
            >
              <ShoppingCart className="h-4 w-4 mr-2" />
              {addingToCart ? 'Adding...' : 'Add to Cart'}
            </Button>
          )}
          
          {(listing.listing_type === 'auction' || listing.listing_type === 'hybrid') && (
            <Button
              onClick={handlePlaceBid}
              disabled={!user}
              className="flex-1 bg-orange-600 hover:bg-orange-700 text-white"
            >
              <Gavel className="h-4 w-4 mr-2" />
              Place Bid
            </Button>
          )}
          
          {listing.listing_type === 'hybrid' && (
            <Button
              onClick={handleAddToCart}
              disabled={addingToCart}
              variant="outline"
              className="flex-1 border-emerald-300 text-emerald-700 hover:bg-emerald-50"
            >
              <ShoppingCart className="h-4 w-4 mr-2" />
              Buy Now
            </Button>
          )}
          
          <Button
            onClick={handleViewDetails}
            variant="outline"
            className="border-emerald-300 text-emerald-700 hover:bg-emerald-50"
          >
            <Eye className="h-4 w-4" />
          </Button>
        </div>

        {/* Additional Info */}
        <div className="flex items-center gap-4 text-xs text-gray-500 pt-2 border-t">
          {listing.has_vet_certificate && (
            <div className="flex items-center gap-1">
              <Shield className="h-3 w-3 text-green-600" />
              <span>Certified</span>
            </div>
          )}
          {listing.health_status && (
            <span className="capitalize">{listing.health_status}</span>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default ListingCard;

