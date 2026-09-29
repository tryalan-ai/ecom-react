import { ShoppingCart, Star } from 'lucide-react';
import { formatPrice, calculateDiscountPercentage } from '../../utils/calculations';
import { useCart } from '../../context/CartContext';
import { useState } from 'react';
import Button from '../ui/Button';
import Toast from '../ui/Toast';

const ProductCard = ({ product }) => {
  const { addToCart } = useCart();
  const [showToast, setShowToast] = useState(false);

  const handleAddToCart = () => {
    if (product.inStock) {
      addToCart(product, 1);
      setShowToast(true);
    }
  };

  const discountPercentage = calculateDiscountPercentage(
    product.originalPrice,
    product.price
  );

  return (
    <>
      <div className="card hover:shadow-md transition-shadow group">
        {/* Image */}
        <div className="relative mb-3">
          <img
            src={product.primaryImage}
            alt={product.name}
            loading="lazy"
            decoding="async"
            className="w-full h-48 object-cover rounded-lg"
          />
          {discountPercentage > 0 && (
            <span className="absolute top-2 left-2 bg-red-500 text-white text-xs font-bold px-2 py-1 rounded">
              -{discountPercentage}%
            </span>
          )}
          {!product.inStock && (
            <span className="absolute top-2 right-2 bg-gray-800 text-white text-xs font-bold px-2 py-1 rounded">
              Out of Stock
            </span>
          )}
        </div>

        {/* Content */}
        <div className="space-y-2">
          {/* Brand */}
          <p className="text-xs text-gray-500 uppercase">{product.brand}</p>

          {/* Name */}
          <h3 className="font-medium text-gray-900 line-clamp-2 min-h-[2.5rem]">
            {product.name}
          </h3>

          {/* Rating */}
          <div className="flex items-center gap-1">
            <Star className="w-4 h-4 fill-yellow-400 text-yellow-400" />
            <span className="text-sm font-medium">{product.rating}</span>
            <span className="text-sm text-gray-500">({product.reviewCount})</span>
          </div>

          {/* Price */}
          <div className="flex items-center gap-2">
            <span className="text-lg font-bold text-gray-900">
              {formatPrice(product.price)}
            </span>
            {product.originalPrice && (
              <span className="text-sm text-gray-500 line-through">
                {formatPrice(product.originalPrice)}
              </span>
            )}
          </div>

          {/* Add to Cart Button */}
          <Button
            onClick={handleAddToCart}
            disabled={!product.inStock}
            className="w-full flex items-center justify-center gap-2"
          >
            <ShoppingCart className="w-4 h-4" />
            {product.inStock ? 'Add to Cart' : 'Out of Stock'}
          </Button>
        </div>
      </div>

      {showToast && (
        <Toast
          message="Product added to cart!"
          type="success"
          onClose={() => setShowToast(false)}
        />
      )}
    </>
  );
};

export default ProductCard;
