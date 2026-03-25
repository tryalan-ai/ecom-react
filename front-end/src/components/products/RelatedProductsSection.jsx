import ProductCard from './ProductCard';

const RelatedProductsSection = ({ products }) => {
  if (!products || products.length === 0) {
    return null;
  }

  return (
    <div className="border-t border-gray-200 pt-12">
      <h2 className="text-3xl font-bold text-gray-900 mb-6">Related Products</h2>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 sm:gap-6">
        {products.map((product) => (
          <ProductCard key={product.id} product={product} />
        ))}
      </div>
    </div>
  );
};

export default RelatedProductsSection;
