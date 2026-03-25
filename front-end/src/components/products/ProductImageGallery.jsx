import { useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

const ProductImageGallery = ({ product }) => {
  const [selectedImageIndex, setSelectedImageIndex] = useState(0);

  // Parse images from product data
  const images = product.images && Array.isArray(product.images)
    ? product.images
    : product.images && typeof product.images === 'string'
    ? JSON.parse(product.images)
    : [];

  const allImages = [product.primaryImage, ...images].filter(Boolean);
  const currentImage = allImages[selectedImageIndex] || product.primaryImage;

  const handlePrevious = () => {
    setSelectedImageIndex((prev) =>
      prev === 0 ? allImages.length - 1 : prev - 1
    );
  };

  const handleNext = () => {
    setSelectedImageIndex((prev) =>
      prev === allImages.length - 1 ? 0 : prev + 1
    );
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Main Image */}
      <div className="relative bg-gray-100 rounded-lg overflow-hidden aspect-square sm:aspect-[3/4] max-h-[600px] flex items-center justify-center group">
        <img
          src={currentImage}
          alt={product.name}
          className="w-full h-full object-cover"
          onError={(e) => {
            e.target.src = '/placeholder-image.png';
          }}
        />

        {/* Navigation Arrows */}
        {allImages.length > 1 && (
          <>
            <button
              onClick={handlePrevious}
              className="absolute left-4 top-1/2 -translate-y-1/2 bg-white bg-opacity-80 hover:bg-opacity-100 p-2 rounded-full shadow-lg transition-all opacity-0 group-hover:opacity-100"
              aria-label="Previous image"
            >
              <ChevronLeft className="w-6 h-6 text-gray-900" />
            </button>
            <button
              onClick={handleNext}
              className="absolute right-4 top-1/2 -translate-y-1/2 bg-white bg-opacity-80 hover:bg-opacity-100 p-2 rounded-full shadow-lg transition-all opacity-0 group-hover:opacity-100"
              aria-label="Next image"
            >
              <ChevronRight className="w-6 h-6 text-gray-900" />
            </button>

            {/* Image counter */}
            <div className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-black bg-opacity-60 text-white px-3 py-1 rounded-full text-sm font-medium opacity-0 group-hover:opacity-100 transition-opacity">
              {selectedImageIndex + 1} / {allImages.length}
            </div>
          </>
        )}
      </div>

      {/* Thumbnail Navigation */}
      {allImages.length > 1 && (
        <div className="flex flex-col lg:flex-row gap-4">
          {/* Desktop: Vertical thumbnails on right */}
          <div className="hidden lg:flex lg:flex-col gap-2 order-2 lg:order-1">
            {allImages.map((image, index) => (
              <button
                key={index}
                onClick={() => setSelectedImageIndex(index)}
                className={`w-16 h-20 rounded-lg overflow-hidden border-2 transition-all flex-shrink-0 ${
                  selectedImageIndex === index
                    ? 'border-primary-600'
                    : 'border-gray-200 hover:border-gray-300'
                }`}
                aria-label={`View image ${index + 1}`}
              >
                <img
                  src={image}
                  alt={`Thumbnail ${index + 1}`}
                  className="w-full h-full object-cover"
                  onError={(e) => {
                    e.target.src = '/placeholder-image.png';
                  }}
                />
              </button>
            ))}
          </div>

          {/* Mobile: Horizontal scroll thumbnails */}
          <div className="lg:hidden flex gap-2 overflow-x-auto pb-2 sm:pb-0">
            {allImages.map((image, index) => (
              <button
                key={index}
                onClick={() => setSelectedImageIndex(index)}
                className={`w-20 h-20 rounded-lg overflow-hidden border-2 transition-all flex-shrink-0 ${
                  selectedImageIndex === index
                    ? 'border-primary-600'
                    : 'border-gray-200 hover:border-gray-300'
                }`}
                aria-label={`View image ${index + 1}`}
              >
                <img
                  src={image}
                  alt={`Thumbnail ${index + 1}`}
                  className="w-full h-full object-cover"
                  onError={(e) => {
                    e.target.src = '/placeholder-image.png';
                  }}
                />
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default ProductImageGallery;
