import { useAuth } from "@/auth/AuthProvider";
// import { Link, Menu, x, Search, X } from "lucide-react";
import { useEffect, useState, useRef } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useSelector } from "react-redux";
import { Button, Input, Badge, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger, Avatar, AvatarFallback } from "..";
// import { Button, Input } from "../ui";
import LocationPicker from "@/components/location/LocationPicker";
import ShoppingCartModal from "@/components/cart/ShoppingCart";
import { Menu, Search, X, ShoppingCart, MessageCircle, ChevronDown, CreditCard, DollarSign, MapPin, LayoutDashboard, Users, Shield, LogOut, User, Plus, Building, Package } from "lucide-react";
import NotificationBell from "@/components/notifications/NotificationBell";
import ContextSwitcher from "@/components/seller/ContextSwitcher";
import api from '@/utils/apiHelper';
import { useLazyGetCartQuery } from "@/store/api/cart.api";
import { selectCartItemCount } from "@/store/cartSlice";
// import { Menu } from "@radix-ui/react-menubar";

// Header component
function Header() {
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [showCart, setShowCart] = useState(false);
  const [cartItemCount, setCartItemCount] = useState(0);
  const user = auth.status === 'authenticated' ? auth.user : null;
  const isAuthenticated = auth.status === 'authenticated';
  const isLoading = auth.status === 'loading';
  const hasFetchedCart = useRef(false);
  const userId = user?.id;

  // Get cart count from Redux for guest users
  const reduxCartCount = useSelector(selectCartItemCount);

  // Use lazy query to only fetch when explicitly called (when user is authenticated)
  const [getCart, {data: cartData, isSuccess: isCartSuccess, isError: isCartError}] = useLazyGetCartQuery();
  
  // Store getCart in a ref to avoid dependency issues
  const getCartRef = useRef(getCart);
  useEffect(() => {
    getCartRef.current = getCart;
  }, [getCart]);
  
  useEffect(() => {
    // Don't do anything while auth is loading
    if (isLoading) {
      return;
    }

    // Reset fetch flag when user logs out
    if (!isAuthenticated || !user) {
      hasFetchedCart.current = false;
      // Update cart count from Redux for guest users
      setCartItemCount(reduxCartCount);
      return;
    }

    // Only fetch cart once when all conditions are met:
    // 1. Auth is not loading (checked above)
    // 2. User is authenticated
    // 3. User object exists and has an ID
    // 4. Token exists in localStorage and is not empty
    // 5. We haven't fetched yet for this user
    const token = localStorage.getItem('token');
    const userHasId = user && user.id;
    
    // Double-check: ensure we have all required data before making the request
    if (isAuthenticated && userHasId && token && token.trim() !== '' && !hasFetchedCart.current) {
      hasFetchedCart.current = true;
      // Use setTimeout to ensure auth state is fully settled
      const timeoutId = setTimeout(() => {
        getCartRef.current().catch((error) => {
          // If fetch fails with 401, user might not be properly authenticated
          // Don't reset the flag for 401 - it means user is not authenticated
          if (error?.status === 401 || error?.data?.status === 401) {
            // Silently handle 401 - user is not authenticated, which is expected
            hasFetchedCart.current = true; // Keep flag to prevent retries
          } else {
            console.error('Failed to fetch cart:', error);
            hasFetchedCart.current = false; // Allow retry for non-401 errors
          }
        });
      }, 100); // Small delay to ensure auth state is settled
      
      return () => {
        if (timeoutId) clearTimeout(timeoutId);
      };
    }
  }, [isLoading, isAuthenticated, userId]); // Stable dependencies - removed getCart

  // console.log('cartData', cartData);
  // console.log('isCartSuccess', isCartSuccess);
  // console.log('isCartError', isCartError);

  // Initialize cart count on mount and when auth status changes
  useEffect(() => {
    if (!isAuthenticated) {
      // For guest users, get count from Redux
      setCartItemCount(reduxCartCount);
    }
  }, [isAuthenticated, reduxCartCount]);
  
  // Listen for storage changes (when cart is updated in another tab/window)
  useEffect(() => {
    if (!isAuthenticated) {
      const handleStorageChange = (e) => {
        if (e.key === 'cart') {
          // Cart updated in another tab, update from Redux
          setCartItemCount(reduxCartCount);
        }
      };
      
      window.addEventListener('storage', handleStorageChange);
      
      return () => {
        window.removeEventListener('storage', handleStorageChange);
      };
    }
  }, [isAuthenticated, reduxCartCount]);

  // Update cart count when cart data changes
  useEffect(() => {
    if (isCartSuccess && cartData !== undefined) {
      setCartItemCount(cartData.item_count || 0);
    }
  }, [cartData, isCartSuccess]);

  // Listen for cart updates from both guest and authenticated users
  useEffect(() => {
    const handleCartUpdate = () => {
      // For guest users, update count from Redux
      if (!isAuthenticated) {
        setCartItemCount(reduxCartCount);
      }
    };

    const handleCartRefetch = async () => {
      // For authenticated users, refetch cart when items are added
      if (isAuthenticated && user && user.id) {
        try {
          await getCartRef.current();
        } catch (error) {
          // Silently handle errors
        }
      }
    };

    window.addEventListener('cartUpdated', handleCartUpdate);
    window.addEventListener('cartRefetch', handleCartRefetch);
    
    return () => {
      window.removeEventListener('cartUpdated', handleCartUpdate);
      window.removeEventListener('cartRefetch', handleCartRefetch);
    };
  }, [isAuthenticated, user, getCartRef, reduxCartCount]);
  // const fetchCartCount = async () => {
  //   try {
  //     // Use new API client with automatic cookie handling
  //     const response = await api.get('/cart');
      
  //     setCartItemCount(response.data.item_count || 0);
  //   } catch (error) {
  //     console.error('Error fetching cart count:', error);
  //   }
  // };

  const isSeller = user && (user.roles || []).includes('seller');
  const isBuyer = user && (user.roles || []).includes('buyer');
  const isAdmin = user && (user.roles || []).includes('admin');

  console.log('user', user);



  const handleSearch = (e) => {
    if (e.key === 'Enter' && searchTerm.trim()) {
      navigate(`/marketplace?search=${encodeURIComponent(searchTerm)}`);
    }
  };

  const handleLogout = () => {
    auth.signOut();
    navigate('/marketplace');
  };

  return (
    <header className="border-b border-emerald-200 bg-white/90 backdrop-blur-sm sticky top-0 z-50 shadow-sm pt-2">
      <div className="container mx-auto px-4 py-3">
        <div className="flex items-center justify-between">
          {/* Logo */}
          <Link to="/" className="flex items-center space-x-3">
            <div className="w-12 h-12 bg-gradient-to-br from-emerald-600 to-green-600 rounded-xl flex items-center justify-center shadow-lg">
              <span className="text-white font-bold text-xl">🐄</span>
            </div>
            <div>
              <h1 className="text-2xl font-bold bg-gradient-to-r from-emerald-700 to-green-700 bg-clip-text text-transparent">
                StockLot
              </h1>
              <p className="text-xs text-emerald-600 font-medium">Livestock Marketplace</p>
            </div>
          </Link>

          {/* Search Bar */}
          <div className="hidden md:flex flex-1 max-w-md mx-8">
            <div className="relative w-full">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-emerald-500 h-4 w-4" />
              <Input
                type="text"
                placeholder="Search livestock..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                onKeyPress={handleSearch}
                className="pl-10 border-emerald-200 focus:border-emerald-500 focus:ring-emerald-500 rounded-full"
              />
            </div>
          </div>

          {/* Desktop Navigation - Cleaned Up */}
          <nav className="hidden lg:flex items-center space-x-6">
            <Link 
              to="/marketplace" 
              className={`font-medium transition-colors hover:text-emerald-700 ${
                location.pathname === '/marketplace' ? 'text-emerald-700' : 'text-gray-600'
              }`}
            >
              Marketplace
            </Link>
            <Link 
              to="/buy-requests" 
              className={`font-medium transition-colors hover:text-emerald-700 ${
                location.pathname === '/buy-requests' ? 'text-emerald-700' : 'text-gray-600'
              }`}
            >
              Buy Requests
            </Link>
          </nav>

          {/* User Menu / Auth Buttons */}
          <div className="flex items-center space-x-4">
              <div className="flex items-center space-x-3">
                {/* Shopping Cart - Always visible */}
                <Button
                  variant="ghost" 
                  onClick={() => navigate('/cart')}
                  className="relative p-2 text-gray-600 hover:text-emerald-600 hover:bg-emerald-50"
                  title="Shopping Cart"
                >
                  <ShoppingCart className="h-5 w-5" />
                  {cartItemCount > 0 && (
                    <Badge className="absolute -top-2 -right-2 bg-emerald-600 text-white text-xs min-w-[20px] h-5 rounded-full flex items-center justify-center">
                      {cartItemCount}
                    </Badge>
                  )}
                </Button>
            {user ? (
                <>
                <NotificationBell />
                
                {/* Messages/Inbox Button */}
                <Button 
                  variant="ghost" 
                  onClick={() => navigate('/inbox')}
                  className="relative p-2 text-gray-600 hover:text-emerald-600 hover:bg-emerald-50"
                  title="Messages & Conversations"
                >
                  <MessageCircle className="h-5 w-5" />
                </Button>
                
                {/* Profile Dropdown */}
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" className="flex items-center space-x-2 hover:bg-emerald-50">
                      <Avatar className="h-8 w-8">
                        <AvatarFallback className="bg-emerald-100 text-emerald-700 font-semibold">
                          {user.full_name.charAt(0)}
                        </AvatarFallback>
                      </Avatar>
                      <div className="hidden md:flex flex-col text-left">
                        <p className="text-sm font-medium text-gray-900">{user.full_name}</p>
                        <div className="flex space-x-1">
                          {(user.roles || []).map(role => (
                            <Badge key={role} variant="secondary" className="text-xs bg-emerald-100 text-emerald-700 capitalize">
                              {role}
                            </Badge>
                          ))}
                        </div>
                      </div>
                      <ChevronDown className="h-4 w-4 text-gray-500" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-56">
                    <DropdownMenuLabel>My Account</DropdownMenuLabel>
                    <DropdownMenuSeparator />
                    
                    
                    {/* Profile & Settings */}
                    <DropdownMenuItem onClick={() => navigate('/profile')}>
                      <User className="mr-2 h-4 w-4" />
                      Profile & Settings
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => navigate('/payment-methods')}>
                      <CreditCard className="mr-2 h-4 w-4" />
                      Payment Methods
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => navigate('/account/credit-wallet')}>
                      <DollarSign className="mr-2 h-4 w-4" />
                      Credit Wallet
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => navigate('/addresses')}>
                      <MapPin className="mr-2 h-4 w-4" />
                      Addresses
                    </DropdownMenuItem>
                    
                    <DropdownMenuSeparator />
                    
                    {/* Main Functions */}
                    <DropdownMenuItem onClick={() => navigate('/dashboard')}>
                      <LayoutDashboard className="mr-2 h-4 w-4" />
                      Dashboard
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => navigate('/inbox')}>
                      <MessageCircle className="mr-2 h-4 w-4" />
                      Messages
                    </DropdownMenuItem>
                    
                    {user.roles.includes('buyer') && (
                      <>
                        <DropdownMenuItem onClick={() => navigate('/buy-requests')}>
                          <ShoppingCart className="mr-2 h-4 w-4" />
                          Buy Requests
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => navigate('/create-buy-request')}>
                          <Plus className="mr-2 h-4 w-4" />
                          Post Request
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => navigate('/create-organization')}>
                          <Building className="mr-2 h-4 w-4" />
                          Create Organization
                        </DropdownMenuItem>
                      </>
                    )}
                    
                    {user.roles.includes('seller') && (
                      <>
                        <DropdownMenuItem onClick={() => navigate('/create-listing')}>
                          <Package className="mr-2 h-4 w-4" />
                          Sell Livestock
                        </DropdownMenuItem>
                      </>
                    )}
                    
                    <DropdownMenuItem onClick={() => navigate('/referrals')}>
                      <Users className="mr-2 h-4 w-4" />
                      Referrals
                    </DropdownMenuItem>
                    
                    {/* Admin Access */}
                    {user.roles.includes('admin') && (
                      <>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem onClick={() => navigate('/admin')} className="text-red-600">
                          <Shield className="mr-2 h-4 w-4" />
                          Admin Panel
                        </DropdownMenuItem>
                      </>
                    )}
                    
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={handleLogout} className="text-red-600">
                      <LogOut className="mr-2 h-4 w-4" />
                      Logout
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
                </>
            ) : (
              <div className="flex items-center space-x-3">
                <Button 
                  variant="outline" 
                  onClick={() => navigate('/login')}
                  className="border-emerald-300 text-emerald-700 hover:bg-emerald-50"
                >
                  Login
                </Button>
                <Button 
                  onClick={() => navigate('/register')}
                  className="bg-gradient-to-r from-emerald-600 to-green-600 hover:from-emerald-700 hover:to-green-700 text-white"
                >
                  Sign Up
                </Button>
              </div>
            )}
              </div>


            {/* Mobile Menu Button */}
            <Button
              variant="ghost"
              size="sm"
              className="lg:hidden"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            >
              {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </Button>
          </div>
        </div>

        {/* Mobile Search */}
        <div className="md:hidden mt-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-emerald-500 h-4 w-4" />
            <Input
              type="text"
              placeholder="Search livestock..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              onKeyPress={handleSearch}
              className="pl-10 border-emerald-200 focus:border-emerald-500 focus:ring-emerald-500 rounded-full"
            />
          </div>
        </div>

        <div className="flex items-center justify-center mb-2">
          {/* Location Picker */}
          <div className="mt-3 flex justify-center">
            <LocationPicker triggerClassName="text-emerald-600 hover:text-emerald-700" />
          </div>

          {/* Context Switcher for Sellers */}
          {isSeller || isBuyer && (
            <div className="mt-3 flex justify-center">
              <ContextSwitcher />
            </div>
          )}
        </div>


        {/* Mobile Menu */}
        {mobileMenuOpen && (
          <div className="lg:hidden mt-4 pb-4 border-t border-emerald-200">
            <nav className="flex flex-col space-y-3 pt-4">
              <Link 
                to="/marketplace" 
                className="font-medium text-gray-600 hover:text-emerald-700 transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                Marketplace
              </Link>
              <Link 
                to="/buy-requests" 
                className="font-medium text-gray-600 hover:text-emerald-700 transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                Buy Requests
              </Link>
              {/* Authenticated User Links */}
              {user && (
                <>
                  {user.roles?.includes('buyer') && (
                    <>
                      <Link 
                        to="/my-buy-requests" 
                        className="font-medium text-gray-600 hover:text-emerald-700 transition-colors"
                        onClick={() => setMobileMenuOpen(false)}
                      >
                        My Buy Requests
                      </Link>
                      <Link 
                        to="/offers-inbox" 
                        className="font-medium text-gray-600 hover:text-emerald-700 transition-colors"
                        onClick={() => setMobileMenuOpen(false)}
                      >
                        Offers Inbox
                      </Link>
                    </>
                  )}
                  {user.roles?.includes('seller') && (
                    <Link 
                      to="/seller-dashboard" 
                      className="font-medium text-gray-600 hover:text-emerald-700 transition-colors"
                      onClick={() => setMobileMenuOpen(false)}
                    >
                      Seller Dashboard
                    </Link>
                  )}
                </>
              )}
              {user && (
                <Link 
                  to="/create-buy-request" 
                  className="font-medium text-gray-600 hover:text-emerald-700 transition-colors"
                  onClick={() => setMobileMenuOpen(false)}
                >
                  Post Request
                </Link>
              )}
              <Link 
                to="/how-it-works" 
                className="font-medium text-gray-600 hover:text-emerald-700 transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                How It Works
              </Link>
              {user && (
                <Link 
                  to="/dashboard" 
                  className="font-medium text-gray-600 hover:text-emerald-700 transition-colors"
                  onClick={() => setMobileMenuOpen(false)}
                >
                  Dashboard
                </Link>
              )}
              {isSeller && (
                <Link 
                  to="/create-listing" 
                  className="font-medium text-gray-600 hover:text-emerald-700 transition-colors"
                  onClick={() => setMobileMenuOpen(false)}
                >
                  Sell Livestock
                </Link>
              )}
              {isAdmin && (
                <Link 
                  to="/admin" 
                  className="font-medium text-gray-600 hover:text-emerald-700 transition-colors"
                  onClick={() => setMobileMenuOpen(false)}
                >
                  Admin
                </Link>
              )}
              <Link 
                to="/contact" 
                className="font-medium text-gray-600 hover:text-emerald-700 transition-colors"
                onClick={() => setMobileMenuOpen(false)}
              >
                Contact
              </Link>
            </nav>
          </div>
        )}
      </div>
      
      {/* Shopping Cart Modal */}
      <ShoppingCartModal 
        isOpen={showCart} 
        onClose={() => setShowCart(false)}
        onCartUpdate={setCartItemCount}
      />
    </header>
  );
}

export default Header;