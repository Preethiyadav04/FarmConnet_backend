import os
import sys
import django
import requests

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.accounts.models import User, FarmerProfile, BuyerProfile, TransporterProfile
from apps.crops.models import Category, Crop, MandiPrice, CropStatus
from apps.orders.models import Order, OrderItem, Payment, PriceNegotiation, OrderStatus, PaymentStatus, NegotiationStatus
from apps.reviews.models import Review, Favorite
from apps.logistics.models import TransportRequest, TransportStatus
from rest_framework_simplejwt.tokens import RefreshToken

API_URL = "http://127.0.0.1:8000/api/"

def get_counts():
    return {
        'users': User.objects.count(),
        'farmers': FarmerProfile.objects.count(),
        'buyers': BuyerProfile.objects.count(),
        'transporters': TransporterProfile.objects.count(),
        'categories': Category.objects.count(),
        'crops': Crop.objects.count(),
        'mandi_prices': MandiPrice.objects.count(),
        'orders': Order.objects.count(),
        'order_items': OrderItem.objects.count(),
        'payments': Payment.objects.count(),
        'reviews': Review.objects.count(),
        'transports': TransportRequest.objects.count(),
    }

# Pre-clean any previous test artifacts
Order.objects.filter(items__crop_title__startswith='P8 ').delete()
PriceNegotiation.objects.filter(listing__crop_name__startswith='P8 ').delete()
Crop.objects.filter(crop_name__startswith='P8 ').delete()
User.objects.filter(username__startswith='temp_').delete()

initial_counts = get_counts()
print(f"=== Baseline Database Counts: {initial_counts} ===")

errors = []

def assert_true(cond, msg):
    if not cond:
        print(f"❌ FAIL: {msg}")
        errors.append(msg)
    else:
        print(f"✅ PASS: {msg}")

# Setup Actors
admin_user = User.objects.filter(role='admin').first()
farmer_user = User.objects.filter(username='farmer_ramesh').first()
buyer_user = User.objects.filter(username='buyer_kiran').first()
trans_user = User.objects.filter(username='trans_rajesh').first()

def get_token(u):
    return str(RefreshToken.for_user(u).access_token)

admin_token = get_token(admin_user)
farmer_token = get_token(farmer_user)
buyer_token = get_token(buyer_user)
trans_token = get_token(trans_user)

# Create a temporary second farmer & second buyer for cross-isolation checks
other_farmer = User.objects.create_user('temp_other_farmer_p8', 'other_farmer@test.com', 'Pass123!', role='farmer')
other_buyer = User.objects.create_user('temp_other_buyer_p8', 'other_buyer@test.com', 'Pass123!', role='buyer')
other_trans = User.objects.create_user('temp_other_trans_p8', 'other_trans@test.com', 'Pass123!', role='transporter')

other_farmer_token = get_token(other_farmer)
other_buyer_token = get_token(other_buyer)
other_trans_token = get_token(other_trans)

# Category for test
cat = Category.objects.first()

print("\n--- 1. Testing Farmer Business Workflows ---")
# 1.1 Create own crop
crop_payload = {
    "category": cat.id,
    "crop_name": "P8 Organic Basmati Rice",
    "variety": "Basmati 370",
    "grade_quality": "Grade A",
    "price_per_unit": 4500.00,
    "unit": "quintal",
    "quantity_available": 50.00,
    "minimum_order_quantity": 2.00,
    "location_city": "Nashik",
    "location_state": "Maharashtra",
    "description": "Premium aged organic aromatic basmati rice."
}
r_crop = requests.post(f"{API_URL}crops/", json=crop_payload, headers={"Authorization": f"Bearer {farmer_token}"})
assert_true(r_crop.status_code == 201, f"Farmer created crop (status {r_crop.status_code})")
p8_crop_id = r_crop.json()["id"]

# 1.2 Edit own crop
r_edit = requests.patch(f"{API_URL}crops/{p8_crop_id}/", json={"price_per_unit": 4600.00}, headers={"Authorization": f"Bearer {farmer_token}"})
assert_true(r_edit.status_code == 200 and float(r_edit.json()["price_per_unit"]) == 4600.00, "Farmer edited own crop price")

# 1.3 Other farmer cannot edit
r_unauth_edit = requests.patch(f"{API_URL}crops/{p8_crop_id}/", json={"price_per_unit": 3000.00}, headers={"Authorization": f"Bearer {other_farmer_token}"})
assert_true(r_unauth_edit.status_code == 403, f"Other farmer edit blocked (status {r_unauth_edit.status_code})")

# 1.4 Toggle availability
r_toggle = requests.post(f"{API_URL}crops/{p8_crop_id}/toggle_availability/", headers={"Authorization": f"Bearer {farmer_token}"})
assert_true(r_toggle.status_code == 200 and r_toggle.json()["status"] == "unavailable", "Farmer toggled status to unavailable")
r_toggle2 = requests.post(f"{API_URL}crops/{p8_crop_id}/toggle_availability/", headers={"Authorization": f"Bearer {farmer_token}"})
assert_true(r_toggle2.status_code == 200 and r_toggle2.json()["status"] == "active", "Farmer toggled status back to active")

# 1.5 Farmer my_crops endpoint
r_my = requests.get(f"{API_URL}crops/my_crops/", headers={"Authorization": f"Bearer {farmer_token}"})
assert_true(r_my.status_code == 200, "Farmer fetched my_crops")

print("\n--- 2. Testing Order & Inventory Safety ---")
# 2.1 Buyer places order on P8 crop
order_payload = {
    "crop_id": p8_crop_id,
    "quantity": 10.00,
    "delivery_address": "Shop 12, Market Yard",
    "delivery_city": "Pune",
    "delivery_state": "Maharashtra",
    "delivery_pincode": "411037",
    "contact_phone": "+919876543202",
    "payment_method": "cod"
}
r_ord = requests.post(f"{API_URL}orders/", json=order_payload, headers={"Authorization": f"Bearer {buyer_token}"})
assert_true(r_ord.status_code == 201, f"Buyer placed order (status {r_ord.status_code})")
p8_order = r_ord.json()
p8_order_id = p8_order["id"]

# Check inventory deduction in MySQL
crop_obj = Crop.objects.get(id=p8_crop_id)
assert_true(crop_obj.quantity_available == 40.00, f"Atomic inventory deducted from 50 to 40 (got {crop_obj.quantity_available})")

# 2.2 Attempt to oversell
r_over = requests.post(f"{API_URL}orders/", json={**order_payload, "quantity": 100.00}, headers={"Authorization": f"Bearer {buyer_token}"})
assert_true(r_over.status_code == 400, "Oversell order blocked with 400 Bad Request")

# 2.3 Other buyer cannot view this order
r_other_ord = requests.get(f"{API_URL}orders/{p8_order_id}/", headers={"Authorization": f"Bearer {other_buyer_token}"})
assert_true(r_other_ord.status_code in [403, 404], f"Cross-buyer order view blocked (status {r_other_ord.status_code})")

# 2.4 Farmer accepts order
r_acc = requests.post(f"{API_URL}orders/{p8_order_id}/accept_order/", headers={"Authorization": f"Bearer {farmer_token}"})
assert_true(r_acc.status_code == 200 and r_acc.json()["status"] == "confirmed", "Farmer accepted order -> status confirmed")

# 2.5 Buyer cancels confirmed order before dispatch -> stock restored atomically
r_canc = requests.post(f"{API_URL}orders/{p8_order_id}/cancel_order/", json={"reason": "Test cancel"}, headers={"Authorization": f"Bearer {buyer_token}"})
assert_true(r_canc.status_code == 200 and r_canc.json()["status"] == "cancelled", "Buyer cancelled order -> status cancelled")
crop_obj.refresh_from_db()
assert_true(crop_obj.quantity_available == 50.00, f"Stock restored back to 50 (got {crop_obj.quantity_available})")

# 2.6 Place second order to test farmer rejection and stock restoration
r_ord2 = requests.post(f"{API_URL}orders/", json=order_payload, headers={"Authorization": f"Bearer {buyer_token}"})
p8_order2_id = r_ord2.json()["id"]
r_rej = requests.post(f"{API_URL}orders/{p8_order2_id}/reject_order/", json={"reason": "Crop reserved"}, headers={"Authorization": f"Bearer {farmer_token}"})
assert_true(r_rej.status_code == 200 and r_rej.json()["status"] == "rejected", "Farmer rejected order -> status rejected")
crop_obj.refresh_from_db()
assert_true(crop_obj.quantity_available == 50.00, f"Stock restored back to 50 after rejection (got {crop_obj.quantity_available})")

print("\n--- 3. Testing Price Negotiation Engine ---")
# 3.1 Buyer submits offer
neg_payload = {
    "listing": p8_crop_id,
    "offered_price_per_unit": 4000.00,
    "quantity": 5.00,
    "message": "Bulk commercial purchase"
}
r_neg = requests.post(f"{API_URL}negotiations/", json=neg_payload, headers={"Authorization": f"Bearer {buyer_token}"})
assert_true(r_neg.status_code == 201, f"Buyer proposed price offer (status {r_neg.status_code})")
p8_neg_id = r_neg.json()["id"]

# 3.2 Farmer counters offer
r_counter = requests.post(f"{API_URL}negotiations/{p8_neg_id}/counter/", json={"counter_price_per_unit": 4300.00, "farmer_notes": "Best bulk rate"}, headers={"Authorization": f"Bearer {farmer_token}"})
assert_true(r_counter.status_code == 200 and r_counter.json()["status"] == "countered", "Farmer submitted counter-offer")

# 3.3 Buyer accepts counter-offer
r_acc_counter = requests.post(f"{API_URL}negotiations/{p8_neg_id}/accept_counter/", headers={"Authorization": f"Bearer {buyer_token}"})
assert_true(r_acc_counter.status_code == 200 and r_acc_counter.json()["status"] == "accepted", "Buyer accepted farmer counter-offer")

# 3.4 Convert to order
r_conv = requests.post(f"{API_URL}negotiations/{p8_neg_id}/convert_to_order/", json={
    "delivery_address": "Pune APMC Yard",
    "delivery_city": "Pune",
    "delivery_state": "Maharashtra",
    "delivery_pincode": "411001",
    "contact_phone": "+919876543202",
    "payment_method": "cod",
    "request_transport": True
}, headers={"Authorization": f"Bearer {buyer_token}"})
assert_true(r_conv.status_code == 201, "Accepted negotiation converted to confirmed order")
conv_order = r_conv.json()
conv_order_id = conv_order.get("order_id") or Order.objects.get(order_number=conv_order["order_number"]).id

print("\n--- 4. Testing Transporter Logistics Workflows ---")
# 4.1 Browse available jobs
r_avail = requests.get(f"{API_URL}logistics/available_jobs/", headers={"Authorization": f"Bearer {trans_token}"})
assert_true(r_avail.status_code == 200, "Transporter fetched available jobs")
avail_jobs = r_avail.json().get('results', r_avail.json())

# Find the transport request created for converted order
p8_trans_req = TransportRequest.objects.filter(order_id=conv_order_id).first()
assert_true(p8_trans_req is not None, "TransportRequest automatically generated for order")

# 4.2 Transporter accepts job
r_claim = requests.post(f"{API_URL}logistics/{p8_trans_req.id}/accept_job/", headers={"Authorization": f"Bearer {trans_token}"})
assert_true(r_claim.status_code == 200 and r_claim.json()["status"] == "accepted", "Transporter claimed transport job")

# 4.3 Other transporter cannot claim or update
r_unauth_claim = requests.post(f"{API_URL}logistics/{p8_trans_req.id}/accept_job/", headers={"Authorization": f"Bearer {other_trans_token}"})
assert_true(r_unauth_claim.status_code in [400, 404], "Second transporter claim blocked (HTTP 400 or 404)")

# 4.4 Status transition: accepted -> picked_up
r_st1 = requests.post(f"{API_URL}logistics/{p8_trans_req.id}/update_status/", json={"status": "picked_up", "tracking_notes": "Loaded at farm"}, headers={"Authorization": f"Bearer {trans_token}"})
assert_true(r_st1.status_code == 200 and r_st1.json()["status"] == "picked_up", "Status updated -> picked_up")

# 4.5 Status transition: picked_up -> in_transit
r_st2 = requests.post(f"{API_URL}logistics/{p8_trans_req.id}/update_status/", json={"status": "in_transit", "current_location": "NH-60 Toll"}, headers={"Authorization": f"Bearer {trans_token}"})
assert_true(r_st2.status_code == 200 and r_st2.json()["status"] == "in_transit", "Status updated -> in_transit")

# 4.6 Status transition: in_transit -> delivered
r_st3 = requests.post(f"{API_URL}logistics/{p8_trans_req.id}/update_status/", json={"status": "delivered", "final_charge": 1800.00}, headers={"Authorization": f"Bearer {trans_token}"})
assert_true(r_st3.status_code == 200 and r_st3.json()["status"] == "delivered", "Status updated -> delivered")

# Order is now delivered
conv_order_obj = Order.objects.get(id=conv_order_id)
assert_true(conv_order_obj.status == OrderStatus.DELIVERED, "Order status auto-advanced to DELIVERED")

print("\n--- 5. Testing Buyer Reviews & Favorites ---")
# 5.1 Undelivered order review blocked
r_rev_blocked = requests.post(f"{API_URL}reviews/", json={"order": p8_order_id, "rating": 5, "comment": "Premature review"}, headers={"Authorization": f"Bearer {buyer_token}"})
assert_true(r_rev_blocked.status_code == 400, "Reviewing undelivered/cancelled order blocked with 400")

# 5.2 Reviewing delivered order succeeds
r_rev = requests.post(f"{API_URL}reviews/", json={"order": conv_order_id, "rating": 5, "comment": "Superb fragrant basmati rice!"}, headers={"Authorization": f"Bearer {buyer_token}"})
assert_true(r_rev.status_code == 201, f"Buyer reviewed delivered order (status {r_rev.status_code})")
p8_review_id = r_rev.json()["id"]

# 5.3 Favorites toggle
r_fav1 = requests.post(f"{API_URL}favorites/toggle/", json={"crop_id": p8_crop_id}, headers={"Authorization": f"Bearer {buyer_token}"})
assert_true(r_fav1.status_code in [200, 201] and r_fav1.json()["is_favorited"] is True, "Crop bookmarked to favorites")
r_fav2 = requests.post(f"{API_URL}favorites/toggle/", json={"crop_id": p8_crop_id}, headers={"Authorization": f"Bearer {buyer_token}"})
assert_true(r_fav2.status_code == 200 and r_fav2.json()["is_favorited"] is False, "Crop un-bookmarked from favorites")

print("\n--- 6. Testing Admin Governance APIs ---")
# 6.1 Non-admin access to /api/users/ blocked
r_users_unauth = requests.get(f"{API_URL}users/", headers={"Authorization": f"Bearer {buyer_token}"})
assert_true(r_users_unauth.status_code == 403, "Non-admin blocked from /api/users/")

# 6.2 Admin access to /api/users/ succeeds
r_users_admin = requests.get(f"{API_URL}users/", headers={"Authorization": f"Bearer {admin_token}"})
assert_true(r_users_admin.status_code == 200, "Admin accessed /api/users/")

# 6.3 Admin toggles verification
r_toggle_k = requests.post(f"{API_URL}users/{other_buyer.id}/toggle_verify/", headers={"Authorization": f"Bearer {admin_token}"})
assert_true(r_toggle_k.status_code == 200 and r_toggle_k.json()["is_verified"] is True, "Admin verified user KYC")

# 6.4 Admin creates category
r_cat_create = requests.post(f"{API_URL}categories/", json={"name": "P8 Test Fungi", "description": "Mushrooms and fungi"}, headers={"Authorization": f"Bearer {admin_token}"})
assert_true(r_cat_create.status_code == 201, "Admin created category")
p8_cat_slug = r_cat_create.json()["slug"]

# 6.5 Admin deletes category
r_cat_del = requests.delete(f"{API_URL}categories/{p8_cat_slug}/", headers={"Authorization": f"Bearer {admin_token}"})
assert_true(r_cat_del.status_code == 204, "Admin deleted category")

# 6.6 Admin analytics check
r_admin_ana = requests.get(f"{API_URL}analytics/admin/", headers={"Authorization": f"Bearer {admin_token}"})
assert_true(r_admin_ana.status_code == 200 and ("platform_overview" in r_admin_ana.json() or "users" in r_admin_ana.json()), "Admin analytics endpoint verified")

print("\n--- 7. Cleaning Up Test Records ---")
# Clean up temporary artifacts created in this test
Review.objects.filter(id=p8_review_id).delete()
TransportRequest.objects.filter(id=p8_trans_req.id).delete()
PriceNegotiation.objects.filter(id=p8_neg_id).delete()
Order.objects.filter(id__in=[p8_order_id, p8_order2_id, conv_order_id]).delete()
Crop.objects.filter(id=p8_crop_id).delete()
User.objects.filter(username__startswith='temp_').delete()

final_counts = get_counts()
print(f"=== Final Database Counts: {final_counts} ===")

for k in initial_counts:
    assert_true(initial_counts[k] == final_counts[k], f"DB count for '{k}' preserved: {initial_counts[k]} == {final_counts[k]}")

if errors:
    print(f"\n❌ FAILED with {len(errors)} errors:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("\n🎉 ALL PHASE 8 BUSINESS WORKFLOWS & PERMISSIONS VERIFIED SUCCESSFULLY!")
    sys.exit(0)
