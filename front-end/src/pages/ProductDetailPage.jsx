import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getProductById, getProducts } from '../utils/api';
import { formatPrice, calculateDiscountPercentage } from '../utils/calculations';
import { useCart } from '../context/CartContext';
import ImageGallery from '../components/products/ImageGallery';
import RelatedProducts from '../components/products/RelatedProducts';
import Button from '../components/ui/Button';
import Toast from '../components/ui/Toast';
import { Star, ShoppingCart, ArrowLeft, Truck, RotateCcw } from 'lucide-react';

const ProductDetailPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { addToCart } = useCart();

  const [product, setProduct] = useState(null);
  const [relatedProducts, setRelatedProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [quantity, setQuantity] = useState(1);
  const [showToast, setShowToast] = useState(false);

  useEffect(() => {
    fetchProduct();
  }, [id]);

  const fetchProduct = async () => {
    setLoading(true);
    try {
      const response = await getProductById(id);
      setProduct(response.data);

      // Fetch related products from the same category
      if (response.data.category) {
        const relatedResponse = await getProducts({
          category: response.data.category,
          limit: 5
        });
        // Filter out the current product
        const filtered = relatedResponse.data.products.filter(p => p.id !== response.data.id);
        setRelatedProducts(filtered);
      }
    } catch (error) {
      console.error('Error fetching product:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAddToCart = () => {
    if (product && product.inStock) {
      addToCart(product, quantity);
      setShowToast(true);
      setQuantity(1);
    }
  };

  const handleQuantityChange = (e) => {
    const value = Math.max(1, Math.min(product.stockCount || 10, parseInt(e.target.value) || 1));
    setQuantity(value);
  };

  const incrementQuantity = () => {
    setQuantity(prev => Math.min(product.stockCount || 10, prev + 1));
  };

  const decrementQuantity = () => {
    setQuantity(prev => Math.max(1, prev - 1));
  };

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-center gap-2 mb-8">
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-2 text-blue-600 hover:text-blue-700"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Products
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div className="bg-gray-200 h-96 rounded-lg animate-pulse" />
          <div className="space-y-4">
            <div className="h-8 bg-gray-200 rounded w-3/4 animate-pulse" />
            <div className="h-4 bg-gray-200 rounded w-1/2 animate-pulse" />
            <div className="h-6 bg-gray-200 rounded w-1/4 animate-pulse" />
          </div>
        </div>
      </div>
    );
  }

  if (!product) {
    return (
      <div className="container mx-auto px-4 py-8 text-center">
        <h1 className="text-2xl font-bold mb-4">Product Not Found</h1>
        <Button onClick={() => navigate('/')}>Back to Products</Button>
      </div>
    );
  }

  const discountPercentage = calculateDiscountPercentage(
    product.originalPrice,
    product.price
  );

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Back Button */}
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-2 text-blue-600 hover:text-blue-700 mb-8 font-medium"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Products
      </button>

      {/* Main Product Section */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-12">
        {/* Image Gallery */}
        <div>
          <ImageGallery
            primaryImage={product.primaryImage}
            images={product.images || []}
            productName={product.name}
          />
        </div>

        {/* Product Details */}
        <div className="space-y-6">
          {/* Brand */}
          <div>
            <p className="text-xs text-gray-500 uppercase font-semibold">
              {product.brand}
            </p>
          </div>

          {/* Title */}
          <div>
            <h1 className="text-3xl font-bold text-gray-900 mb-2">
              {product.name}
            </h1>
          </div>

          {/* Rating */}
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1">
              {[...Array(5)].map((_, i) => (
                <Star
                  key={i}
                  className={`w-5 h-5 ${
                    i < Math.round(product.rating)
                      ? 'fill-yellow-400 text-yellow-400'
                      : 'text-gray-300'
                  }`}
                />
              ))}
            </div>
            <span className="text-lg font-semibold text-gray-900">
              {product.rating}
            </span>
            <span className="text-gray-600">
              ({product.reviewCount} reviews)
            </span>
          </div>

          {/* Price */}
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <span className="text-4xl font-bold text-gray-900">
                {formatPrice(product.price)}
              </span>
              {product.originalPrice && (
                <>
                  <span className="text-lg text-gray-500 line-through">
                    {formatPrice(product.originalPrice)}
                  </span>
                  {discountPercentage > 0 && (
                    <span className="text-lg font-bold text-red-500">
                      -{discountPercentage}% off
                    </span>
                  )}
                </>
              )}
            </div>
          </div>

          {/* Stock Status */}
          <div className="flex items-center gap-2">
            <div
              className={`w-3 h-3 rounded-full ${
                product.inStock ? 'bg-green-500' : 'bg-red-500'
              }`}
            />
            <span
              className={`text-sm font-medium ${
                product.inStock ? 'text-green-700' : 'text-red-700'
              }`}
            >
              {product.inStock
                ? `In Stock (${product.stockCount} available)`
                : 'Out of Stock'}
            </span>
          </div>

          {/* Description */}
          {product.description && (
            <div>
              <h3 className="text-sm font-semibold text-gray-900 mb-2">
                Description
              </h3>
              <p className="text-gray-600 leading-relaxed">
                {product.description}
              </p>
            </div>
          )}

          {/* Attributes */}
          {product.attributes && Object.keys(product.attributes).length > 0 && (
            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-gray-900">
                Specifications
              </h3>
              <div className="grid grid-cols-2 gap-3">
                {Object.entries(product.attributes).map(([key, value]) => (
                  <div
                    key={key}
                    className="border border-gray-200 rounded-lg p-3"
                  >
                    <p className="text-xs text-gray-500 uppercase font-semibold">
                      {key}
                    </p>
                    <p className="text-sm font-medium text-gray-900">
                      {Array.isArray(value) ? value.join(', ') : value}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Quantity and Add to Cart */}
          <div className="space-y-4 pt-4 border-t border-gray-200">
            <div className="flex items-center gap-4">
              <div className="flex items-center border border-gray-300 rounded-lg">
                <button
                  onClick={decrementQuantity}
                  disabled={!product.inStock || quantity === 1}
                  className="px-3 py-2 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  −
                </button>
                <input
                  type="number"
                  value={quantity}
                  onChange={handleQuantityChange}
                  disabled={!product.inStock}
                  className="w-16 text-center border-l border-r border-gray-300 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
                  min="1"
                  max={product.stockCount || 10}
                />
                <button
                  onClick={incrementQuantity}
                  disabled={!product.inStock || quantity >= (product.stockCount || 10)}
                  className="px-3 py-2 hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  +
                </button>
              </div>
              <span className="text-sm text-gray-600">
                {product.stockCount ? `${product.stockCount} in stock` : 'Limited availability'}
              </span>
            </div>

            <Button
              onClick={handleAddToCart}
              disabled={!product.inStock}
              className="w-full flex items-center justify-center gap-2 py-3 text-lg"
            >
              <ShoppingCart className="w-5 h-5" />
              {product.inStock ? 'Add to Cart' : 'Out of Stock'}
            </Button>
          </div>

          {/* Shipping and Returns Info */}
          <div className="grid grid-cols-2 gap-4 pt-4 border-t border-gray-200">
            <div className="flex gap-3">
              <Truck className="w-5 h-5 text-gray-600 flex-shrink-0 mt-1" />
              <div>
                <p className="text-sm font-semibold text-gray-900">
                  Free Shipping
                </p>
                <p className="text-xs text-gray-600">On orders over $100</p>
              </div>
            </div>
            <div className="flex gap-3">
              <RotateCcw className="w-5 h-5 text-gray-600 flex-shrink-0 mt-1" />
              <div>
                <p className="text-sm font-semibold text-gray-900">
                  Easy Returns
                </p>
                <p className="text-xs text-gray-600">30-day return policy</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Related Products Section */}
      {relatedProducts.length > 0 && (
        <div>
          <h2 className="text-2xl font-bold mb-6">Related Products</h2>
          <RelatedProducts products={relatedProducts} />
        </div>
      )}

      {showToast && (
        <Toast
          message={`${product.name} added to cart!`}
          type="success"
          onClose={() => setShowToast(false)}
        />
      )}
    </div>
  );
};

export default ProductDetailPage;
