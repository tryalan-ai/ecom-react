import sequelize from './src/config/database.js';
import './src/models/Product.js';

async function seedProducts() {
  try {
    await sequelize.authenticate();
    console.log('✓ Database connected');

    const Product = sequelize.models.Product;

    const products = [
      {
        name: 'Premium Wireless Headphones',
        description: 'High-quality wireless headphones with active noise cancellation, 30-hour battery life, and premium comfort padding.',
        price: 199.99,
        originalPrice: 249.99,
        currency: 'USD',
        primaryImage: 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500',
        images: JSON.stringify([
          'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=500',
          'https://images.unsplash.com/photo-1484704849700-f032a568e944?w=500',
          'https://images.unsplash.com/photo-1487215078519-e21cc028cb29?w=500'
        ]),
        category: 'Electronics',
        brand: 'AudioTech',
        rating: 4.7,
        reviewCount: 342,
        inStock: true,
        stockCount: 25,
        attributes: JSON.stringify({
          color: ['Black', 'Silver', 'Rose Gold'],
          connectivity: ['Bluetooth 5.0', 'Wired 3.5mm']
        }),
        featured: true
      },
      {
        name: 'Classic Analog Watch',
        description: 'Elegant analog watch with leather strap, water resistant, perfect for any occasion.',
        price: 89.99,
        originalPrice: 129.99,
        currency: 'USD',
        primaryImage: 'https://images.unsplash.com/photo-1523170335684-f1b5be63fb94?w=500',
        images: JSON.stringify([
          'https://images.unsplash.com/photo-1523170335684-f1b5be63fb94?w=500',
          'https://images.unsplash.com/photo-1569495253454-9fde8c8a3979?w=500'
        ]),
        category: 'Accessories',
        brand: 'TimeKeeper',
        rating: 4.4,
        reviewCount: 156,
        inStock: true,
        stockCount: 40,
        attributes: JSON.stringify({
          color: ['Black', 'Brown', 'Navy'],
          size: ['Small', 'Medium', 'Large']
        }),
        featured: true
      },
      {
        name: '4K Ultra HD Camera',
        description: 'Professional-grade 4K camera with advanced autofocus and stabilization technology.',
        price: 899.99,
        originalPrice: 1099.99,
        currency: 'USD',
        primaryImage: 'https://images.unsplash.com/photo-1606986628025-35d57e735ae0?w=500',
        images: JSON.stringify([
          'https://images.unsplash.com/photo-1606986628025-35d57e735ae0?w=500',
          'https://images.unsplash.com/photo-1510690655402-2ee9a854cf00?w=500'
        ]),
        category: 'Electronics',
        brand: 'ProVision',
        rating: 4.8,
        reviewCount: 89,
        inStock: true,
        stockCount: 8,
        attributes: JSON.stringify({
          resolution: ['4K 30fps', '4K 60fps'],
          storage: ['64GB', '128GB', '256GB']
        }),
        featured: true
      },
      {
        name: 'Organic Cotton T-Shirt',
        description: 'Comfortable, eco-friendly t-shirt made from 100% organic cotton.',
        price: 34.99,
        originalPrice: 44.99,
        currency: 'USD',
        primaryImage: 'https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=500',
        images: JSON.stringify([
          'https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=500',
          'https://images.unsplash.com/photo-1583394838336-acd977736f90?w=500'
        ]),
        category: 'Clothing',
        brand: 'EcoWear',
        rating: 4.3,
        reviewCount: 267,
        inStock: true,
        stockCount: 100,
        attributes: JSON.stringify({
          color: ['White', 'Black', 'Navy', 'Green'],
          size: ['XS', 'S', 'M', 'L', 'XL', 'XXL']
        }),
        featured: false
      },
      {
        name: 'Portable Bluetooth Speaker',
        description: 'Waterproof portable speaker with 360-degree sound and 12-hour battery life.',
        price: 79.99,
        originalPrice: 99.99,
        currency: 'USD',
        primaryImage: 'https://images.unsplash.com/photo-1589003077984-894e133814c9?w=500',
        images: JSON.stringify([
          'https://images.unsplash.com/photo-1589003077984-894e133814c9?w=500',
          'https://images.unsplash.com/photo-1608043152269-423dbba4e7e1?w=500'
        ]),
        category: 'Electronics',
        brand: 'SoundPro',
        rating: 4.6,
        reviewCount: 512,
        inStock: true,
        stockCount: 50,
        attributes: JSON.stringify({
          color: ['Black', 'Blue', 'Red', 'White']
        }),
        featured: false
      }
    ];

    for (const product of products) {
      await Product.create(product);
      console.log(`✓ Created: ${product.name}`);
    }

    console.log(`\n✓ Seeded ${products.length} products`);
    process.exit(0);
  } catch (error) {
    console.error('Error seeding products:', error);
    process.exit(1);
  }
}

seedProducts();
