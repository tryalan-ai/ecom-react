import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCart } from '../context/CartContext';
import CheckoutProgress from '../components/checkout/CheckoutProgress';
import ShippingForm from '../components/checkout/ShippingForm';
import PaymentForm from '../components/checkout/PaymentForm';
import OrderReview from '../components/checkout/OrderReview';
import CartSummary from '../components/cart/CartSummary';
import { createOrder } from '../utils/api';

const CheckoutPage = () => {
  const { cart, clearCart } = useCart();
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(1);
  const [loading, setLoading] = useState(false);

  const [checkoutData, setCheckoutData] = useState(() => {
    const saved = localStorage.getItem('checkoutData');
    return saved
      ? JSON.parse(saved)
      : {
          shipping: null,
          payment: null,
          sameAsBilling: true
        };
  });

  // Redirect to home if cart is empty
  useEffect(() => {
    if (cart.items.length === 0) {
      navigate('/');
    }
  }, [cart.items.length, navigate]);

  // Save checkout data to localStorage
  useEffect(() => {
    localStorage.setItem('checkoutData', JSON.stringify(checkoutData));
  }, [checkoutData]);

  const handleShippingSubmit = (shippingInfo, sameAsBilling) => {
    console.log('[Checkout] Shipping submitted:', { city: shippingInfo.city, state: shippingInfo.state, sameAsBilling });
    setCheckoutData({
      ...checkoutData,
      shipping: shippingInfo,
      sameAsBilling
    });
    setCurrentStep(2);
  };

  const handlePaymentSubmit = (paymentInfo) => {
    console.log('[Checkout] Payment submitted:', { method: 'card', last4: paymentInfo.cardNumber?.slice(-4) });
    setCheckoutData({
      ...checkoutData,
      payment: paymentInfo
    });
    setCurrentStep(3);
  };

  const handleOrderSubmit = async () => {
    console.log('[Checkout] Placing order:', { itemCount: cart.items.length, total: cart.totals.total });
    setLoading(true);

    try {
      // Prepare order data
      const orderData = {
        customer: {
          name: checkoutData.shipping.name,
          email: checkoutData.shipping.email,
          phone: checkoutData.shipping.phone
        },
        shippingAddress: {
          address: checkoutData.shipping.address,
          apartment: checkoutData.shipping.apartment,
          city: checkoutData.shipping.city,
          state: checkoutData.shipping.state,
          zipCode: checkoutData.shipping.zipCode,
          country: checkoutData.shipping.country
        },
        billingAddress: checkoutData.sameAsBilling
          ? {
              address: checkoutData.shipping.address,
              apartment: checkoutData.shipping.apartment,
              city: checkoutData.shipping.city,
              state: checkoutData.shipping.state,
              zipCode: checkoutData.shipping.zipCode,
              country: checkoutData.shipping.country
            }
          : {
              address: checkoutData.shipping.address,
              apartment: checkoutData.shipping.apartment,
              city: checkoutData.shipping.city,
              state: checkoutData.shipping.state,
              zipCode: checkoutData.shipping.zipCode,
              country: checkoutData.shipping.country
            },
        items: cart.items.map(item => ({
          productId: item.productId,
          productName: item.product.name,
          quantity: item.quantity,
          price: item.price
        })),
        totals: cart.totals,
        paymentMethod: 'card',
        promoCode: cart.promoCode
      };

      const response = await createOrder(orderData);

      // Navigate to confirmation page first, then clear cart
      // (clearing cart first triggers useEffect redirect to home)
      console.log('[Checkout] Order placed successfully:', { orderId: response.data.orderId });
      navigate(`/confirmation/${response.data.orderId}`);

      // Clear cart and checkout data after navigation
      setTimeout(() => {
        clearCart();
        localStorage.removeItem('checkoutData');
      }, 100);
    } catch (error) {
      console.error('Error creating order:', error);
      alert('Failed to place order. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleBack = (step) => {
    setCurrentStep(step);
  };

  return (
    <div className="min-h-screen bg-gray-50 py-8">
      <div className="container mx-auto px-4">
        <div className="max-w-4xl mx-auto">
          <h1 className="text-3xl font-bold mb-8 text-center">Checkout</h1>

          <CheckoutProgress currentStep={currentStep} />

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            {/* Form Section */}
            <div className="lg:col-span-2">
              <div className="card">
                {currentStep === 1 && (
                  <ShippingForm
                    initialData={checkoutData.shipping}
                    onSubmit={handleShippingSubmit}
                  />
                )}

                {currentStep === 2 && (
                  <PaymentForm
                    initialData={checkoutData.payment}
                    onSubmit={handlePaymentSubmit}
                    onBack={() => setCurrentStep(1)}
                  />
                )}

                {currentStep === 3 && (
                  <OrderReview
                    shippingInfo={checkoutData.shipping}
                    paymentInfo={checkoutData.payment}
                    onSubmit={handleOrderSubmit}
                    onBack={handleBack}
                    loading={loading}
                  />
                )}
              </div>
            </div>

            {/* Order Summary Sidebar */}
            <div className="lg:col-span-1">
              <div className="card sticky top-20">
                <h3 className="text-lg font-bold mb-4">Order Summary</h3>
                <div className="space-y-3 mb-4">
                  {cart.items.map((item) => (
                    <div key={item.productId} className="flex gap-3 text-sm">
                      <img
                        src={item.product.primaryImage}
                        alt={item.product.name}
                        className="w-12 h-12 object-cover rounded"
                      />
                      <div className="flex-1">
                        <p className="font-medium line-clamp-1">{item.product.name}</p>
                        <p className="text-gray-600">Qty: {item.quantity}</p>
                      </div>
                    </div>
                  ))}
                </div>
                <CartSummary totals={cart.totals} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CheckoutPage;
