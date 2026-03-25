import Order from '../models/Order.js';
import OrderItem from '../models/OrderItem.js';
import Product from '../models/Product.js';

// Generate unique order ID
const generateOrderId = () => {
  const timestamp = Date.now().toString(36);
  const random = Math.random().toString(36).substring(2, 7);
  return `ORD-${timestamp}${random}`.toUpperCase();
};

export const createOrder = async (req, res, next) => {
  try {
    const {
      customer,
      shippingAddress,
      billingAddress,
      items,
      totals,
      paymentMethod,
      promoCode
    } = req.body;

    // Validate required fields
    if (!customer || !shippingAddress || !items || items.length === 0) {
      const error = new Error('Missing required order information');
      error.statusCode = 400;
      return next(error);
    }

    // Validate stock for all items
    for (const item of items) {
      const product = await Product.findByPk(item.productId);
      if (!product) {
        const error = new Error(`Product ${item.productId} not found`);
        error.statusCode = 404;
        return next(error);
      }
      if (!product.inStock || product.stockCount < item.quantity) {
        const error = new Error(`Product ${product.name} is out of stock`);
        error.statusCode = 400;
        return next(error);
      }
    }

    console.log('[API] POST /orders — customer:', customer.name, 'items:', items.length, 'total:', totals.total);

    // Generate order ID
    const orderId = generateOrderId();

    // Create order
    const order = await Order.create({
      orderId,
      customerName: customer.name,
      customerEmail: customer.email,
      customerPhone: customer.phone,
      shippingAddress,
      billingAddress: billingAddress || shippingAddress,
      subtotal: totals.subtotal,
      tax: totals.tax,
      shipping: totals.shipping,
      discount: totals.discount || 0,
      total: totals.total,
      promoCode: promoCode || null,
      paymentMethod,
      status: 'confirmed'
    });

    // Create order items
    const orderItems = await Promise.all(
      items.map(item =>
        OrderItem.create({
          orderId: order.id,
          productId: item.productId,
          productName: item.productName,
          quantity: item.quantity,
          price: item.price
        })
      )
    );

    // Update product stock
    for (const item of items) {
      await Product.decrement('stockCount', {
        by: item.quantity,
        where: { id: item.productId }
      });
    }

    // Fetch complete order with items
    const completeOrder = await Order.findOne({
      where: { id: order.id },
      include: [
        {
          model: OrderItem,
          as: 'items',
          include: [Product]
        }
      ]
    });

    console.log('[API] Order created:', { orderId, itemCount: orderItems.length, total: totals.total });

    res.status(201).json({
      success: true,
      data: completeOrder
    });
  } catch (error) {
    next(error);
  }
};

export const getOrderById = async (req, res, next) => {
  try {
    const { orderId } = req.params;

    const order = await Order.findOne({
      where: { orderId },
      include: [
        {
          model: OrderItem,
          as: 'items',
          include: [Product]
        }
      ]
    });

    if (!order) {
      const error = new Error('Order not found');
      error.statusCode = 404;
      return next(error);
    }

    res.json({
      success: true,
      data: order
    });
  } catch (error) {
    next(error);
  }
};
