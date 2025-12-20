import { createSlice } from '@reduxjs/toolkit';

// Load cart from localStorage on initialization
const loadCartFromStorage = () => {
  try {
    const cartData = localStorage.getItem('cart');
    if (cartData) {
      return JSON.parse(cartData);
    }
  } catch (error) {
    console.error('Error loading cart from localStorage:', error);
  }
  return { items: [] };
};

// Save cart to localStorage
const saveCartToStorage = (cart) => {
  try {
    localStorage.setItem('cart', JSON.stringify(cart));
  } catch (error) {
    console.error('Error saving cart to localStorage:', error);
  }
};

const initialState = loadCartFromStorage();

const cartSlice = createSlice({
  name: 'cart',
  initialState,
  reducers: {
    addItem: (state, action) => {
      const { listing_id, title, price, qty = 1, unit = 'head', species, product_type, image, seller_id, location } = action.payload;
      
      // Check if item already exists in cart
      const existingItemIndex = state.items.findIndex(
        item => item.listing_id === listing_id
      );
      
      if (existingItemIndex >= 0) {
        // Update quantity if item exists
        state.items[existingItemIndex].qty += qty;
      } else {
        // Add new item
        state.items.push({
          listing_id,
          title,
          price: parseFloat(price) || 0,
          qty,
          unit,
          species,
          product_type,
          image,
          seller_id,
          location,
          added_at: new Date().toISOString()
        });
      }
      
      // Sync with localStorage
      saveCartToStorage(state);
    },
    
    removeItem: (state, action) => {
      const itemId = action.payload;
      state.items = state.items.filter(
        item => item.listing_id !== itemId && item.id !== itemId
      );
      
      // Sync with localStorage
      saveCartToStorage(state);
    },
    
    updateItemQuantity: (state, action) => {
      const { itemId, quantity } = action.payload;
      const item = state.items.find(
        item => item.listing_id === itemId || item.id === itemId
      );
      
      if (item) {
        if (quantity <= 0) {
          // Remove item if quantity is 0 or less
          state.items = state.items.filter(
            i => i.listing_id !== itemId && i.id !== itemId
          );
        } else {
          item.qty = quantity;
        }
      }
      
      // Sync with localStorage
      saveCartToStorage(state);
    },
    
    clearCart: (state) => {
      state.items = [];
      
      // Sync with localStorage
      saveCartToStorage(state);
    },
    
    setCart: (state, action) => {
      state.items = action.payload.items || action.payload || [];
      
      // Sync with localStorage
      saveCartToStorage(state);
    },
    
    // Sync cart from API response (for authenticated users)
    syncFromAPI: (state, action) => {
      const apiItems = action.payload.items || action.payload || [];
      
      // Transform API cart items to our format
      state.items = apiItems.map(item => ({
        id: item.id,
        listing_id: item.listing_id || item.listing?.id,
        title: item.listing?.title || item.title || 'Unknown Item',
        price: item.price || item.price_per_unit || item.listing?.price_per_unit || 0,
        qty: item.quantity || item.qty || 1,
        quantity: item.quantity || item.qty || 1,
        unit: item.unit || item.listing?.unit || 'head',
        species: item.species || item.listing?.species,
        product_type: item.product_type || item.listing?.product_type,
        image: item.listing?.images?.[0] || item.listing?.media?.[0]?.url || item.image,
        seller_id: item.seller_id || item.listing?.seller_id,
        location: item.listing?.location?.province || item.location,
        added_at: item.added_at || new Date().toISOString()
      }));
      
      // Sync with localStorage
      saveCartToStorage(state);
    }
  }
});

export const { addItem, removeItem, updateItemQuantity, clearCart, setCart, syncFromAPI } = cartSlice.actions;

// Selectors
export const selectCartItems = (state) => state.cart.items || [];
export const selectCartItemCount = (state) => {
  return (state.cart.items || []).reduce((sum, item) => sum + (item.qty || item.quantity || 1), 0);
};
export const selectCartTotal = (state) => {
  return (state.cart.items || []).reduce((total, item) => {
    const price = item.price || item.price_per_unit || 0;
    const quantity = item.qty || item.quantity || 1;
    return total + (price * quantity);
  }, 0);
};

export default cartSlice.reducer;

