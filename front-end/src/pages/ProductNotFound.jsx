import { useNavigate } from 'react-router-dom';
import { Package } from 'lucide-react';
import Button from '../components/ui/Button';

const ProductNotFound = () => {
  const navigate = useNavigate();

  return (
    <div className="container mx-auto px-4 py-12">
      <div className="flex flex-col items-center justify-center text-center py-12">
        <Package className="w-20 h-20 text-gray-400 mb-6" />
        <h1 className="text-4xl font-bold text-gray-900 mb-3">Product Not Found</h1>
        <p className="text-lg text-gray-600 mb-3 max-w-md">
          We're sorry, but the product you're looking for doesn't exist or has been removed.
        </p>
        <p className="text-sm text-gray-500 mb-8 max-w-md">
          The product ID may be incorrect, or the product might no longer be available.
        </p>

        <div className="flex flex-col sm:flex-row gap-4">
          <Button
            variant="primary"
            onClick={() => navigate('/')}
            size="lg"
          >
            Back to Products
          </Button>
          <Button
            variant="outline"
            onClick={() => window.history.back()}
            size="lg"
          >
            Go Back
          </Button>
        </div>
      </div>
    </div>
  );
};

export default ProductNotFound;
