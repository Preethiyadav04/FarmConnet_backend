"""
FarmConnect - Phase 8 Final Audit & Verification Test Suite
Tests:
1. Admin permissions & governance (KYC, categories, crop protection, RBAC)
2. Order & inventory safety (single restoration, duplicate block, transport sync)
3. Negotiation engine (single conversion, unauthorized protection)
4. Logistics workflow (sequence machine, exclusivity, cancelled order guard)
5. Zero database baseline degradation
"""

import os
import sys
from decimal import Decimal
import requests

API_URL = "http://127.0.0.1:8000/api/"

# Setup Django
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from apps.accounts.models import User, UserRole
from apps.crops.models import Category, Crop, CropStatus, MandiPrice
from apps.orders.models import Order, OrderItem, OrderStatus, Payment, PaymentStatus, PriceNegotiation, NegotiationStatus
from apps.logistics.models import TransportRequest, TransportStatus
from apps.reviews.models import Review, Favorite

errors = []

def assert_true(cond, msg):
    if not cond:
        print(f"❌ FAIL: {msg}")
        errors.append(msg)
    else:
        print(f"✅ PASS: {msg}")

def get_counts():
    return {
        'users': User.objects.count(),
        'farmers': User.objects.filter(role=UserRole.FARMER).count(),
        'buyers': User.objects.filter(role=UserRole.BUYER).count(),
        'transporters': User.objects.filter(role=UserRole.TRANSPORTER).count(),
        'categories': Category.objects.count(),
        'crops': Crop.objects.count(),
        'mandi_prices': MandiPrice.objects.count(),
        'orders': Order.objects.count(),
        'order_items': OrderItem.objects.count(),
        'payments': Payment.objects.count(),
        'reviews': Review.objects.count(),
        'transports': TransportRequest.objects.count(),
    }

initial_counts = get_counts()
print(f"=== Initial Database Counts: {initial_counts} ===")

# 0. Authenticate baseline test actors
def login(username, password="Password@123"):
    r = requests.post(f"{API_URL}auth/login/", json={"username": username, "password": password})
    if r.status_code != 200:
        raise Exception(f"Failed login for {username}: {r.json()}")
    return r.json()["access"]

admin_token = login("admin")
farmer_token = login("farmer_ramesh")
buyer_token = login("buyer_kiran")
trans_token = login("trans_rajesh")

# Create temporary extra users for authorization tests
other_buyer = User.objects.create_user(
    username="audit_other_buyer",
    email="audit_other_buyer@farmconnect.test",
    password="Password@123",
    role=UserRole.BUYER
)
other_buyer_token = login("audit_other_buyer")

other_trans = User.objects.create_user(
    username="audit_other_trans",
    email="audit_other_trans@farmconnect.test",
    password="Password@123",
    role=UserRole.TRANSPORTER
)
other_trans_token = login("audit_other_trans")

# Setup temporary crop for audit tests
farmer_user = User.objects.get(username="farmer_ramesh")
cat_grains = Category.objects.get(slug="grains-cereals")
test_crop = Crop.objects.create(
    farmer=farmer_user,
    category=cat_grains,
    crop_name="Audit Test Organic Barley",
    variety="Himalayan Two-Row",
    price_per_unit=Decimal("3200.00"),
    quantity_available=Decimal("100.00"),
    minimum_order_quantity=Decimal("5.00"),
    unit="quintal",
    location_city="Nashik",
    location_state="Maharashtra",
    status=CropStatus.ACTIVE
)

try:
    print("\n--- 1. AUDITING ADMIN PERMISSIONS & GOVERNANCE ---")
    # 1.1 Non-admin blocked from /api/users/
    r = requests.get(f"{API_URL}users/", headers={"Authorization": f"Bearer {buyer_token}"})
    assert_true(r.status_code == 403, "Non-admin user blocked from /api/users/ (403)")

    # 1.2 Admin accesses /api/users/
    r = requests.get(f"{API_URL}users/", headers={"Authorization": f"Bearer {admin_token}"})
    assert_true(r.status_code == 200, "Admin successfully accesses /api/users/ (200)")

    # 1.3 Admin toggles KYC verification and persists in MySQL
    r = requests.post(f"{API_URL}users/{other_buyer.id}/toggle_verify/", headers={"Authorization": f"Bearer {admin_token}"})
    assert_true(r.status_code == 200 and r.json()["is_verified"] is True, "Admin toggled KYC verification ON")
    other_buyer.refresh_from_db()
    assert_true(other_buyer.is_verified is True, "KYC is_verified persisted as True in MySQL")

    r = requests.post(f"{API_URL}users/{other_buyer.id}/toggle_verify/", headers={"Authorization": f"Bearer {admin_token}"})
    assert_true(r.status_code == 200 and r.json()["is_verified"] is False, "Admin toggled KYC verification OFF")
    other_buyer.refresh_from_db()
    assert_true(other_buyer.is_verified is False, "KYC revocation persisted as False in MySQL")

    # 1.4 Category deletion guard: cannot delete category with linked crops
    r = requests.delete(f"{API_URL}categories/{cat_grains.slug}/", headers={"Authorization": f"Bearer {admin_token}"})
    assert_true(r.status_code == 400, "Category with linked crops cannot be deleted (cascade protection: 400)")

    # 1.5 Admin can create and delete empty category
    r_cat = requests.post(f"{API_URL}categories/", json={"name": "Audit Temp Cat", "description": "Temp"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert_true(r_cat.status_code == 201, "Admin created empty category (201)")
    temp_cat_slug = r_cat.json()["slug"]
    r_del = requests.delete(f"{API_URL}categories/{temp_cat_slug}/", headers={"Authorization": f"Bearer {admin_token}"})
    assert_true(r_del.status_code == 204, "Admin deleted empty category (204)")

    # 1.6 Admin analytics calculations from real DB records
    r_ana = requests.get(f"{API_URL}analytics/admin/", headers={"Authorization": f"Bearer {admin_token}"})
    assert_true(r_ana.status_code == 200 and "platform_overview" in r_ana.json(), "Admin analytics endpoint verified (200)")
    r_ana_unauth = requests.get(f"{API_URL}analytics/admin/", headers={"Authorization": f"Bearer {buyer_token}"})
    assert_true(r_ana_unauth.status_code == 403, "Non-admin blocked from /api/analytics/admin/ (403)")


    print("\n--- 2. AUDITING ORDER & INVENTORY BUSINESS LOGIC ---")
    # 2.1 Oversell prevention
    r_over = requests.post(f"{API_URL}orders/", json={
        "crop_id": test_crop.id,
        "quantity": 105.00,
        "delivery_address": "Pune APMC Yard",
        "delivery_city": "Pune",
        "delivery_state": "Maharashtra",
        "delivery_pincode": "411001",
        "contact_phone": "+919876543202",
        "payment_method": "cod"
    }, headers={"Authorization": f"Bearer {buyer_token}"})
    assert_true(r_over.status_code == 400, "Oversell order blocked with 400 Bad Request")

    # 2.2 Place valid order (order 1: 20 quintals)
    r_ord1 = requests.post(f"{API_URL}orders/", json={
        "crop_id": test_crop.id,
        "quantity": 20.00,
        "delivery_address": "Pune APMC Yard",
        "delivery_city": "Pune",
        "delivery_state": "Maharashtra",
        "delivery_pincode": "411001",
        "contact_phone": "+919876543202",
        "payment_method": "cod"
    }, headers={"Authorization": f"Bearer {buyer_token}"})
    assert_true(r_ord1.status_code == 201, "Order 1 placed (201)")
    ord1_id = r_ord1.json()["id"]

    test_crop.refresh_from_db()
    assert_true(test_crop.quantity_available == Decimal("80.00"), "Atomic stock deducted from 100 to 80")

    # Verify associated transport request for Order 1
    tr1_obj = TransportRequest.objects.get(order_id=ord1_id)
    assert_true(tr1_obj.status == TransportStatus.REQUESTED, "Transport request auto-generated for Order 1 in REQUESTED state")
    tr1_id = tr1_obj.id

    # 2.3 Buyer cancels Order 1 -> stock restored exactly once & transport cancelled
    r_cancel = requests.post(f"{API_URL}orders/{ord1_id}/cancel_order/", headers={"Authorization": f"Bearer {buyer_token}"})
    assert_true(r_cancel.status_code == 200, "Buyer cancelled Order 1 (200)")

    test_crop.refresh_from_db()
    assert_true(test_crop.quantity_available == Decimal("100.00"), "Stock restored back to 100 quintals")

    tr1_obj = TransportRequest.objects.get(id=tr1_id)
    assert_true(tr1_obj.status == TransportStatus.CANCELLED, "Linked TransportRequest auto-cancelled when order was cancelled")

    # 2.4 Duplicate cancellation rejected
    r_cancel2 = requests.post(f"{API_URL}orders/{ord1_id}/cancel_order/", headers={"Authorization": f"Bearer {buyer_token}"})
    assert_true(r_cancel2.status_code == 400, "Duplicate cancellation attempt blocked with 400")

    test_crop.refresh_from_db()
    assert_true(test_crop.quantity_available == Decimal("100.00"), "Stock not double-restored (remains exactly 100)")

    # 2.5 Place Order 2 (15 quintals) and test Farmer Rejection with transport cancellation
    r_ord2 = requests.post(f"{API_URL}orders/", json={
        "crop_id": test_crop.id,
        "quantity": 15.00,
        "delivery_address": "Mumbai Market",
        "delivery_city": "Mumbai",
        "delivery_state": "Maharashtra",
        "delivery_pincode": "400001",
        "contact_phone": "+919876543202",
        "payment_method": "cod"
    }, headers={"Authorization": f"Bearer {buyer_token}"})
    ord2_id = r_ord2.json()["id"]

    test_crop.refresh_from_db()
    assert_true(test_crop.quantity_available == Decimal("85.00"), "Stock deducted to 85 quintals")

    # Verify associated transport request for Order 2
    tr2_obj = TransportRequest.objects.get(order_id=ord2_id)
    assert_true(tr2_obj.status == TransportStatus.REQUESTED, "Transport request auto-generated for Order 2 in REQUESTED state")
    tr2_id = tr2_obj.id

    # Farmer rejects Order 2
    r_rej = requests.post(f"{API_URL}orders/{ord2_id}/reject_order/", json={"reason": "Audit rejection test"}, headers={"Authorization": f"Bearer {farmer_token}"})
    assert_true(r_rej.status_code == 200, "Farmer rejected Order 2 (200)")

    test_crop.refresh_from_db()
    assert_true(test_crop.quantity_available == Decimal("100.00"), "Stock restored back to 100 quintals after rejection")

    tr2_obj = TransportRequest.objects.get(id=tr2_id)
    assert_true(tr2_obj.status == TransportStatus.CANCELLED, "Linked TransportRequest auto-cancelled when order was rejected")

    # Duplicate rejection blocked
    r_rej2 = requests.post(f"{API_URL}orders/{ord2_id}/reject_order/", json={"reason": "Again"}, headers={"Authorization": f"Bearer {farmer_token}"})
    assert_true(r_rej2.status_code == 400, "Duplicate rejection attempt blocked with 400")

    # 2.6 Unauthorized order update blocked
    r_unauth_upd = requests.post(f"{API_URL}orders/{ord2_id}/accept_order/", headers={"Authorization": f"Bearer {buyer_token}"})
    assert_true(r_unauth_upd.status_code == 403, "Buyer cannot accept farmer's incoming order (403)")

    # 2.7 Payment status update
    # Place Order 3 to test payment status sync
    r_ord3 = requests.post(f"{API_URL}orders/", json={
        "crop_id": test_crop.id,
        "quantity": 10.00,
        "delivery_address": "Pune Market",
        "delivery_city": "Pune",
        "delivery_state": "Maharashtra",
        "delivery_pincode": "411001",
        "contact_phone": "+919876543202",
        "payment_method": "cod"
    }, headers={"Authorization": f"Bearer {buyer_token}"})
    ord3_id = r_ord3.json()["id"]

    # Buyer cannot mark payment completed
    r_pay_unauth = requests.post(f"{API_URL}orders/{ord3_id}/update_payment_status/", json={"payment_status": "completed"}, headers={"Authorization": f"Bearer {buyer_token}"})
    assert_true(r_pay_unauth.status_code == 403, "Buyer cannot update payment collection status (403)")

    # Farmer verifies payment
    r_pay_ok = requests.post(f"{API_URL}orders/{ord3_id}/update_payment_status/", json={"payment_status": "completed", "transaction_reference": "AUDIT-COD-1234"}, headers={"Authorization": f"Bearer {farmer_token}"})
    assert_true(r_pay_ok.status_code == 200, "Farmer confirmed payment collection (200)")
    pay3 = Payment.objects.get(order_id=ord3_id)
    assert_true(pay3.payment_status == PaymentStatus.COMPLETED and pay3.paid_at is not None, "Payment status COMPLETED and paid_at recorded in MySQL")


    print("\n--- 3. AUDITING NEGOTIATION ENGINE ---")
    # 3.1 Buyer proposes offer
    r_neg = requests.post(f"{API_URL}negotiations/", json={
        "listing": test_crop.id,
        "offered_price_per_unit": 2900.00,
        "quantity": 10.00,
        "message": "Bulk purchase rate"
    }, headers={"Authorization": f"Bearer {buyer_token}"})
    assert_true(r_neg.status_code == 201, "Buyer created price negotiation offer (201)")
    neg_id = r_neg.json()["id"]

    # 3.2 Unauthorized user cannot counter or accept
    r_unauth_counter = requests.post(f"{API_URL}negotiations/{neg_id}/counter/", json={"counter_price_per_unit": 3100.00}, headers={"Authorization": f"Bearer {other_buyer_token}"})
    assert_true(r_unauth_counter.status_code in [403, 404], "Unrelated user blocked from countering negotiation (403/404)")

    # 3.3 Farmer counters
    r_counter = requests.post(f"{API_URL}negotiations/{neg_id}/counter/", json={"counter_price_per_unit": 3050.00, "farmer_notes": "Best price"}, headers={"Authorization": f"Bearer {farmer_token}"})
    assert_true(r_counter.status_code == 200 and r_counter.json()["status"] == "countered", "Farmer submitted counter-offer (200)")

    # 3.4 Buyer accepts counter-offer
    r_acc_counter = requests.post(f"{API_URL}negotiations/{neg_id}/accept_counter/", headers={"Authorization": f"Bearer {buyer_token}"})
    assert_true(r_acc_counter.status_code == 200 and r_acc_counter.json()["status"] == "accepted", "Buyer accepted farmer counter-offer (200)")

    # Repeated accept blocked
    r_acc_counter2 = requests.post(f"{API_URL}negotiations/{neg_id}/accept_counter/", headers={"Authorization": f"Bearer {buyer_token}"})
    assert_true(r_acc_counter2.status_code == 400, "Repeated counter-offer accept blocked with 400")

    # 3.5 Convert to order
    r_conv = requests.post(f"{API_URL}negotiations/{neg_id}/convert_to_order/", json={
        "delivery_address": "Pune APMC Yard",
        "delivery_city": "Pune",
        "delivery_state": "Maharashtra",
        "delivery_pincode": "411001",
        "contact_phone": "+919876543202",
        "payment_method": "cod",
        "request_transport": True
    }, headers={"Authorization": f"Bearer {buyer_token}"})
    assert_true(r_conv.status_code == 201, "Accepted negotiation converted to confirmed order (201)")
    conv_order_id = r_conv.json()["order_id"]

    # Exactly one order created, repeated convert blocked
    r_conv2 = requests.post(f"{API_URL}negotiations/{neg_id}/convert_to_order/", json={}, headers={"Authorization": f"Bearer {buyer_token}"})
    assert_true(r_conv2.status_code == 400, "Repeated conversion attempt blocked with 400 (Cannot convert already converted negotiation)")


    print("\n--- 4. AUDITING TRANSPORT WORKFLOW ---")
    tr_conv = TransportRequest.objects.get(order_id=conv_order_id)
    assert_true(tr_conv.status == TransportStatus.REQUESTED, "Transport request created in REQUESTED state")

    # 4.1 Cancelled/rejected order cannot be claimed
    r_claim_cancelled = requests.post(f"{API_URL}logistics/{tr1_id}/accept_job/", headers={"Authorization": f"Bearer {trans_token}"})
    assert_true(r_claim_cancelled.status_code in [400, 404], "Transporter cannot claim transport for a cancelled order (400/404)")

    # 4.2 Transporter claims open job
    r_claim = requests.post(f"{API_URL}logistics/{tr_conv.id}/accept_job/", headers={"Authorization": f"Bearer {trans_token}"})
    assert_true(r_claim.status_code == 200 and r_claim.json()["status"] == "accepted", "Transporter claimed open shipment (200)")

    # 4.3 Another transporter cannot claim already assigned job
    r_double_claim = requests.post(f"{API_URL}logistics/{tr_conv.id}/accept_job/", headers={"Authorization": f"Bearer {other_trans_token}"})
    assert_true(r_double_claim.status_code in [400, 404], "Second transporter claim rejected (400/404)")

    # 4.4 Invalid status transition rejected
    # Attempting to jump directly from 'accepted' to 'delivered'
    r_bad_trans = requests.post(f"{API_URL}logistics/{tr_conv.id}/update_status/", json={"status": "delivered"}, headers={"Authorization": f"Bearer {trans_token}"})
    assert_true(r_bad_trans.status_code == 400, "Invalid status transition (accepted -> delivered) rejected with 400")

    # 4.5 Valid sequence: accepted -> picked_up -> in_transit -> delivered
    r_st1 = requests.post(f"{API_URL}logistics/{tr_conv.id}/update_status/", json={"status": "picked_up", "tracking_notes": "Picked up from Nashik"}, headers={"Authorization": f"Bearer {trans_token}"})
    assert_true(r_st1.status_code == 200 and r_st1.json()["status"] == "picked_up", "Status transition -> picked_up (200)")

    r_st2 = requests.post(f"{API_URL}logistics/{tr_conv.id}/update_status/", json={"status": "in_transit", "tracking_notes": "On highway"}, headers={"Authorization": f"Bearer {trans_token}"})
    assert_true(r_st2.status_code == 200 and r_st2.json()["status"] == "in_transit", "Status transition -> in_transit (200)")

    r_st3 = requests.post(f"{API_URL}logistics/{tr_conv.id}/update_status/", json={"status": "delivered", "final_charge": 1600.00}, headers={"Authorization": f"Bearer {trans_token}"})
    assert_true(r_st3.status_code == 200 and r_st3.json()["status"] == "delivered", "Status transition -> delivered (200)")

    # Delivery completion updates linked order to delivered
    conv_order_obj = Order.objects.get(id=conv_order_id)
    assert_true(conv_order_obj.status == OrderStatus.DELIVERED, "Linked order status auto-updated to DELIVERED")

    # Cancelled/rejected order cannot advance delivery status
    r_bad_adv = requests.post(f"{API_URL}logistics/{tr1_id}/update_status/", json={"status": "picked_up"}, headers={"Authorization": f"Bearer {trans_token}"})
    assert_true(r_bad_adv.status_code in [400, 403, 404], "Cannot advance delivery status on cancelled order (400/403/404)")

finally:
    print("\n--- 5. CLEANING UP AUDIT TEST RECORDS ---")
    tr_ids = [i for i in [locals().get('tr1_id'), locals().get('tr2_id'), getattr(locals().get('tr_conv'), 'id', None)] if i]
    TransportRequest.objects.filter(id__in=tr_ids).delete()
    if 'neg_id' in locals():
        PriceNegotiation.objects.filter(id=neg_id).delete()
    ord_ids = [i for i in [locals().get('ord1_id'), locals().get('ord2_id'), locals().get('ord3_id'), locals().get('conv_order_id')] if i]
    Order.objects.filter(id__in=ord_ids).delete()
    if 'test_crop' in locals():
        Crop.objects.filter(id=test_crop.id).delete()
    User.objects.filter(username__in=["audit_other_buyer", "audit_other_trans"]).delete()

final_counts = get_counts()
print(f"=== Final Database Counts: {final_counts} ===")

for k in initial_counts:
    assert_true(initial_counts[k] == final_counts[k], f"DB count for '{k}' preserved: {initial_counts[k]} == {final_counts[k]}")

if errors:
    print(f"\n❌ AUDIT FAILED with {len(errors)} issues:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("\n🎉 ALL PHASE 8 AUDIT & VERIFICATION CHECKS PASSED PERFECTLY!")
    sys.exit(0)
