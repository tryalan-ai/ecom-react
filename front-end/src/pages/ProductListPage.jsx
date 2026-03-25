import { useState, useEffect } from 'react';
import { getProducts } from '../utils/api';
import ProductGrid from '../components/products/ProductGrid';
import FilterSidebar from '../components/products/FilterSidebar';
import SearchBar from '../components/products/SearchBar';
import SortDropdown from '../components/products/SortDropdown';
import ActiveFilters from '../components/products/ActiveFilters';
import { Filter } from 'lucide-react';

const ProductListPage = () => {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pagination, setPagination] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [sortBy, setSortBy] = useState('featured');
  const [showMobileFilters, setShowMobileFilters] = useState(false);

  const [filters, setFilters] = useState({
    categories: [],
    brands: [],
    minPrice: null,
    maxPrice: null,
    minRating: null,
    inStock: null
  });

  useEffect(() => {
    fetchProducts();
  }, [filters, searchTerm, sortBy]);

  const fetchProducts = async () => {
    setLoading(true);
    try {
      const params = {
        search: searchTerm || undefined,
        sortBy,
        category: filters.categories.length > 0 ? filters.categories : undefined,
        brand: filters.brands.length > 0 ? filters.brands : undefined,
        minPrice: filters.minPrice || undefined,
        maxPrice: filters.maxPrice || undefined,
        minRating: filters.minRating || undefined,
        inStock: filters.inStock !== null ? filters.inStock : undefined
      };

      console.log('[Products] Fetching with params:', params);
      const response = await getProducts(params);
      console.log('[Products] Loaded:', { count: response.data.products.length, total: response.data.pagination.total });
      setProducts(response.data.products);
      setPagination(response.data.pagination);
    } catch (error) {
      console.error('Error fetching products:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveFilter = (type, value) => {
    if (type === 'category') {
      setFilters({
        ...filters,
        categories: filters.categories.filter(c => c !== value)
      });
    } else if (type === 'brand') {
      setFilters({
        ...filters,
        brands: filters.brands.filter(b => b !== value)
      });
    } else if (type === 'price') {
      setFilters({
        ...filters,
        minPrice: null,
        maxPrice: null
      });
    } else if (type === 'rating') {
      setFilters({
        ...filters,
        minRating: null
      });
    } else if (type === 'stock') {
      setFilters({
        ...filters,
        inStock: null
      });
    }
  };

  const handleClearFilters = () => {
    setFilters({
      categories: [],
      brands: [],
      minPrice: null,
      maxPrice: null,
      minRating: null,
      inStock: null
    });
    setSearchTerm('');
  };

  return (
    <div className="container mx-auto px-4 py-6">
      {/* Header Section */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold mb-4">Products</h1>

        {/* Search and Sort */}
        <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
          <SearchBar onSearch={setSearchTerm} initialValue={searchTerm} />

          <div className="flex items-center gap-4">
            <button
              onClick={() => setShowMobileFilters(!showMobileFilters)}
              className="lg:hidden flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
            >
              <Filter className="w-4 h-4" />
              Filters
            </button>
            <SortDropdown value={sortBy} onChange={setSortBy} />
          </div>
        </div>
      </div>

      {/* Active Filters */}
      {(filters.categories.length > 0 ||
        filters.brands.length > 0 ||
        filters.minPrice ||
        filters.maxPrice ||
        filters.minRating ||
        filters.inStock !== null) && (
        <div className="mb-6">
          <ActiveFilters
            filters={filters}
            onRemoveFilter={handleRemoveFilter}
            onClearAll={handleClearFilters}
          />
        </div>
      )}

      {/* Results Count */}
      {pagination && (
        <p className="text-sm text-gray-600 mb-4">
          Showing {products.length} of {pagination.total} products
        </p>
      )}

      {/* Main Content */}
      <div className="flex flex-col lg:flex-row gap-6">
        {/* Filters Sidebar */}
        <div className={`${showMobileFilters ? 'block' : 'hidden'} lg:block`}>
          <FilterSidebar
            filters={filters}
            onFilterChange={setFilters}
            onClearFilters={handleClearFilters}
          />
        </div>

        {/* Product Grid */}
        <div className="flex-1">
          <ProductGrid products={products} loading={loading} />
        </div>
      </div>
    </div>
  );
};

export default ProductListPage;
