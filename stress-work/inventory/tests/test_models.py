"""Unit tests for the value models: Product, SKU, Location and StockLevel."""

import unittest
from decimal import Decimal

from inventory import InsufficientStock, Location, Product, SKU, StockLevel, ValidationError


class ProductTests(unittest.TestCase):
    def test_product_strips_text_and_defaults(self):
        product = Product(product_id="  p-1  ", name="  Widget  ")
        self.assertEqual(product.product_id, "p-1")
        self.assertEqual(product.name, "Widget")
        self.assertEqual(product.category, "uncategorized")
        self.assertEqual(product.unit_price, Decimal("0.00"))
        self.assertTrue(product.is_free)

    def test_product_quantizes_price_to_cents(self):
        self.assertEqual(Product("p-1", "Widget", Decimal("3.456")).unit_price, Decimal("3.46"))
        self.assertEqual(Product("p-1", "Widget", "2.5").unit_price, Decimal("2.50"))
        self.assertFalse(Product("p-1", "Widget", "2.5").is_free)

    def test_product_rejects_blank_identifier(self):
        with self.assertRaises(ValidationError):
            Product(product_id="   ", name="Widget")

    def test_product_rejects_negative_price(self):
        with self.assertRaises(ValidationError):
            Product("p-1", "Widget", Decimal("-1"))

    def test_product_rejects_non_numeric_price(self):
        with self.assertRaises(ValidationError):
            Product("p-1", "Widget", object())

    def test_product_is_hashable(self):
        product = Product("p-1", "Widget", "9.99")
        self.assertEqual({product, Product("p-1", "Widget", "9.99")}, {product})


class SKUTests(unittest.TestCase):
    def setUp(self):
        self.product = Product("p-1", "Widget", "9.99")

    def test_sku_requires_a_product_instance(self):
        with self.assertRaises(ValidationError):
            SKU(code="s-1", product="p-1")

    def test_sku_defaults_and_barcode_flag(self):
        plain = SKU("s-1", self.product)
        self.assertEqual(plain.unit_of_measure, "each")
        self.assertEqual(plain.pack_size, 1)
        self.assertFalse(plain.is_scannable)

        tagged = SKU("s-2", self.product, barcode=" 0123456789 ")
        self.assertTrue(tagged.is_scannable)
        self.assertEqual(tagged.barcode, "0123456789")

    def test_sku_pack_size_must_be_at_least_one(self):
        for bad in (0, -3, "six", True):
            with self.subTest(pack_size=bad):
                with self.assertRaises(ValidationError):
                    SKU("s-1", self.product, pack_size=bad)


class LocationTests(unittest.TestCase):
    def test_location_defaults(self):
        location = Location("A-01", "Aisle 1 Bin 1")
        self.assertEqual(location.zone, "default")
        self.assertIsNone(location.capacity)
        self.assertFalse(location.is_bounded)

    def test_location_capacity_rejects_zero_and_negative(self):
        self.assertTrue(Location("A-01", "Bin", capacity=40).is_bounded)
        with self.assertRaises(ValidationError):
            Location("A-01", "Bin", capacity=0)
        with self.assertRaises(ValidationError):
            Location("A-01", "Bin", capacity=-5)


class StockLevelTests(unittest.TestCase):
    def setUp(self):
        self.sku = SKU("s-1", Product("p-1", "Widget", "9.99"))
        self.location = Location("A-01", "Aisle 1 Bin 1")

    def make(self, **kwargs):
        return StockLevel(sku=self.sku, location=self.location, **kwargs)

    def test_available_subtracts_reserved_units(self):
        record = self.make(quantity=10, reserved=4)
        self.assertEqual(record.available, 6)
        self.assertFalse(record.is_empty)

    def test_reserved_cannot_exceed_quantity(self):
        with self.assertRaises(ValidationError):
            self.make(quantity=2, reserved=3)

    def test_is_low_only_when_a_threshold_is_configured(self):
        self.assertFalse(self.make(quantity=0).is_low)
        self.assertFalse(self.make(quantity=0, reorder_point=0).is_low)
        self.assertTrue(self.make(quantity=5, reorder_point=5).is_low)
        self.assertTrue(self.make(quantity=6, reserved=2, reorder_point=5).is_low)
        self.assertFalse(self.make(quantity=6, reorder_point=5).is_low)

    def test_reserve_and_release_move_availability(self):
        record = self.make(quantity=10)
        record.reserve(3)
        self.assertEqual((record.quantity, record.reserved, record.available), (10, 3, 7))
        record.release(2)
        self.assertEqual((record.quantity, record.reserved, record.available), (10, 1, 9))

    def test_reserve_beyond_availability_raises(self):
        record = self.make(quantity=5, reserved=4)
        with self.assertRaises(InsufficientStock):
            record.reserve(2)

    def test_release_beyond_reserved_raises(self):
        record = self.make(quantity=5)
        with self.assertRaises(InsufficientStock):
            record.release(1)

    def test_movement_quantities_must_be_positive_integers(self):
        record = self.make(quantity=10)
        for bad in (0, -1, "2", True, 1.5):
            with self.subTest(units=bad):
                with self.assertRaises(ValidationError):
                    record.reserve(bad)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
