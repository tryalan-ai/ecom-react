import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getProductById, getProducts } from '../utils/api';
import ProductImageGallery from '../components/products/ProductImageGallery';
import ProductInfoSection from '../components/products/ProductInfoSection';
import RelatedProductsSection from '../components/products/RelatedProductsSection';
import ProductNotFound from './ProductNotFound';
import { AlertCircle } from 'lucide-react';
import Button from '../components/ui/Button';

const ProductDetailPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [product, setProduct] = useState(null);
  const [relatedProducts, setRelatedProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    window.scrollTo(0, 0);
    fetchProduct();
  }, [id]);

  useEffect(() => {
    if (product && product.category) {
      fetchRelatedProducts();
    }
  }, [product]);

  const fetchProduct = async () => {
    setLoading(true);
    setError(null);
    setNotFound(false);
    try {
      const response = await getProductById(id);
      if (response && response.data) {
        setProduct(response.data);
      } else {
        setNotFound(true);
      }
    } catch (err) {
      console.error('Error fetching product:', err);
      if (err.response && err.response.status === 404) {
        setNotFound(true);
      } else {
        setError('Failed to load product. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  const fetchRelatedProducts = async () => {
    try {
      const response = await getProducts({
        category: product.category,
        limit: 6
      });
      if (response && response.data && response.data.products) {
        // Filter out current product and limit to 4-6 items
        const filtered = response.data.products
          .filter(p => p.id !== product.id)
          .slice(0, 6);
        setRelatedProducts(filtered);
      }
    } catch (err) {
      console.error('Error fetching related products:', err);
    }
  };

  // Loading skeleton
  if (loading) {
    return (
      <div className="container mx-auto px-4 py-6">
        <div className="flex flex-col lg:grid lg:grid-cols-2 gap-8">
          {/* Image skeleton */}
          <div className="bg-gray-200 rounded-lg h-96 sm:h-96 lg:h-[600px] animate-pulse" />

          {/* Info skeleton */}
          <div className="space-y-6">
            <div className="h-6 bg-gray-200 rounded w-24 animate-pulse" />
            <div className="h-8 bg-gray-200 rounded w-3/4 animate-pulse" />
            <div className="h-6 bg-gray-200 rounded w-32 animate-pulse" />
            <div className="h-24 bg-gray-200 rounded animate-pulse" />
            <div className="h-10 bg-gray-200 rounded w-full animate-pulse" />
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="container mx-auto px-4 py-6">
        <div className="flex flex-col items-center justify-center py-12">
          <AlertCircle className="w-16 h-16 text-red-500 mb-4" />
          <h2 className="text-2xl font-bold text-gray-900 mb-2">Error Loading Product</h2>
          <p className="text-gray-600 text-center mb-6 max-w-md">{error}</p>
          <div className="flex gap-4">
            <Button variant="primary" onClick={fetchProduct}>
              Try Again
            </Button>
            <Button variant="outline" onClick={() => navigate('/')}>
              Back to Products
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // Not found state
  if (notFound) {
    return <ProductNotFound />;
  }

  // Product detail view
  if (!product) {
    return null;
  }

  return (
    <div className="flex flex-col min-h-screen">
      <div className="container mx-auto px-4 py-6 flex-1">
        {/* Breadcrumb / Back button */}
        <button
          onClick={() => navigate('/')}
          className="text-primary-600 hover:text-primary-700 text-sm font-medium mb-6 inline-flex items-center gap-1"
        >
          ← Back to Products
        </button>

        {/* Product Detail Section */}
        <div className="flex flex-col lg:grid lg:grid-cols-2 gap-8 mb-12">
          {/* Left: Image Gallery */}
          <div>
            <ProductImageGallery product={product} />
          </div>

          {/* Right: Product Info */}
          <div>
            <ProductInfoSection product={product} />
          </div>
        </div>

        {/* Related Products Section */}
        {relatedProducts.length > 0 && (
          <RelatedProductsSection products={relatedProducts} />
        )}
      </div>
    </div>
  );
};

export default ProductDetailPage;
