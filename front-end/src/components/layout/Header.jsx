import { ShoppingCart, Store } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useCart } from '../../context/CartContext';
import { useState } from 'react';
import CartDrawer from '../cart/CartDrawer';

const Header = () => {
  const { getCartItemCount } = useCart();
  const [isCartOpen, setIsCartOpen] = useState(false);
  const cartCount = getCartItemCount();

  return (
    <>
      <header className="sticky top-0 z-40 bg-white border-b border-gray-200 shadow-sm">
        <div className="container mx-auto px-4">
          <div className="flex items-center justify-between h-16">
            {/* Logo */}
            <Link to="/" className="flex items-center gap-2 text-primary-600 hover:text-primary-700 transition-colors">
              <Store className="w-8 h-8" />
              <span className="text-xl font-bold">E-Shop</span>
            </Link>

            {/* Actions */}
            <div className="flex items-center gap-4">
              {/* Cart */}
              <button
                onClick={() => setIsCartOpen(true)}
                aria-label="Open cart"
                className="relative p-2 text-gray-700 hover:text-primary-600 transition-colors"
              >
                <ShoppingCart className="w-6 h-6" aria-hidden="true" />
                {cartCount > 0 && (
                  <span
                    data-testid="cart-badge"
                    className="absolute -top-1 -right-1 bg-primary-600 text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center"
                  >
                    {cartCount}
                  </span>
                )}
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Cart Drawer */}
      <CartDrawer isOpen={isCartOpen} onClose={() => setIsCartOpen(false)} />
    </>
  );
};

export default Header;
