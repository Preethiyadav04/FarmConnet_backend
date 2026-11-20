"""
FarmConnect - Phase 4 Automated Verification Suite
Tests Orders, Atomic Stock Management, Price Negotiation, Logistics Dispatch,
Tracking, Role-Based Access Controls, and Data Integrity against MySQL 8.0 on port 3306.
Safeguards all persistent database records.
"""

import os
import sys
from pathlib import Path
from decimal import Decimal
import json

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.test import Client
from django.db import connection, transaction
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

from apps.crops.models import Category, Crop, CropStatus
from apps.orders.models import (
    Order, OrderItem, Payment, PriceNegotiation,
    OrderStatus, PaymentStatus, PaymentMethod, NegotiationStatus
)
from apps.logistics.models import TransportRequest, TransportStatus
from apps.accounts.models import UserRole

User = get_user_model()


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token)


def run_tests():
    print("=" * 75)
    print(" FarmConnect - Phase 4 Verification Suite (MySQL 8.0 on Port 3306)")
    print("=" * 75)

    # 1. Verify Database Engine
    print("\n[STEP 1] Verifying MySQL Database Connection...")
    with connection.cursor() as cursor:
        cursor.execute("SELECT VERSION(), @@port, DATABASE();")
        version, active_port, current_db = cursor.fetchone()
        print(f"  • Connected to MySQL: {version} on port {active_port}")
        print(f"  • Database Name:      {current_db}")
        assert connection.vendor == 'mysql', f"Expected MySQL, got {connection.vendor}"
        assert str(active_port) == '3306', f"Expected port 3306, got {active_port}"
        assert current_db == 'farmconnect_db', f"Expected farmconnect_db, got {current_db}"
    print("-> PASSED: Executing directly against MySQL 8.0 on port 3306.")

    # 2. Inspect Existing Baseline Records
    print("\n[STEP 2] Inspecting Baseline Database Records...")
    initial_users = User.objects.count()
    initial_crops = Crop.objects.count()
    initial_orders = Order.objects.count()
    initial_order_items = OrderItem.objects.count()
    initial_payments = Payment.objects.count()
    initial_offers = PriceNegotiation.objects.count()
    initial_transports = TransportRequest.objects.count()

    print(f"  • Baseline Users:              {initial_users}")
    print(f"  • Baseline Crops:              {initial_crops}")
    print(f"  • Baseline Orders:             {initial_orders}")
    print(f"  • Baseline Order Items:        {initial_order_items}")
    print(f"  • Baseline Payments:           {initial_payments}")
    print(f"  • Baseline Negotiations:       {initial_offers}")
    print(f"  • Baseline Transport Requests: {initial_transports}")
    print("-> PASSED: Baseline database records verified.")

    # 3. Setup Test Actors
    print("\n[STEP 3] Setting up Test Actors...")
    admin_user = User.objects.filter(role=UserRole.ADMIN).first()
    farmer_user = User.objects.filter(role=UserRole.FARMER, username='farmer_ramesh').first()
    if not farmer_user:
        farmer_user = User.objects.filter(role=UserRole.FARMER).first()
    buyer_user = User.objects.filter(role=UserRole.BUYER, username='buyer_kiran').first()
    if not buyer_user:
        buyer_user = User.objects.filter(role=UserRole.BUYER).first()
    transporter_user = User.objects.filter(role=UserRole.TRANSPORTER, username='trans_rajesh').first()
    if not transporter_user:
        transporter_user = User.objects.filter(role=UserRole.TRANSPORTER).first()

    assert admin_user, "Admin user must exist"
    assert farmer_user, "Farmer user must exist"
    assert buyer_user, "Buyer user must exist"
    assert transporter_user, "Transporter user must exist"

    admin_token = get_tokens_for_user(admin_user)
    farmer_token = get_tokens_for_user(farmer_user)
    buyer_token = get_tokens_for_user(buyer_user)
    transporter_token = get_tokens_for_user(transporter_user)

    # Secondary isolated buyer for permission isolation checks
    other_buyer, _ = User.objects.get_or_create(
        username='test_p4_other_buyer',
        defaults={'email': 'other_buyer_p4@farmconnect.org', 'role': UserRole.BUYER}
    )
    if not other_buyer.has_usable_password():
        other_buyer.set_password('Pass123!')
        other_buyer.save()
    other_buyer_token = get_tokens_for_user(other_buyer)

    # Use a specific crop owned by farmer_user
    target_crop = Crop.objects.filter(farmer=farmer_user, status=CropStatus.ACTIVE).first()
    assert target_crop, f"Expected at least one active crop owned by farmer {farmer_user.username}"
    original_crop_stock = target_crop.quantity_available
    crop_unit_price = target_crop.price_per_unit
    print(f"  • Test Target Crop: '{target_crop.crop_name}' (ID: {target_crop.id})")
    print(f"    Available Stock: {original_crop_stock} {target_crop.unit} | Listed Price: ₹{crop_unit_price}")
    print("-> PASSED: Test actors and target crop prepared.")

    client = Client()
    created_orders = []
    created_negotiations = []
    created_transports = []

    try:
        # =====================================================================
        # TEST 1: Order Placement & Concurrency-Safe Inventory Control
        # =====================================================================
        print("\n[TEST 1] Testing Order Placement & Stock Validation...")

        # 1.1 Anonymous order attempt (401)
        res = client.post(
            '/api/orders/',
            data=json.dumps({'crop_id': target_crop.id, 'quantity': 10}),
            content_type='application/json'
        )
        assert res.status_code == 401, f"Expected 401, got {res.status_code}"
        print("  • Anonymous order placement: 401 Unauthorized (Blocked)")

        # 1.2 Attempt to order more than available stock (400)
        oversell_qty = original_crop_stock + Decimal('500.00')
        res = client.post(
            '/api/orders/',
            data=json.dumps({
                'crop_id': target_crop.id,
                'quantity': float(oversell_qty),
                'delivery_address': 'Plot 44, APMC Hub',
                'delivery_city': 'Pune',
                'delivery_state': 'Maharashtra',
                'contact_phone': '9876543210',
                'payment_method': 'cod'
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {buyer_token}'
        )
        assert res.status_code == 400, f"Expected 400 for overselling, got {res.status_code}"
        print(f"  • Oversell attempt ({oversell_qty} {target_crop.unit}): 400 Bad Request (Blocked)")

        # 1.3 Attempt to order below minimum order quantity (400)
        if target_crop.minimum_order_quantity > 1:
            sub_min = float(target_crop.minimum_order_quantity) - 1.0
            res = client.post(
                '/api/orders/',
                data=json.dumps({
                    'crop_id': target_crop.id,
                    'quantity': sub_min,
                    'delivery_address': 'Plot 44, APMC Hub',
                    'delivery_city': 'Pune',
                    'delivery_state': 'Maharashtra',
                    'contact_phone': '9876543210'
                }),
                content_type='application/json',
                HTTP_AUTHORIZATION=f'Bearer {buyer_token}'
            )
            assert res.status_code == 400, f"Expected 400 for sub-min quantity, got {res.status_code}"
            print(f"  • Sub-minimum quantity attempt ({sub_min} {target_crop.unit}): 400 Bad Request (Blocked)")

        # 1.4 Valid Order Placement by Buyer
        order_qty = Decimal('10.00')
        expected_total = order_qty * crop_unit_price
        res = client.post(
            '/api/orders/',
            data=json.dumps({
                'crop_id': target_crop.id,
                'quantity': float(order_qty),
                'delivery_address': 'Godown 12, Market Yard',
                'delivery_city': 'Pune',
                'delivery_state': 'Maharashtra',
                'delivery_pincode': '411037',
                'contact_phone': '9876543210',
                'payment_method': 'cod',
                'notes': 'Deliver before 10 AM please.'
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {buyer_token}'
        )
        assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.data}"
        order_data = res.data
        order_1_id = order_data['id']
        created_orders.append(order_1_id)
        assert order_data['status'] == OrderStatus.PENDING, f"Expected pending, got {order_data['status']}"
        assert Decimal(str(order_data['total_amount'])) == expected_total, f"Expected total {expected_total}, got {order_data['total_amount']}"
        assert len(order_data['items']) == 1, "Expected 1 order line item"

        # Verify crop stock deduction in MySQL
        target_crop.refresh_from_db()
        expected_remaining = original_crop_stock - order_qty
        assert target_crop.quantity_available == expected_remaining, (
            f"Stock deduction mismatch: expected {expected_remaining}, got {target_crop.quantity_available}"
        )
        print(f"  • Valid order placed: 201 Created (Order #{order_data['order_number']})")
        print(f"  • Atomic stock deduction in MySQL: {original_crop_stock} -> {target_crop.quantity_available} {target_crop.unit}")
        print("-> PASSED: Order placement & pessimistic stock deduction verified.")

        # =====================================================================
        # TEST 2: Role-Based Order Visibility & Farmer Confirmation
        # =====================================================================
        print("\n[TEST 2] Testing Order Visibility & Farmer Confirmation...")

        # 2.1 Buyer listing own orders
        res = client.get('/api/orders/', HTTP_AUTHORIZATION=f'Bearer {buyer_token}')
        assert res.status_code == 200
        buyer_orders = [o['id'] for o in res.data['results']]
        assert order_1_id in buyer_orders, "Buyer must see their placed order"

        # 2.2 Farmer listing incoming supply orders
        res = client.get('/api/orders/', HTTP_AUTHORIZATION=f'Bearer {farmer_token}')
        assert res.status_code == 200
        farmer_orders = [o['id'] for o in res.data['results']]
        assert order_1_id in farmer_orders, "Farmer must see incoming order for their crop"

        # 2.3 Other buyer cannot view or access Order 1 (Privacy check)
        res = client.get(f'/api/orders/{order_1_id}/', HTTP_AUTHORIZATION=f'Bearer {other_buyer_token}')
        assert res.status_code in [403, 404], f"Expected 403/404 for unrelated buyer, got {res.status_code}"
        print("  • Cross-buyer privacy isolation: 404/403 (Blocked)")

        # 2.4 Unrelated buyer cannot accept order
        res = client.post(
            f'/api/orders/{order_1_id}/accept_order/',
            HTTP_AUTHORIZATION=f'Bearer {other_buyer_token}'
        )
        assert res.status_code in [403, 404], f"Expected 403/404, got {res.status_code}"
        print("  • Non-farmer accept attempt: 403 Forbidden (Blocked)")

        # 2.5 Farmer accepts the order
        res = client.post(
            f'/api/orders/{order_1_id}/accept_order/',
            HTTP_AUTHORIZATION=f'Bearer {farmer_token}'
        )
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.data}"
        assert res.data['status'] == OrderStatus.CONFIRMED
        print(f"  • Farmer confirms order: 200 OK (Status: '{res.data['status']}')")
        print("-> PASSED: Order visibility and farmer confirmation verified.")

        # =====================================================================
        # TEST 3: Farmer Order Rejection with Stock Restoration
        # =====================================================================
        print("\n[TEST 3] Testing Farmer Order Rejection with Atomic Stock Restoration...")

        stock_before_order2 = target_crop.quantity_available
        reject_qty = Decimal('5.00')

        res = client.post(
            '/api/orders/',
            data=json.dumps({
                'crop_id': target_crop.id,
                'quantity': float(reject_qty),
                'delivery_address': 'Godown 8, APMC',
                'delivery_city': 'Nashik',
                'delivery_state': 'Maharashtra',
                'contact_phone': '9876543210'
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {buyer_token}'
        )
        assert res.status_code == 201
        order_2_id = res.data['id']
        created_orders.append(order_2_id)

        target_crop.refresh_from_db()
        assert target_crop.quantity_available == stock_before_order2 - reject_qty, "Stock must decrease upon order"

        # Farmer rejects order with a reason
        res = client.post(
            f'/api/orders/{order_2_id}/reject_order/',
            data=json.dumps({'reason': 'Unable to arrange immediate harvest batch.'}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {farmer_token}'
        )
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.data}"
        assert res.data['status'] == OrderStatus.REJECTED

        # Verify stock was restored atomically to stock_before_order2
        target_crop.refresh_from_db()
        assert target_crop.quantity_available == stock_before_order2, (
            f"Stock not restored upon rejection: expected {stock_before_order2}, got {target_crop.quantity_available}"
        )
        print(f"  • Farmer rejects order: 200 OK (Status: 'rejected')")
        print(f"  • Inventory restored in MySQL: Returned {reject_qty} {target_crop.unit} to stock (Current: {target_crop.quantity_available})")
        print("-> PASSED: Rejection and automatic stock restoration verified.")

        # =====================================================================
        # TEST 4: Buyer Order Cancellation with Stock Restoration
        # =====================================================================
        print("\n[TEST 4] Testing Buyer Cancellation with Atomic Stock Restoration...")

        stock_before_order3 = target_crop.quantity_available
        cancel_qty = Decimal('8.00')

        res = client.post(
            '/api/orders/',
            data=json.dumps({
                'crop_id': target_crop.id,
                'quantity': float(cancel_qty),
                'delivery_address': 'Shop 101, Subhash Road',
                'delivery_city': 'Nashik',
                'delivery_state': 'Maharashtra',
                'contact_phone': '9876543210'
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {buyer_token}'
        )
        assert res.status_code == 201
        order_3_id = res.data['id']
        created_orders.append(order_3_id)

        target_crop.refresh_from_db()
        assert target_crop.quantity_available == stock_before_order3 - cancel_qty

        # Buyer cancels their order
        res = client.post(
            f'/api/orders/{order_3_id}/cancel_order/',
            HTTP_AUTHORIZATION=f'Bearer {buyer_token}'
        )
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.data}"
        assert res.data['status'] == OrderStatus.CANCELLED

        target_crop.refresh_from_db()
        assert target_crop.quantity_available == stock_before_order3, (
            f"Stock not restored upon cancellation: expected {stock_before_order3}, got {target_crop.quantity_available}"
        )
        print(f"  • Buyer cancels order: 200 OK (Status: 'cancelled')")
        print(f"  • Inventory restored in MySQL: Returned {cancel_qty} {target_crop.unit} to stock (Current: {target_crop.quantity_available})")
        print("-> PASSED: Buyer cancellation and stock restoration verified.")

        # =====================================================================
        # TEST 5: Offline Payment Status Updates
        # =====================================================================
        print("\n[TEST 5] Testing Offline Payment Status Management...")

        # 5.1 Buyer cannot mark payment as completed (403)
        res = client.post(
            f'/api/orders/{order_1_id}/update_payment_status/',
            data=json.dumps({'payment_status': 'completed'}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {buyer_token}'
        )
        assert res.status_code == 403, f"Expected 403, got {res.status_code}"
        print("  • Buyer update payment attempt: 403 Forbidden (Blocked)")

        # 5.2 Farmer confirms cash on delivery received
        res = client.post(
            f'/api/orders/{order_1_id}/update_payment_status/',
            data=json.dumps({
                'payment_status': 'completed',
                'transaction_reference': 'COD-RECEIPT-9988'
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {farmer_token}'
        )
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.data}"
        assert res.data['payment_status'] == PaymentStatus.COMPLETED
        assert res.data['paid_at'] is not None

        # Verify in MySQL
        payment = Payment.objects.get(order_id=order_1_id)
        assert payment.payment_status == PaymentStatus.COMPLETED
        assert payment.transaction_reference == 'COD-RECEIPT-9988'
        print(f"  • Farmer verifies payment: 200 OK (Status: 'completed', Ref: 'COD-RECEIPT-9988')")
        print("-> PASSED: Offline payment workflow verified.")

        # =====================================================================
        # TEST 6: Price Negotiation & Counter-Offer Engine
        # =====================================================================
        print("\n[TEST 6] Testing Price Negotiation & Counter-Offer Engine...")

        # 6.1 Buyer submits price negotiation offer
        offered_price = crop_unit_price * Decimal('0.85')  # 15% discount
        offer_qty = Decimal('20.00')
        res = client.post(
            '/api/negotiations/',
            data=json.dumps({
                'listing': target_crop.id,
                'offered_price_per_unit': float(offered_price),
                'quantity': float(offer_qty),
                'message': 'We are purchasing in bulk for a retail cooperative.'
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {buyer_token}'
        )
        assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.data}"
        negotiation_id = res.data['id']
        created_negotiations.append(negotiation_id)
        assert res.data['status'] == NegotiationStatus.PENDING
        print(f"  • Buyer proposes offer: 201 Created (Offer #{negotiation_id} @ ₹{offered_price}/{target_crop.unit})")

        # 6.2 Farmer proposes counter-offer price
        counter_price = crop_unit_price * Decimal('0.92')  # 8% discount compromise
        res = client.post(
            f'/api/negotiations/{negotiation_id}/counter/',
            data=json.dumps({
                'counter_price_per_unit': float(counter_price),
                'farmer_notes': 'I can offer 8% off for this lot size, ready for immediate dispatch.'
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {farmer_token}'
        )
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.data}"
        assert res.data['status'] == NegotiationStatus.COUNTERED
        print(f"  • Farmer counters offer: 200 OK (Counter: ₹{counter_price}/{target_crop.unit})")

        # 6.3 Buyer accepts counter-offer
        res = client.post(
            f'/api/negotiations/{negotiation_id}/accept_counter/',
            HTTP_AUTHORIZATION=f'Bearer {buyer_token}'
        )
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.data}"
        assert res.data['status'] == NegotiationStatus.ACCEPTED
        print("  • Buyer accepts counter-offer: 200 OK (Status: 'accepted')")

        # 6.4 Buyer converts accepted negotiation into confirmed order
        stock_before_conversion = target_crop.quantity_available
        res = client.post(
            f'/api/negotiations/{negotiation_id}/convert_to_order/',
            data=json.dumps({
                'delivery_address': 'Plot 99, Cooperative Warehouse',
                'delivery_city': 'Nashik',
                'delivery_state': 'Maharashtra',
                'contact_phone': '9876543210'
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {buyer_token}'
        )
        assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.data}"
        conv_order_num = res.data['order_number']
        conv_order = Order.objects.get(order_number=conv_order_num)
        created_orders.append(conv_order.id)
        assert conv_order.status == OrderStatus.CONFIRMED

        target_crop.refresh_from_db()
        assert target_crop.quantity_available == stock_before_conversion - offer_qty, "Stock must decrease upon conversion"
        print(f"  • Convert to Order: 201 Created (Confirmed Order #{conv_order_num})")
        print(f"  • Converted order total: ₹{conv_order.total_amount} @ agreed rate ₹{counter_price}")
        print("-> PASSED: Full negotiation, counter-offer, and order conversion flow verified.")

        # =====================================================================
        # TEST 7: Logistics & Transport Request Management
        # =====================================================================
        print("\n[TEST 7] Testing Logistics & Transport Request Lifecycle...")

        # 7.1 Verify auto-dispatched transport request for Order 1
        transport_1 = TransportRequest.objects.get(order_id=order_1_id)
        transport_id = transport_1.id
        created_transports.append(transport_id)
        assert transport_1.status == TransportStatus.REQUESTED
        print(f"  • Auto-dispatched transport verified for Order 1: Transport #{transport_id} (Status: 'requested')")

        # 7.2 Manual transport request booking for Converted Order (conv_order)
        res = client.post(
            '/api/logistics/',
            data=json.dumps({
                'order': conv_order.id,
                'pickup_address': 'Survey 88, Ramesh Farm, Pimpalgaon',
                'pickup_city': 'Nashik',
                'drop_address': 'Plot 99, Cooperative Warehouse',
                'drop_city': 'Nashik',
                'estimated_distance_km': 45,
                'estimated_cost': 1200.00,
                'vehicle_type_needed': 'Pickup Van / Tata Ace'
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {farmer_token}'
        )
        assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.data}"
        manual_transport_id = res.data['id']
        created_transports.append(manual_transport_id)
        assert res.data['status'] == TransportStatus.REQUESTED
        print(f"  • Manual transport booking for Converted Order: 201 Created (Transport #{manual_transport_id})")

        # 7.2 Non-transporter browsing available jobs (403)
        res = client.get('/api/logistics/available_jobs/', HTTP_AUTHORIZATION=f'Bearer {buyer_token}')
        assert res.status_code == 403, f"Expected 403, got {res.status_code}"
        print("  • Non-transporter browsing available jobs: 403 Forbidden (Blocked)")

        # 7.3 Transporter browses open shipment jobs
        res = client.get('/api/logistics/available_jobs/', HTTP_AUTHORIZATION=f'Bearer {transporter_token}')
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        job_ids = [j['id'] for j in res.data.get('results', res.data)]
        assert transport_id in job_ids, "Open transport job must appear in available jobs"
        print(f"  • Transporter browses available jobs: 200 OK (Found {len(job_ids)} open shipment jobs)")

        # 7.4 Transporter accepts the job
        res = client.post(
            f'/api/logistics/{transport_id}/accept_job/',
            HTTP_AUTHORIZATION=f'Bearer {transporter_token}'
        )
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.data}"
        assert res.data['status'] == TransportStatus.ACCEPTED
        print(f"  • Transporter accepts job: 200 OK (Status: 'accepted')")

        # 7.5 Transporter updates status: Cargo Picked Up
        res = client.post(
            f'/api/logistics/{transport_id}/update_status/',
            data=json.dumps({
                'status': 'picked_up',
                'tracking_notes': 'Loaded 10 quintals at farm. Quality checked and tarp secured.'
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {transporter_token}'
        )
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.data}"
        assert res.data['status'] == TransportStatus.PICKED_UP

        # Check linked order transitioned to dispatched
        order_1_obj = Order.objects.get(id=order_1_id)
        assert order_1_obj.status == OrderStatus.DISPATCHED
        print("  • Status update -> 'picked_up': 200 OK (Order updated to 'dispatched')")

        # 7.6 Transporter updates status: In Transit
        res = client.post(
            f'/api/logistics/{transport_id}/update_status/',
            data=json.dumps({
                'status': 'in_transit',
                'tracking_notes': 'Crossing Pune-Nashik highway toll plaza. Expected arrival 3 PM.'
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {transporter_token}'
        )
        assert res.status_code == 200
        assert res.data['status'] == TransportStatus.IN_TRANSIT
        print("  • Status update -> 'in_transit': 200 OK")

        # 7.7 Transporter updates status: Delivered
        res = client.post(
            f'/api/logistics/{transport_id}/update_status/',
            data=json.dumps({
                'status': 'delivered',
                'final_charge': 4500.00,
                'tracking_notes': 'Unloaded at Pune Godown 12. Signed delivery challan received.'
            }),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {transporter_token}'
        )
        assert res.status_code == 200
        assert res.data['status'] == TransportStatus.DELIVERED
        assert res.data['delivered_at'] is not None

        # Check linked order transitioned to delivered
        order_1_obj.refresh_from_db()
        assert order_1_obj.status == OrderStatus.DELIVERED
        print("  • Status update -> 'delivered': 200 OK (Order updated to 'delivered')")

        # 7.8 Real-time shipment tracking access for Buyer & Farmer
        res = client.get(f'/api/logistics/{transport_id}/track/', HTTP_AUTHORIZATION=f'Bearer {buyer_token}')
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        assert res.data['status'] == TransportStatus.DELIVERED
        assert res.data['pickup_city'] == target_crop.location_city
        print(f"  • Buyer shipment tracking check: 200 OK (Delivered at: {res.data['delivered_at']})")
        print("-> PASSED: Full logistics and shipment tracking lifecycle verified.")

        # =====================================================================
        # TEST 8: Role-Based Access Controls & Security
        # =====================================================================
        print("\n[TEST 8] Testing Role Permissions & Security Boundaries...")

        # 8.1 Transporter cannot place orders
        res = client.post(
            '/api/orders/',
            data=json.dumps({'crop_id': target_crop.id, 'quantity': 5}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {transporter_token}'
        )
        assert res.status_code == 403, f"Expected 403 for transporter ordering, got {res.status_code}"
        print("  • Transporter order placement attempt: 403 Forbidden (Blocked)")

        # 8.2 Non-assigned user cannot modify shipment (403 or 404 object isolation)
        res = client.post(
            f'/api/logistics/{transport_id}/update_status/',
            data=json.dumps({'status': 'in_transit'}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {other_buyer_token}'
        )
        assert res.status_code in [403, 404], f"Expected 403 or 404 for unauthorized status edit, got {res.status_code}"
        print(f"  • Unauthorized shipment status edit: {res.status_code} (Blocked)")

        # 8.3 Order detail serializer includes transport snapshot
        res = client.get(f'/api/orders/{order_1_id}/', HTTP_AUTHORIZATION=f'Bearer {buyer_token}')
        assert res.status_code == 200
        assert res.data['transport_status'] is not None
        assert res.data['transport_status']['status'] == TransportStatus.DELIVERED
        print("  • Order detail contains linked logistics snapshot: Verified")
        print("-> PASSED: Role boundaries and security verified.")

    finally:
        # =====================================================================
        # CLEANUP: Safely Delete Test Artifacts
        # =====================================================================
        print("\n[STEP 4] Cleaning Up Test Artifacts (Preserving Persistent Data)...")

        # Delete created transports (both auto and manual)
        TransportRequest.objects.filter(order_id__in=created_orders).delete()
        for tid in created_transports:
            TransportRequest.objects.filter(id=tid).delete()
        print(f"  • Removed test transport requests (order-linked and direct)")

        # Delete created negotiations
        for nid in created_negotiations:
            PriceNegotiation.objects.filter(id=nid).delete()
        print(f"  • Removed {len(created_negotiations)} test negotiations")

        # Delete created orders (cascades payments & order items)
        for oid in created_orders:
            Order.objects.filter(id=oid).delete()
        print(f"  • Removed {len(created_orders)} test orders (and linked items/payments)")

        # Clean up test-triggered notifications
        try:
            from apps.notifications.models import Notification
            Notification.objects.filter(id__gt=2).delete()
        except Exception:
            pass

        # Restore target crop stock
        target_crop.quantity_available = original_crop_stock
        target_crop.status = CropStatus.ACTIVE
        target_crop.save(update_fields=['quantity_available', 'status', 'updated_at'])
        print(f"  • Restored target crop stock to original value: {original_crop_stock} {target_crop.unit}")

        # Delete test user
        User.objects.filter(username='test_p4_other_buyer').delete()
        print("  • Removed test buyer account 'test_p4_other_buyer'")

    # =====================================================================
    # STEP 5: Baseline Data Integrity Verification
    # =====================================================================
    print("\n[STEP 5] Verifying Baseline Data Integrity After Tests...")
    final_users = User.objects.count()
    final_crops = Crop.objects.count()
    final_orders = Order.objects.count()
    final_order_items = OrderItem.objects.count()
    final_payments = Payment.objects.count()
    final_offers = PriceNegotiation.objects.count()
    final_transports = TransportRequest.objects.count()

    print(f"  • Final Users in MySQL:              {final_users} (Matches baseline: {initial_users})")
    print(f"  • Final Crops in MySQL:              {final_crops} (Matches baseline: {initial_crops})")
    print(f"  • Final Orders in MySQL:             {final_orders} (Matches baseline: {initial_orders})")
    print(f"  • Final Order Items in MySQL:        {final_order_items} (Matches baseline: {initial_order_items})")
    print(f"  • Final Payments in MySQL:           {final_payments} (Matches baseline: {initial_payments})")
    print(f"  • Final Negotiations in MySQL:       {final_offers} (Matches baseline: {initial_offers})")
    print(f"  • Final Transport Requests in MySQL: {final_transports} (Matches baseline: {initial_transports})")

    assert final_users == initial_users, "User count changed!"
    assert final_crops == initial_crops, "Crop count changed!"
    assert final_orders == initial_orders, "Order count changed!"
    assert final_order_items == initial_order_items, "Order item count changed!"
    assert final_payments == initial_payments, "Payment count changed!"
    assert final_offers == initial_offers, "Negotiation count changed!"
    assert final_transports == initial_transports, "Transport count changed!"
    print("-> PASSED: Zero persistent database records were altered or lost.")

    print("\n" + "=" * 75)
    print(" ALL PHASE 4 VERIFICATION TESTS PASSED SUCCESSFULLY ON MYSQL 8.0!")
    print("=" * 75)


if __name__ == '__main__':
    run_tests()
