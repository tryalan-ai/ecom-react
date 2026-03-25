import { useState } from 'react';
import { Heart, Star, Minus, Plus } from 'lucide-react';
import { formatPrice, calculateDiscountPercentage } from '../../utils/calculations';
import { useCart } from '../../context/CartContext';
import Button from '../ui/Button';
import Toast from '../ui/Toast';

const ProductInfoSection = ({ product }) => {
  const { addToCart } = useCart();
  const [quantity, setQuantity] = useState(1);
  const [selectedVariants, setSelectedVariants] = useState({});
  const [showToast, setShowToast] = useState(false);
  const [isWishlisted, setIsWishlisted] = useState(false);

  // Parse variants from product attributes
  const variants = product.attributes && typeof product.attributes === 'string'
    ? JSON.parse(product.attributes)
    : product.attributes || {};

  const discountPercentage = calculateDiscountPercentage(
    product.originalPrice,
    product.price
  );

  const handleQuantityChange = (value) => {
    const num = Math.max(1, Math.min(parseInt(value) || 1, product.stockCount || 1));
    setQuantity(num);
  };

  const handleVariantSelect = (variantName, value) => {
    setSelectedVariants(prev => ({
      ...prev,
      [variantName]: value
    }));
  };

  const handleAddToCart = () => {
    if (product.inStock) {
      addToCart(product, quantity);
      setShowToast(true);
      // Reset quantity after adding
      setQuantity(1);
    }
  };

  const handleToggleWishlist = () => {
    setIsWishlisted(!isWishlisted);
  };

  const variantEntries = Object.entries(variants);
  const hasVariants = variantEntries.length > 0;

  return (
    <>
      <div className="flex flex-col gap-6">
        {/* Brand */}
        <div>
          <p className="text-sm text-gray-500 uppercase font-medium">{product.brand}</p>
        </div>

        {/* Name */}
        <div>
          <h1 className="text-3xl sm:text-4xl font-bold text-gray-900">
            {product.name}
          </h1>
        </div>

        {/* Rating */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1">
            {[...Array(5)].map((_, i) => (
              <Star
                key={i}
                className={`w-5 h-5 ${
                  i < Math.floor(product.rating)
                    ? 'fill-yellow-400 text-yellow-400'
                    : 'text-gray-300'
                }`}
              />
            ))}
          </div>
          <span className="font-semibold text-gray-900">{product.rating}</span>
          <span className="text-gray-500">({product.reviewCount} reviews)</span>
        </div>

        {/* Pricing */}
        <div className="border-t border-b border-gray-200 py-4">
          <div className="flex items-baseline gap-3">
            <span className="text-3xl font-bold text-gray-900">
              {formatPrice(product.price)}
            </span>
            {product.originalPrice && (
              <span className="text-lg text-gray-500 line-through">
                {formatPrice(product.originalPrice)}
              </span>
            )}
            {discountPercentage > 0 && (
              <span className="text-lg font-semibold text-red-600">
                Save {discountPercentage}%
              </span>
            )}
          </div>
          <p className="text-sm text-gray-600 mt-2">
            {product.inStock ? (
              <span className="text-green-600 font-medium">
                ✓ In Stock ({product.stockCount} available)
              </span>
            ) : (
              <span className="text-red-600 font-medium">Out of Stock</span>
            )}
          </p>
        </div>

        {/* Description */}
        <div>
          <p className="text-gray-700 leading-relaxed">
            {product.description}
          </p>
        </div>

        {/* Variants */}
        {hasVariants && (
          <div className="space-y-4">
            {variantEntries.map(([variantName, options]) => {
              const optionArray = Array.isArray(options) ? options : [];
              const isLargeList = optionArray.length > 4;

              return (
                <div key={variantName}>
                  <label className="block text-sm font-semibold text-gray-900 mb-3 capitalize">
                    {variantName}
                  </label>

                  {isLargeList ? (
                    /* Dropdown for 5+ options */
                    <select
                      value={selectedVariants[variantName] || ''}
                      onChange={(e) => handleVariantSelect(variantName, e.target.value)}
                      className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                    >
                      <option value="">Select {variantName}</option>
                      {optionArray.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  ) : (
                    /* Buttons for 2-4 options */
                    <div className="flex flex-wrap gap-2">
                      {optionArray.map((option) => (
                        <button
                          key={option}
                          onClick={() => handleVariantSelect(variantName, option)}
                          className={`px-4 py-2 rounded-lg font-medium transition-all border-2 ${
                            selectedVariants[variantName] === option
                              ? 'border-primary-600 bg-primary-50 text-primary-600'
                              : 'border-gray-200 text-gray-700 hover:border-gray-300'
                          }`}
                        >
                          {option}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Quantity Selector */}
        <div className="flex items-center gap-4">
          <label className="text-sm font-semibold text-gray-900">Quantity:</label>
          <div className="flex items-center border border-gray-300 rounded-lg">
            <button
              onClick={() => handleQuantityChange(quantity - 1)}
              disabled={quantity <= 1 || !product.inStock}
              className="p-2 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
              aria-label="Decrease quantity"
            >
              <Minus className="w-4 h-4" />
            </button>
            <input
              type="number"
              value={quantity}
              onChange={(e) => handleQuantityChange(e.target.value)}
              min="1"
              max={product.stockCount || 1}
              disabled={!product.inStock}
              className="w-16 text-center border-none focus:outline-none disabled:bg-gray-50"
            />
            <button
              onClick={() => handleQuantityChange(quantity + 1)}
              disabled={quantity >= (product.stockCount || 1) || !product.inStock}
              className="p-2 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
              aria-label="Increase quantity"
            >
              <Plus className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Add to Cart & Wishlist Buttons */}
        <div className="flex gap-3 sm:gap-4">
          <Button
            onClick={handleAddToCart}
            disabled={!product.inStock}
            size="lg"
            className="flex-1"
          >
            Add to Cart
          </Button>
          <button
            onClick={handleToggleWishlist}
            className="p-3 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            aria-label="Add to wishlist"
          >
            <Heart
              className={`w-6 h-6 ${
                isWishlisted
                  ? 'fill-red-500 text-red-500'
                  : 'text-gray-600'
              }`}
            />
          </button>
        </div>

        {/* Additional Info */}
        <div className="space-y-2 text-sm text-gray-600">
          <p>✓ Free shipping on orders over $100</p>
          <p>✓ 30-day money-back guarantee</p>
          <p>✓ Secure checkout</p>
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

export default ProductInfoSection;
