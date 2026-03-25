import { Op } from 'sequelize';
import Product from '../models/Product.js';

export const getAllProducts = async (req, res, next) => {
  try {
    const {
      category,
      brand,
      minPrice,
      maxPrice,
      minRating,
      inStock,
      search,
      sortBy = 'featured',
      page = 1,
      limit = 20
    } = req.query;

    // Build filter conditions
    const where = {};

    if (category) {
      const categories = Array.isArray(category) ? category : [category];
      where.category = {
        [Op.in]: categories
      };
    }

    if (brand) {
      const brands = Array.isArray(brand) ? brand : [brand];
      where.brand = {
        [Op.in]: brands
      };
    }

    if (minPrice || maxPrice) {
      where.price = {};
      if (minPrice) where.price[Op.gte] = parseFloat(minPrice);
      if (maxPrice) where.price[Op.lte] = parseFloat(maxPrice);
    }

    if (minRating) {
      where.rating = {
        [Op.gte]: parseFloat(minRating)
      };
    }

    if (inStock === 'true' || inStock === true) {
      where.inStock = true;
    } else if (inStock === 'false' || inStock === false) {
      where.inStock = false;
    }

    if (search) {
      where[Op.or] = [
        { name: { [Op.like]: `%${search}%` } },
        { description: { [Op.like]: `%${search}%` } },
        { brand: { [Op.like]: `%${search}%` } },
        { category: { [Op.like]: `%${search}%` } }
      ];
    }

    // Build sort order
    let order = [];
    switch (sortBy) {
      case 'price_asc':
        order = [['price', 'ASC']];
        break;
      case 'price_desc':
        order = [['price', 'DESC']];
        break;
      case 'newest':
        order = [['createdAt', 'DESC']];
        break;
      case 'rating':
        order = [['rating', 'DESC']];
        break;
      case 'featured':
      default:
        order = [['featured', 'DESC'], ['rating', 'DESC']];
        break;
    }

    // Calculate pagination
    const offset = (parseInt(page) - 1) * parseInt(limit);

    console.log('[API] GET /products — filters:', JSON.stringify(where), 'sort:', sortBy);

    // Execute query
    const { count, rows } = await Product.findAndCountAll({
      where,
      order,
      limit: parseInt(limit),
      offset
    });

    console.log('[API] GET /products — returned:', count, 'products, page:', page);

    res.json({
      success: true,
      data: {
        products: rows,
        pagination: {
          total: count,
          page: parseInt(page),
          limit: parseInt(limit),
          pages: Math.ceil(count / parseInt(limit))
        }
      }
    });
  } catch (error) {
    next(error);
  }
};

export const getProductById = async (req, res, next) => {
  try {
    const { id } = req.params;
    const product = await Product.findByPk(id);

    if (!product) {
      const error = new Error('Product not found');
      error.statusCode = 404;
      return next(error);
    }

    res.json({
      success: true,
      data: product
    });
  } catch (error) {
    next(error);
  }
};

export const getCategories = async (req, res, next) => {
  try {
    const categories = await Product.findAll({
      attributes: ['category'],
      group: ['category'],
      raw: true
    });

    const categoryList = categories.map(c => c.category).filter(Boolean);

    res.json({
      success: true,
      data: categoryList
    });
  } catch (error) {
    next(error);
  }
};

export const getBrands = async (req, res, next) => {
  try {
    const brands = await Product.findAll({
      attributes: ['brand'],
      group: ['brand'],
      raw: true
    });

    const brandList = brands.map(b => b.brand).filter(Boolean);

    res.json({
      success: true,
      data: brandList
    });
  } catch (error) {
    next(error);
  }
};
