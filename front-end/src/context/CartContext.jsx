import { createContext, useContext, useReducer, useEffect, useState } from 'react';
import { calculateCartTotals } from '../utils/calculations';

const CartContext = createContext();

// Action types
const ADD_TO_CART = 'ADD_TO_CART';
const REMOVE_FROM_CART = 'REMOVE_FROM_CART';
const UPDATE_QUANTITY = 'UPDATE_QUANTITY';
const APPLY_PROMO_CODE = 'APPLY_PROMO_CODE';
const CLEAR_CART = 'CLEAR_CART';
const LOAD_CART = 'LOAD_CART';

// Cart reducer
const cartReducer = (state, action) => {
  let newState;

  switch (action.type) {
    case ADD_TO_CART: {
      const existingItemIndex = state.items.findIndex(
        item => item.productId === action.payload.productId
      );

      if (existingItemIndex > -1) {
        // Item already exists, update quantity
        const newItems = [...state.items];
        newItems[existingItemIndex] = {
          ...newItems[existingItemIndex],
          quantity: newItems[existingItemIndex].quantity + action.payload.quantity
        };
        newState = { ...state, items: newItems };
      } else {
        // Add new item
        newState = {
          ...state,
          items: [...state.items, action.payload]
        };
      }
      break;
    }

    case REMOVE_FROM_CART: {
      newState = {
        ...state,
        items: state.items.filter(item => item.productId !== action.payload)
      };
      break;
    }

    case UPDATE_QUANTITY: {
      const newItems = state.items.map(item =>
        item.productId === action.payload.productId
          ? { ...item, quantity: action.payload.quantity }
          : item
      );
      newState = { ...state, items: newItems };
      break;
    }

    case APPLY_PROMO_CODE: {
      newState = { ...state, promoCode: action.payload };
      break;
    }

    case CLEAR_CART: {
      newState = {
        items: [],
        promoCode: null,
        totals: { subtotal: 0, tax: 0, shipping: 0, discount: 0, total: 0 }
      };
      break;
    }

    case LOAD_CART: {
      return action.payload;
    }

    default:
      return state;
  }

  // Calculate totals
  const totals = calculateCartTotals(newState.items, newState.promoCode);
  newState.totals = totals;

  return newState;
};

const initialState = {
  items: [],
  promoCode: null,
  totals: {
    subtotal: 0,
    tax: 0,
    shipping: 0,
    discount: 0,
    total: 0
  }
};

export const CartProvider = ({ children }) => {
  const [state, dispatch] = useReducer(cartReducer, initialState);
  // Tracks whether the persisted cart has been read. Route guards must wait for
  // this so a direct load of /checkout doesn't see an empty cart and redirect
  // before the saved cart is hydrated.
  const [isHydrated, setIsHydrated] = useState(false);

  // Load cart from localStorage on mount
  useEffect(() => {
    const savedCart = localStorage.getItem('cart');
    if (savedCart) {
      try {
        const parsedCart = JSON.parse(savedCart);
        dispatch({ type: LOAD_CART, payload: parsedCart });
      } catch (error) {
        console.error('Error loading cart from localStorage:', error);
      }
    }
    setIsHydrated(true);
  }, []);

  // Save cart to localStorage whenever it changes, but only after hydration so
  // the initial empty state can't overwrite a persisted cart.
  useEffect(() => {
    if (!isHydrated) return;
    localStorage.setItem('cart', JSON.stringify(state));
  }, [state, isHydrated]);

  const addToCart = (product, quantity = 1) => {
    dispatch({
      type: ADD_TO_CART,
      payload: {
        productId: product.id,
        product: {
          id: product.id,
          name: product.name,
          price: product.price,
          primaryImage: product.primaryImage,
          inStock: product.inStock,
          stockCount: product.stockCount
        },
        quantity,
        price: product.price
      }
    });
  };

  const removeFromCart = (productId) => {
    dispatch({ type: REMOVE_FROM_CART, payload: productId });
  };

  const updateQuantity = (productId, quantity) => {
    if (quantity <= 0) {
      removeFromCart(productId);
    } else {
      dispatch({
        type: UPDATE_QUANTITY,
        payload: { productId, quantity }
      });
    }
  };

  const applyPromoCode = (code) => {
    dispatch({ type: APPLY_PROMO_CODE, payload: code });
  };

  const clearCart = () => {
    dispatch({ type: CLEAR_CART });
  };

  const getCartItemCount = () => {
    return state.items.reduce((total, item) => total + item.quantity, 0);
  };

  const value = {
    cart: state,
    isHydrated,
    addToCart,
    removeFromCart,
    updateQuantity,
    applyPromoCode,
    clearCart,
    getCartItemCount
  };

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
};

export const useCart = () => {
  const context = useContext(CartContext);
  if (!context) {
    throw new Error('useCart must be used within a CartProvider');
  }
  return context;
};

export default CartContext;
