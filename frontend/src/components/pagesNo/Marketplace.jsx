import { useAuth } from "@/auth/AuthProvider";
import React, { useState, useEffect, useMemo, useRef } from "react";
import { useNavigate, useLocation } from 'react-router-dom';

// Redux RTK Query hooks
import { useGetListingsQuery, useLazyGetListingsQuery } from "@/store/api/listings.api";
import { 
  useGetTaxonomyCategoriesQuery, 
  useLazyGetSpeciesQuery,
  useGetBreedsBySpeciesQuery,
  useGetProductTypesQuery 
} from "@/store/api/taxonomy.api";
import { useSmartSearchMutation } from "@/store/api/search.api";

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, Label, Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui";
import { Brain, Filter, MapPin, Search, Shield, Star, User } from "lucide-react";
import DeliverableFilterBar from "../geofence/DeliverableFilterBar";
import ListingCard from "../listings/ListingCard";
import OrderModal from "../listings/OrderModal";
import BiddingModal from "../listings/BiddingModal";
import Header from '@/components/ui/common/Header';
import Footer from '@/components/ui/common/Footer';
function Marketplace() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [listings, setListings] = useState([]);
  const [showExotics, setShowExotics] = useState(false);
  const [filters, setFilters] = useState({
    category_group_id: '',
    species_id: '',
    breed_id: '',
    product_type_id: '',
    province: '',
    price_min: '',
    price_max: '',
    listing_type: 'all',
    include_exotics: false  // Default: core livestock only
  });
  const [showOrderModal, setShowOrderModal] = useState(false);
  const [showBiddingModal, setShowBiddingModal] = useState(false);
  const [selectedListing, setSelectedListing] = useState(null);
  const [sortBy, setSortBy] = useState('newest');
  const [deliverableOnly, setDeliverableOnly] = useState(false);
  const [smartSearchQuery, setSmartSearchQuery] = useState('');
  const [smartSearchResults, setSmartSearchResults] = useState(null);
  const [cartUpdateCallback, setCartUpdateCallback] = useState(() => {
    // Default cart callback function
    return (listing, quantity = 1) => {
      console.log('Adding to cart:', listing.title, 'Quantity:', quantity);
      // This can be enhanced later with actual cart functionality
    };
  });

  // Redux RTK Query hooks
  const categoryMode = showExotics ? 'all' : 'core';
  const { data: categoriesData, isLoading: categoriesLoading } = useGetTaxonomyCategoriesQuery({ mode: categoryMode });
  const { data: productTypesData, isLoading: productTypesLoading } = useGetProductTypesQuery({});
  
  // Fetch all species on mount
  const [getAllSpecies, { data: allSpeciesData, isLoading: speciesLoading }] = useLazyGetSpeciesQuery();
  // console.log('All species data:', allSpeciesData);
  const [getSpeciesByGroup, { data: speciesByGroupData }] = useLazyGetSpeciesQuery();
  // console.log('Species by group data:', speciesByGroupData);
  
  const { data: breedsData, isLoading: breedsLoading } = useGetBreedsBySpeciesQuery(
    filters.species_id || '',
    { skip: !filters.species_id }
  );
  // console.log('Breeds data:', breedsData);

  
  // Listings query with filters
  const listingsParams = useMemo(() => {
    const params = {};
    if (filters.category_group_id) params.category_group_id = filters.category_group_id;
    if (filters.species_id) params.species_id = filters.species_id;
    if (filters.breed_id) params.breed_id = filters.breed_id;
    if (filters.product_type_id) params.product_type_id = filters.product_type_id;
    if (filters.province) params.region = filters.province;
    if (filters.price_min) params.price_min = filters.price_min;
    if (filters.price_max) params.price_max = filters.price_max;
    if (filters.listing_type && filters.listing_type !== 'all') params.listing_type = filters.listing_type;
    params.include_exotics = filters.include_exotics;
    if (deliverableOnly) params.deliverable_only = true;
    return params;
  }, [filters, deliverableOnly]);
  
  const { data: listingsData, isLoading: listingsLoading, error: listingsError, refetch: refetchListings } = useGetListingsQuery(listingsParams);
  console.log('Listings data for:', listingsData);
  const [smartSearch, { isLoading: smartSearchLoading }] = useSmartSearchMutation();
  console.log('Smart search loading:', smartSearchLoading);

  // Derived state from API responses - handle different response formats
const categoryGroups = useMemo(() => {
  if (!categoriesData) return [];

  const raw =
    Array.isArray(categoriesData)
      ? categoriesData
      : categoriesData.categories || [];

  // ✅ remove duplicates by id
  const unique = Array.from(
  new Map(raw.map(item => [item.name, item])).values()
);
  return unique;
}, [categoriesData]);

  
  const productTypes = useMemo(() => {
    if (!productTypesData) return [];
    if (Array.isArray(productTypesData)) return productTypesData;
    if (productTypesData.product_types) return productTypesData.product_types;
    return [];
  }, [productTypesData]);
  
  // Species data - use filtered by group if available, otherwise use all species
  const allSpecies = useMemo(() => {
    if (filters.category_group_id && speciesByGroupData) {
      return Array.isArray(speciesByGroupData) ? speciesByGroupData : [];
    }
    if (allSpeciesData) {
      return Array.isArray(allSpeciesData) ? allSpeciesData : [];
    }
    return [];
  }, [allSpeciesData, speciesByGroupData, filters.category_group_id]);
  
  const breeds = useMemo(() => {
    if (!breedsData) return [];
    return Array.isArray(breedsData) ? breedsData : [];
  }, [breedsData]);
  
  // Get species filtered by category group (for display)
  const species = useMemo(() => {
    if (!filters.category_group_id) return allSpecies;
    return allSpecies.filter(s => s.category_group_id === filters.category_group_id);
  }, [allSpecies, filters.category_group_id]);

  const loading = categoriesLoading || productTypesLoading || listingsLoading || smartSearchLoading;

  // Fetch all species on mount
  useEffect(() => {
    getAllSpecies({});
  }, [getAllSpecies]);

  // Check URL params for exotic mode
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const includeExotics = urlParams.get('include_exotics') === 'true';
    
    if (includeExotics) {
      setShowExotics(true);
      setFilters(prev => ({ ...prev, include_exotics: true }));
    }
  }, []);

  // Set up real-time auction updates
  useEffect(() => {
    const interval = setInterval(() => {
      updateAuctionTimers();
    }, 1000);

    return () => clearInterval(interval);
  }, []);

  // Fetch species when category group changes
  useEffect(() => {
    if (filters.category_group_id) {
      getSpeciesByGroup({ category_group_id: filters.category_group_id });
    }
  }, [filters.category_group_id, getSpeciesByGroup]);

  // Update listings when API data changes
  useEffect(() => {
    if (listingsData) {
      // Handle different response formats
      let listingsArray = [];
      if (Array.isArray(listingsData)) {
        listingsArray = listingsData;
      } else if (listingsData.listings) {
        listingsArray = listingsData.listings;
      } else if (listingsData.data) {
        listingsArray = listingsData.data;
      }
      
      console.log('📊 Listings data received:', {
        total: listingsArray.length,
        format: Array.isArray(listingsData) ? 'array' : 'object',
        hasListings: !!listingsData.listings,
        hasData: !!listingsData.data
      });
      
      // Enhance listings with auction data and species information
      const enhancedListings = listingsArray.map(listing => {
        const listingSpecies = allSpecies.find(s => s.id === listing.species_id);
        
        return {
          ...listing,
          species: listingSpecies ? listingSpecies.name : null,
          listing_type: listing.listing_type || 'buy_now',
          current_bid: listing.current_bid || (
            listing.listing_type === 'auction' || listing.listing_type === 'hybrid' 
              ? listing.starting_price || listing.price_per_unit 
              : null
          ),
          auction_end_time: listing.auction_end_time || (
            listing.listing_type !== 'buy_now' 
              ? new Date(Date.now() + Math.random() * 7 * 24 * 60 * 60 * 1000).toISOString()
              : null
          ),
          total_bids: listing.total_bids || 0,
          starting_price: listing.starting_price || listing.price_per_unit,
          buy_now_price: listing.listing_type === 'hybrid' ? listing.buy_now_price || (listing.price_per_unit * 1.2) : null,
          reserve_price: listing.reserve_price || null
        };
      });
      
      console.log(`✅ Processed ${enhancedListings.length} listings`);
      setListings(enhancedListings);
    } else if (listingsData === null || listingsData === undefined) {
      // No data yet, keep existing listings or set empty
      if (listings.length === 0) {
        console.log('⚠️ No listings data received');
      }
    }
  }, [listingsData, allSpecies]);

  // Update filters when exotic toggle changes
  useEffect(() => {
    setFilters(prev => ({ ...prev, include_exotics: showExotics }));
  }, [showExotics]);

  const updateAuctionTimers = () => {
    setListings(prevListings => 
      prevListings.map(listing => {
        if (listing.listing_type !== 'buy_now' && listing.auction_end_time) {
          const timeRemaining = new Date(listing.auction_end_time) - new Date();
          if (timeRemaining <= 0 && !listing.expired) {
            // Auction ended
            return { ...listing, expired: true };
          }
        }
        return listing;
      })
    );
  };

  const handleViewDetails = (listing) => {
    // Navigate to the new PDP page
    navigate(`/listing/${listing.id}`);
  };

  const handlePlaceBid = (listing) => {
    if (!user) {
      navigate('/login');
      return;
    }
    setSelectedListing(listing);
    setShowBiddingModal(true);
  };

  const handleBidPlaced = (updatedListing, bidData) => {
    // Update the listing in the state
    setListings(prevListings =>
      prevListings.map(listing =>
        listing.id === updatedListing.id ? updatedListing : listing
      )
    );

    setShowBiddingModal(false);
  };

  // Listings are now fetched via Redux hook - no need for fetchListings function

  const getSpeciesName = (speciesId) => {
    const spec = species.find(s => s.id === speciesId);
    return spec ? spec.name : 'Unknown';
  };

  const handleSmartSearch = async () => {
    if (!smartSearchQuery.trim()) return;
    
    try {
      const result = await smartSearch({ query: smartSearchQuery }).unwrap();
      
      setSmartSearchResults(result.search);
      
      // Update listings with search results
      const searchListings = result.search.results
        .filter(result => result.type === 'listing')
        .map(result => result.data);
      
      setListings(searchListings);
      
    } catch (error) {
      console.error('Smart search error:', error);
      
      // Fallback to regular filtering
      const fallbackListings = listings.filter(listing => 
        listing.title?.toLowerCase().includes(smartSearchQuery.toLowerCase()) ||
        listing.description?.toLowerCase().includes(smartSearchQuery.toLowerCase()) ||
        listing.breed?.toLowerCase().includes(smartSearchQuery.toLowerCase()) ||
        listing.species?.toLowerCase().includes(smartSearchQuery.toLowerCase())
      );
      
      setListings(fallbackListings);
    }
  };

  const clearSmartSearch = () => {
    setSmartSearchQuery('');
    setSmartSearchResults(null);
    refetchListings(); // Reload all listings using Redux
  };

  // Enhanced handleFilterChange to clear smart search when filters are used
  const handleFilterChange = (key, value) => {
    console.log('Filter change called:', key, value); // Debug log
    const newFilters = { ...filters, [key]: value };
    
    // Reset dependent filters when parent changes
    if (key === 'category_group_id') {
      newFilters.species_id = '';
      newFilters.breed_id = '';
    } else if (key === 'species_id') {
      newFilters.breed_id = '';
    }
    
    // Clear smart search when using filters
    if (smartSearchResults) {
      clearSmartSearch();
    }
    
    console.log('Setting new filters:', newFilters); // Debug log
    setFilters(newFilters);
  };

  const handleAISearch = (searchQuery) => {
    if (!searchQuery.trim()) return;
    
    // Simple AI-like parsing for immediate value
    const query = searchQuery.toLowerCase();
    const newFilters = { ...filters };
    
    // Parse species/animals
    if (query.includes('chick') || query.includes('chicken')) {
      const broilerSpecies = species.find(s => s.name.includes('Commercial Broilers'));
      const freeRangeSpecies = species.find(s => s.name.includes('Free Range'));
      
      if (query.includes('free range')) {
        newFilters.species_id = freeRangeSpecies?.id || '';
      } else {
        newFilters.species_id = broilerSpecies?.id || '';
      }
    } else if (query.includes('goat')) {
      const goatSpecies = species.find(s => s.name === 'Goats');
      newFilters.species_id = goatSpecies?.id || '';
    } else if (query.includes('cattle') || query.includes('cow')) {
      const cattleSpecies = species.find(s => s.name === 'Cattle');
      newFilters.species_id = cattleSpecies?.id || '';
    } else if (query.includes('sheep')) {
      const sheepSpecies = species.find(s => s.name === 'Sheep');
      newFilters.species_id = sheepSpecies?.id || '';
    }
    
    // Parse breeds
    if (query.includes('ross 308') || query.includes('ross308')) {
      // Will be filtered by breed when breeds are loaded
    } else if (query.includes('boer')) {
      // Will be filtered by breed when breeds are loaded  
    }
    
    // Parse location
    const provinces = ['gauteng', 'western cape', 'limpopo', 'mpumalanga', 'free state', 'north west', 'northern cape', 'eastern cape', 'kwazulu natal'];
    provinces.forEach(province => {
      if (query.includes(province)) {
        newFilters.province = province.split(' ').map(word => 
          word.charAt(0).toUpperCase() + word.slice(1)
        ).join(' ');
      }
    });
    
    // Parse price
    const priceMatch = query.match(/under r?(\d+)/i) || query.match(/below r?(\d+)/i);
    if (priceMatch) {
      newFilters.price_max = priceMatch[1];
    }
    
    const minPriceMatch = query.match(/above r?(\d+)/i) || query.match(/over r?(\d+)/i);
    if (minPriceMatch) {
      newFilters.price_min = minPriceMatch[1];
    }
    
    setFilters(newFilters);
  };

  const clearFilters = () => {
    setFilters({
      category_group_id: '',
      species_id: '',
      breed_id: '',
      product_type_id: '',
      province: '',
      price_min: '',
      price_max: ''
    });
  };

  const getFilteredProductTypes = () => {
    if (!filters.category_group_id) return productTypes;
    const selectedGroup = categoryGroups.find(g => g.id === filters.category_group_id);
    if (!selectedGroup) return productTypes;
    
    return productTypes.filter(pt => 
      pt.applicable_to_groups && pt.applicable_to_groups.includes(selectedGroup.name)
    );
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-emerald-50 via-green-50 to-emerald-100 flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 bg-gradient-to-br from-emerald-600 to-green-600 rounded-2xl flex items-center justify-center mx-auto mb-4 animate-pulse">
            <span className="text-white text-2xl">📦</span>
          </div>
          <p className="text-emerald-700">Loading livestock...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-emerald-50 via-green-50 to-emerald-100 py-4">
      <Header />
      <div className="container mx-auto px-4 py-8">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-emerald-900 mb-2">Browse Livestock</h1>
          <p className="text-emerald-700">Find quality animals from verified sellers across South Africa</p>
        </div>

        {/* AI-Powered Search Bar */}
        <Card className="mb-6 border-emerald-200">
          <CardContent className="p-4">
            <div className="flex items-center space-x-3">
              <Search className="h-5 w-5 text-emerald-600" />
              <Input
                value={smartSearchQuery}
                onChange={(e) => setSmartSearchQuery(e.target.value)}
                placeholder="Try: '50 day-old Ross 308 chicks in Gauteng under R20 each' or 'Boer goats in Limpopo'"
                className="border-0 bg-transparent text-emerald-800 placeholder-emerald-500 flex-1"
                onKeyPress={(e) => {
                  if (e.key === 'Enter') {
                    handleSmartSearch();
                  }
                }}
              />
              <Button 
                onClick={handleSmartSearch}
                className="bg-emerald-600 hover:bg-emerald-700 text-white px-6"
                disabled={!smartSearchQuery.trim()}
              >
                Search
              </Button>
              <Badge variant="outline" className="text-emerald-600 border-emerald-300">
                <Brain className="h-3 w-3 mr-1" />
                ML Powered
              </Badge>
            </div>
          </CardContent>
        </Card>

        {/* Deliverable Filter Bar */}
        <DeliverableFilterBar 
          value={deliverableOnly} 
          onChange={setDeliverableOnly}
        />

        {/* Exotic Livestock Toggle */}
        <Card className="mb-6 border-emerald-200">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <h3 className="text-lg font-semibold text-emerald-900">Livestock Categories</h3>
                <Badge variant="secondary" className="text-emerald-700">
                  {showExotics ? 'All Categories' : 'Core Livestock Only'}
                </Badge>
              </div>
              
              <label className="inline-flex items-center gap-3 cursor-pointer">
                <span className="text-sm text-gray-700">Show Exotic & Specialty</span>
                <input
                  type="checkbox"
                  checked={showExotics}
                  onChange={(e) => setShowExotics(e.target.checked)}
                  className="w-4 h-4 text-amber-600 bg-gray-100 border-gray-300 rounded focus:ring-amber-500 focus:ring-2"
                />
                <span className="text-xs text-gray-500">(Ostrich, Game Animals, Camelids, etc.)</span>
              </label>
            </div>
            
            {showExotics && (
              <div className="mt-3 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                <div className="flex items-start">
                  <div className="flex-shrink-0">
                    <svg className="h-5 w-5 text-amber-400" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                    </svg>
                  </div>
                  <div className="ml-3">
                    <h4 className="text-sm font-medium text-amber-800">Exotic Livestock Notice</h4>
                    <p className="text-sm text-amber-700 mt-1">
                      Now showing exotic and specialty livestock. Some species require permits and special care. 
                      <a href="/exotics" className="underline ml-1">Learn more about exotic livestock →</a>
                    </p>
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Advanced Filters */}
        <Card className="mb-8 border-emerald-200">
          <CardHeader>
            <CardTitle className="flex items-center text-emerald-900">
              <Filter className="mr-2 h-5 w-5" />
              Filter Animals
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid md:grid-cols-3 lg:grid-cols-6 gap-4 mb-4">
              {/* Category Group */}
              <div>
                <Label className="text-emerald-800 text-sm">Category</Label>
                <Select value={filters.category_group_id || ""} onValueChange={(value) => handleFilterChange('category_group_id', value)}>
                  <SelectTrigger className="border-emerald-200">
                    <SelectValue placeholder="All categories" />
                  </SelectTrigger>
                  <SelectContent>
                    {categoryGroups.map((group, index) => (
                      <SelectItem key={group.id || index} value={group.id || ''}>
                        {group.name || 'Unknown Category'}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              
              {/* Species */}
              <div>
                <Label className="text-emerald-800 text-sm">Species</Label>
                <Select value={filters.species_id || ""} onValueChange={(value) => handleFilterChange('species_id', value)} disabled={!filters.category_group_id}>
                  <SelectTrigger className="border-emerald-200">
                    <SelectValue placeholder="Select species" />
                  </SelectTrigger>
                  <SelectContent>
                    {species.map((spec, index) => (
                      <SelectItem key={spec.id || index} value={spec.id || ''}>
                        {spec.name || 'Unknown Species'}
                        {spec.is_free_range && " 🌿"}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Breed */}
              <div>
                <Label className="text-emerald-800 text-sm">Breed</Label>
                <Select value={filters.breed_id || ""} onValueChange={(value) => handleFilterChange('breed_id', value)} disabled={!filters.species_id}>
                  <SelectTrigger className="border-emerald-200">
                    <SelectValue placeholder="Any breed" />
                  </SelectTrigger>
                  <SelectContent>
                    {breeds.map(breed => (
                      <SelectItem key={breed.id} value={breed.id}>
                        {breed.name}
                        {breed.purpose_hint && ` (${breed.purpose_hint})`}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Product Type */}
              <div>
                <Label className="text-emerald-800 text-sm">Product Type</Label>
                <Select value={filters.product_type_id || undefined} onValueChange={(value) => handleFilterChange('product_type_id', value || "")}>
                  <SelectTrigger className="border-emerald-200">
                    <SelectValue placeholder="Any type" />
                  </SelectTrigger>
                  <SelectContent>
                    {(getFilteredProductTypes() || []).filter(type => type && type.id && type.id !== "").map(type => (
                      <SelectItem key={type.id} value={type.id}>
                        {type.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Listing Type Filter */}
              <div>
                <Label className="text-emerald-800 text-sm">Listing Type</Label>
                <Select value={filters.listing_type} onValueChange={(value) => handleFilterChange('listing_type', value)}>
                  <SelectTrigger className="border-emerald-200">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Types</SelectItem>
                    <SelectItem value="buy_now">Buy Now Only</SelectItem>
                    <SelectItem value="auction">Auctions Only</SelectItem>
                    <SelectItem value="hybrid">Hybrid (Bid + Buy Now)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Province */}
              <div>
                <Label className="text-emerald-800 text-sm">Province</Label>
                <Input
                  placeholder="e.g., Gauteng"
                  value={filters.province}
                  onChange={(e) => handleFilterChange('province', e.target.value)}
                  className="border-emerald-200"
                />
              </div>
            </div>

            {/* Price Range & Sort */}
            <div className="grid md:grid-cols-4 gap-4">
              <div>
                <Label className="text-emerald-800 text-sm">Min Price (R)</Label>
                <Input
                  type="number"
                  placeholder="0"
                  value={filters.price_min}
                  onChange={(e) => handleFilterChange('price_min', e.target.value)}
                  className="border-emerald-200"
                />
              </div>
              <div>
                <Label className="text-emerald-800 text-sm">Max Price (R)</Label>
                <Input
                  type="number"
                  placeholder="10000"
                  value={filters.price_max}
                  onChange={(e) => handleFilterChange('price_max', e.target.value)}
                  className="border-emerald-200"
                />
              </div>
              <div>
                <Label className="text-emerald-800 text-sm">Sort By</Label>
                <Select value={sortBy} onValueChange={setSortBy}>
                  <SelectTrigger className="border-emerald-200">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="newest">Newest First</SelectItem>
                    <SelectItem value="price_low">Price: Low to High</SelectItem>
                    <SelectItem value="price_high">Price: High to Low</SelectItem>
                    <SelectItem value="ending_soon">Ending Soon</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-end">
                <Button onClick={clearFilters} variant="outline" className="w-full border-emerald-300 text-emerald-700 hover:bg-emerald-50">
                  Clear Filters
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Market Summary */}
        <Card className="mb-6 border-emerald-200 bg-gradient-to-r from-emerald-50 to-green-50">
          <CardContent className="p-4">
            <div className="grid md:grid-cols-4 gap-4 text-center">
              <div>
                <p className="text-2xl font-bold text-emerald-900">{listings.length}</p>
                <p className="text-sm text-emerald-600">Total Listings</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-blue-900">
                  {listings.filter(l => l.listing_type === 'buy_now').length}
                </p>
                <p className="text-sm text-blue-600">Buy Now</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-orange-900">
                  {listings.filter(l => l.listing_type === 'auction' || l.listing_type === 'hybrid').length}
                </p>
                <p className="text-sm text-orange-600">Active Auctions</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-purple-900">
                  {listings.filter(l => l.listing_type === 'hybrid').length}
                </p>
                <p className="text-sm text-purple-600">Hybrid Listings</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* AI Market Insights Panel (Future) */}
        {filters.species_id && (
          <Card className="mb-6 border-emerald-200 bg-gradient-to-r from-emerald-50 to-green-50">
            <CardContent className="p-4">
              <div className="flex items-center space-x-3">
                <div className="w-8 h-8 bg-emerald-600 rounded-full flex items-center justify-center">
                  <span className="text-white text-sm">AI</span>
                </div>
                <div>
                  <p className="text-emerald-800 font-medium">Market Insights</p>
                  <p className="text-emerald-600 text-sm">
                    {getSpeciesName(filters.species_id)} average price: R{Math.floor(Math.random() * 500 + 200)} per head
                    • {listings.length} listings available
                    {filters.province && ` in ${filters.province}`}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Category Overview */}
        {!filters.category_group_id && (
          <div className="mb-8">
            <h2 className="text-2xl font-bold text-emerald-900 mb-4">Browse by Category</h2>
            <div className="grid md:grid-cols-2 lg:grid-cols-5 gap-4">
              {categoryGroups.map(group => {
                // Enhanced category count logic
                const groupListings = listings.filter(listing => {
                  // Method 1: Direct species matching
                  if (listing.species && typeof listing.species === 'string') {
                    const speciesName = listing.species.toLowerCase();
                    if (group.name === 'Poultry' && (speciesName.includes('chicken') || speciesName.includes('poultry'))) return true;
                    if (group.name === 'Ruminants' && (speciesName.includes('cattle') || speciesName.includes('goat') || speciesName.includes('sheep'))) return true;
                    if (group.name === 'Rabbits' && speciesName.includes('rabbit')) return true;
                    if (group.name === 'Aquaculture' && (speciesName.includes('fish') || speciesName.includes('aqua'))) return true;
                    if (group.name === 'Other Small Livestock' && (speciesName.includes('pig') || speciesName.includes('duck'))) return true;
                  }
                  
                  // Method 2: Species ID matching (fallback)
                  const listingSpecies = species.find(s => s.id === listing.species_id);
                  if (listingSpecies && listingSpecies.category_group_id === group.id) return true;
                  
                  // Method 3: Breed-based matching (additional fallback)
                  if (listing.breed && typeof listing.breed === 'string') {
                    const breedName = listing.breed.toLowerCase();
                    if (group.name === 'Poultry' && (breedName.includes('ross') || breedName.includes('koekoek') || breedName.includes('chicken'))) return true;
                    if (group.name === 'Ruminants' && (breedName.includes('boer') || breedName.includes('angus') || breedName.includes('brahman'))) return true;
                  }
                  
                  return false;
                });
                
                return (
                  <Card 
                    key={group.id} 
                    className="cursor-pointer hover:shadow-lg transition-shadow border-emerald-200"
                    onClick={() => handleFilterChange('category_group_id', group.id)}
                  >
                    <CardContent className="p-4 text-center">
                      <div className="text-3xl mb-2">
                        {group.name === 'Poultry' && '🐓'}
                        {group.name === 'Ruminants' && '🐄'}
                        {group.name === 'Rabbits' && '🐰'}
                        {group.name === 'Aquaculture' && '🐟'}
                        {group.name === 'Other Small Livestock' && '🕊️'}
                      </div>
                      <h3 className="font-semibold text-emerald-900">{group.name}</h3>
                      <p className="text-sm text-emerald-600">
                        {groupListings.length} listing{groupListings.length !== 1 ? 's' : ''}
                      </p>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </div>
        )}

        {/* Listings Grid */}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {(() => {
            // Apply deliverable filtering
            let filteredListings = listings;
            // console.log('🔍 DEBUG: Raw listings state:', listings.length, 'listings:', listings.map(l => l.title || l.id));
            
            if (deliverableOnly) {
              filteredListings = listings.filter(listing => {
                // Mock service area for demonstration - in real app this comes from API
                const serviceArea = listing.service_area || {
                  mode: 'RADIUS',
                  origin: { lat: -26.2041 + (Math.random() - 0.5) * 4, lng: 28.0473 + (Math.random() - 0.5) * 4 },
                  radius_km: 150 + Math.random() * 200
                };
                
                // Simplified deliverability check - just return true for now
                // In production, this would check actual delivery capabilities
                return listing.delivery_available !== false;
              });
            }
            
            // Apply sorting to filtered listings
            const sortedListings = [...filteredListings].sort((a, b) => {
              switch (sortBy) {
                case 'price_low':
                  return (a.current_bid || a.price_per_unit) - (b.current_bid || b.price_per_unit);
                case 'price_high':
                  return (b.current_bid || b.price_per_unit) - (a.current_bid || a.price_per_unit);
                case 'ending_soon':
                  if (a.listing_type === 'buy_now' && b.listing_type === 'buy_now') return 0;
                  if (a.listing_type === 'buy_now') return 1;
                  if (b.listing_type === 'buy_now') return -1;
                  return new Date(a.auction_end_time) - new Date(b.auction_end_time);
                case 'newest':
                default:
                  return new Date(b.created_at || b.id) - new Date(a.created_at || a.id);
              }
            });

            return sortedListings.length > 0 ? (
              <>
                {/* {console.log('🔍 DEBUG: Rendering', sortedListings.length, 'listings:', sortedListings.map(l => l.title))} */}
                {sortedListings.map(listing => (
                  <ListingCard
                    key={listing.id} 
                    listing={listing} 
                    onViewDetails={handleViewDetails}
                    onBidPlaced={handlePlaceBid}
                    onAddToCart={cartUpdateCallback}
                  />
                ))}
              </>
            ) : (
              <div className="col-span-full text-center py-12">
                <div className="w-24 h-24 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-4">
                  <Search className="h-12 w-12 text-emerald-400" />
                </div>
                <h3 className="text-xl font-semibold text-emerald-900 mb-2">
                  {deliverableOnly ? 'No deliverable listings found' : 'No livestock found'}
                </h3>
                <p className="text-emerald-600">
                  {deliverableOnly 
                    ? 'Try turning off the delivery filter or updating your location.'
                    : 'Try adjusting your filters or check back later for new listings.'
                  }
                </p>
                {deliverableOnly && (
                  <Button 
                    variant="outline" 
                    className="mt-4"
                    onClick={() => setDeliverableOnly(false)}
                  >
                    Show All Listings
                  </Button>
                )}
              </div>
            );
          })()}
        </div>
      </div>

      {/* Order Modal */}
      {showOrderModal && selectedListing && (
        <OrderModal
          listing={selectedListing}
          isOpen={showOrderModal}
          onClose={() => setShowOrderModal(false)}
        />
      )}

      {/* Bidding Modal */}
      {showBiddingModal && selectedListing && (
        <BiddingModal
          listing={selectedListing}
          isOpen={showBiddingModal}
          onClose={() => setShowBiddingModal(false)}
          onBidPlaced={handleBidPlaced}
        />
      )}
      <Footer />
    </div>
  );
}
export default Marketplace;