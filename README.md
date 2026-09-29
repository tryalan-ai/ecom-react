# E-commerce Product Catalog Platform

A modern, full-stack e-commerce web application built with React, Node.js, Express, and SQLite. Features advanced product filtering, shopping cart management, and a streamlined 3-step checkout process.

## 🚀 Features

### Product Catalog
- Grid view with responsive design (4 cols desktop, 2 tablet, 1 mobile)
- 100 products across multiple categories
- Product cards with images, ratings, prices, and sale badges
- Real-time search functionality
- Advanced filtering system:
  - Category filter (hierarchical, multi-select)
  - Price range filter (with presets and custom range)
  - Brand filter (multi-select)
  - Rating filter (minimum star rating)
  - Availability filter (in stock/out of stock)
- Multiple sorting options (Featured, Price, Newest, Top Rated)
- Active filter tags with individual remove buttons
- URL-based filter state (shareable filtered views)

### Shopping Cart
- Add/remove/update quantity
- Persistent cart (localStorage)
- Slide-out cart drawer
- Real-time total calculations
- Stock validation
- Promo code support (SAVE10 for 10% off)
- Cart badge with item count

### Checkout Flow
- 3-step checkout process (Shipping → Payment → Review)
- Form validation with inline error messages
- Progress indicator
- Order summary sidebar
- Checkout state persistence
- Responsive mobile-friendly forms

### Order Management
- Order confirmation page
- Order details with item summary
- Estimated delivery date
- Order tracking information

## 📁 Project Structure

```
ecom-react/
├── API/                          # Backend API
│   ├── src/
│   │   ├── config/               # Database configuration
│   │   ├── controllers/          # Business logic
│   │   ├── middleware/           # Express middleware
│   │   ├── models/               # Sequelize models
│   │   ├── routes/               # API routes
│   │   ├── seeders/              # Database seeders
│   │   └── server.js             # Entry point
│   ├── database/
│   │   └── ecommerce.db          # SQLite database
│   └── package.json
│
├── front-end/                    # React Frontend
│   ├── src/
│   │   ├── components/
│   │   │   ├── cart/             # Cart components
│   │   │   ├── checkout/         # Checkout forms
│   │   │   ├── layout/           # Layout components
│   │   │   ├── products/         # Product components
│   │   │   └── ui/               # Reusable UI components
│   │   ├── context/              # React Context (Cart)
│   │   ├── pages/                # Page components
│   │   ├── utils/                # Utility functions
│   │   ├── App.jsx               # Main app component
│   │   └── main.jsx              # Entry point
│   └── package.json
│
├── TECHNICAL_SPEC.md             # Technical documentation
└── README.md                     # This file
```

## 🛠️ Tech Stack

### Frontend
- **React 18** - UI framework
- **Vite 5** - Build tool and dev server
- **React Router v6** - Client-side routing
- **Tailwind CSS** - Utility-first CSS framework
- **Lucide React** - Icon library
- **Axios** - HTTP client

### Backend
- **Node.js** - Runtime environment
- **Express.js** - Web framework
- **SQLite3** - Database
- **Sequelize** - ORM
- **CORS** - Cross-origin resource sharing

## 📦 Installation & Setup

### Prerequisites
- Node.js 18+ installed
- npm or yarn package manager

### 1. Clone the Repository
```bash
git clone <repository-url>
cd ecom-react
```

### 2. Set Up the Backend API

```bash
cd API
npm ci
mkdir -p database
npm run seed    # Seed database with 100 products
npm start       # Start API server on port 3001
```

The API will be available at `http://localhost:3001`

### 3. Set Up the Frontend

Open a new terminal window:

```bash
cd front-end
npm ci
npm run dev     # Start development server on port 5173
```

The app will be available at `http://localhost:5173`

## 🎯 Usage

### Running the Application

1. **Start the Backend:**
   ```bash
   cd API
   npm start
   ```

2. **Start the Frontend (in a new terminal):**
   ```bash
   cd front-end
   npm run dev
   ```

3. **Access the Application:**
   - Open your browser and navigate to `http://localhost:5173`

### Test the Application

1. **Browse Products**
   - View 100 products in a responsive grid
   - Use filters to narrow down products
   - Search for specific items
   - Sort by different criteria

2. **Add to Cart**
   - Click "Add to Cart" on any product
   - View cart by clicking the cart icon
   - Adjust quantities or remove items

3. **Checkout**
   - Click "Proceed to Checkout" in the cart
   - Fill in shipping information
   - Enter payment details (test card: 4532 1234 5678 9010)
   - Review order and place

4. **Order Confirmation**
   - View order details and confirmation
   - See estimated delivery date

### Promo Codes
- `SAVE10` - 10% discount
- `SAVE20` - 20% discount

## 🔌 API Endpoints

### Products
- `GET /api/products` - Get all products (with filtering, sorting, pagination)
- `GET /api/products/:id` - Get single product

### Filters
- `GET /api/filters/categories` - Get all categories
- `GET /api/filters/brands` - Get all brands

### Orders
- `POST /api/orders` - Create new order
- `GET /api/orders/:orderId` - Get order details

### Health Check
- `GET /api/health` - API health status

## 📊 Database

The application uses SQLite with the following schema:

- **products** - Product catalog
- **orders** - Order records
- **order_items** - Order line items

The database is automatically created and seeded with 100 products when you run `npm run seed`.

## 🎨 Features Highlights

### Filtering System
- Multiple filters can be applied simultaneously (AND logic)
- Filters persist in URL for shareable links
- Real-time product count updates
- Easy filter removal with active filter tags

### Shopping Cart
- Persists across page refreshes (localStorage)
- Automatic stock validation
- Real-time price calculations including:
  - Subtotal
  - Shipping (FREE over $100)
  - Tax (8%)
  - Discounts (promo codes)
  - Grand total

### Checkout Flow
- Multi-step process with progress indicator
- Form validation with helpful error messages
- Ability to go back and edit previous steps
- Checkout state saves in localStorage
- Order summary visible throughout

### Responsive Design
- Mobile-first approach
- Breakpoints: 320px (mobile), 768px (tablet), 1024px (desktop)
- Collapsible filters on mobile
- Touch-friendly interactions

## 🐛 Troubleshooting

### Port Already in Use
If you get an error that the port is already in use:

**Backend (3001):**
```bash
lsof -ti:3001 | xargs kill -9
```

**Frontend (5173):**
```bash
lsof -ti:5173 | xargs kill -9
```

### Database Issues
To reset the database:
```bash
cd API
rm database/ecommerce.db
npm run seed
```

### Clear Cart/Checkout Data
Clear browser localStorage:
- Open browser DevTools (F12)
- Go to Application → Local Storage
- Clear `cart` and `checkoutData` keys

## 📝 Development

### Build for Production

**Frontend:**
```bash
cd front-end
npm run build
```

The production build will be in `front-end/dist/`

### Environment Variables

The application uses hardcoded URLs for development:
- API: `http://localhost:3001`
- Frontend: `http://localhost:5173`

For production, update `API_BASE_URL` in `front-end/src/utils/api.js`

## 🎓 Learning Resources

This project demonstrates:
- React Hooks (useState, useEffect, useContext, useReducer)
- React Router for SPA navigation
- Context API for global state management
- Form handling and validation
- REST API integration
- Responsive design with Tailwind CSS
- SQLite database with Sequelize ORM
- Express.js API development

## 📄 License

This is a demo project for testing purposes.

## 👥 Author

Built as a functional e-commerce testing platform.

---

**Happy Shopping! 🛍️**
