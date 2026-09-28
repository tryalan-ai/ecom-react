import ProductCard from './ProductCard';
import InlineLoader from '../ui/InlineLoader';
import { Package } from 'lucide-react';

const ProductGrid = ({ products, loading, loadStartedAt = null, loadDetail = null }) => {
  if (loading) {
    return (
      <div className="space-y-4">
        {/* Claude Code/Codex-style inline loader: spinner + live elapsed/step
            metadata, complementary to the skeleton grid below (kept intact). */}
        <InlineLoader
          status="Fetching products"
          detail={loadDetail}
          startedAt={loadStartedAt}
          countLabel="products"
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {[...Array(8)].map((_, i) => (
          <div key={i} className="card animate-pulse">
            <div className="w-full h-48 bg-gray-200 rounded-lg mb-3" />
            <div className="space-y-2">
              <div className="h-4 bg-gray-200 rounded w-1/2" />
              <div className="h-4 bg-gray-200 rounded w-3/4" />
              <div className="h-4 bg-gray-200 rounded w-1/4" />
            </div>
          </div>
        ))}
        </div>
      </div>
    );
  }

  if (products.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <Package className="w-16 h-16 text-gray-300 mb-4" />
        <h3 className="text-lg font-medium text-gray-900 mb-2">No products found</h3>
        <p className="text-gray-600 text-center">
          Try adjusting your filters or search terms
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
      {products.map((product) => (
        <ProductCard key={product.id} product={product} />
      ))}
    </div>
  );
};

export default ProductGrid;
