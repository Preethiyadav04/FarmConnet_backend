"""
FarmConnect - Phase 9 Comprehensive End-to-End & Security Test Suite
Covers:
- Section A: Authentication & Token Lifecycle
- Section B: Public Marketplace & Transparency
- Section C: Farmer Workflows
- Section D: Buyer Workflows & Order Lifecycle
- Section E: Transporter Logistics & State Machine
- Section F: Admin Governance & RBAC
- Section G: Business Logic & Data Integrity
- Section H: Security & Information Disclosure Audit
- Section I: Database Baseline Preservation
"""

import os
import sys
from decimal import Decimal
import requests

API_URL = "http://127.0.0.1:8000/api/"

# Setup Django environment
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from apps.accounts.models import User, UserRole, FarmerProfile, BuyerProfile, TransporterProfile
from apps.crops.models import Category, Crop, CropStatus, MandiPrice
from apps.orders.models import Order, OrderItem, OrderStatus, Payment, PaymentStatus, PriceNegotiation, NegotiationStatus
from apps.logistics.models import TransportRequest, TransportStatus
from apps.reviews.models import Review, Favorite
from apps.notifications.models import Notification

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
        'farmer_profiles': FarmerProfile.objects.count(),
        'buyer_profiles': BuyerProfile.objects.count(),
        'transporter_profiles': TransporterProfile.objects.count(),
        'categories': Category.objects.count(),
        'crops': Crop.objects.count(),
        'mandi_prices': MandiPrice.objects.count(),
        'orders': Order.objects.count(),
        'order_items': OrderItem.objects.count(),
        'payments': Payment.objects.count(),
        'negotiations': PriceNegotiation.objects.count(),
        'reviews': Review.objects.count(),
        'favorites': Favorite.objects.count(),
        'notifications': Notification.objects.count(),
        'transports': TransportRequest.objects.count(),
    }

initial_counts = get_counts()
print(f"=== Initial Database Counts: {initial_counts} ===")

# Test cleanup trackers
created_user_ids = []
created_crop_ids = []
created_order_ids = []
created_neg_ids = []
created_review_ids = []
created_cat_slugs = []

try:
    print("\n--- A. TESTING AUTHENTICATION & TOKEN LIFECYCLE ---")
    # A.1 Register Farmer with profile data
    r_reg_f = requests.post(f"{API_URL}auth/register/", json={
        "username": "p9_test_farmer",
        "email": "p9_farmer@farmconnect.test",
        "password": "Password@123",
        "password_confirm": "Password@123",
        "role": "farmer",
        "phone": "+919876543001",
        "city": "Nashik",
        "state": "Maharashtra",
        "farm_name": "P9 Green Orchards",
        "farm_size_acres": 25.0
    })
    assert_true(r_reg_f.status_code == 201, "Farmer registration successful (201)")
    p9_farmer_id = r_reg_f.json()["id"]
    created_user_ids.append(p9_farmer_id)
    assert_true(FarmerProfile.objects.filter(user_id=p9_farmer_id, farm_name="P9 Green Orchards").exists(), "FarmerProfile persisted in MySQL")

    # A.2 Register Buyer with profile data
    r_reg_b = requests.post(f"{API_URL}auth/register/", json={
        "username": "p9_test_buyer",
        "email": "p9_buyer@farmconnect.test",
        "password": "Password@123",
        "password_confirm": "Password@123",
        "role": "buyer",
        "phone": "+919876543002",
        "business_name": "P9 Wholesale Agrico",
        "buyer_type": "wholesaler"
    })
    assert_true(r_reg_b.status_code == 201, "Buyer registration successful (201)")
    p9_buyer_id = r_reg_b.json()["id"]
    created_user_ids.append(p9_buyer_id)

    # A.3 Register Transporter with profile data
    r_reg_t = requests.post(f"{API_URL}auth/register/", json={
        "username": "p9_test_trans",
        "email": "p9_trans@farmconnect.test",
        "password": "Password@123",
        "password_confirm": "Password@123",
        "role": "transporter",
        "phone": "+919876543003",
        "vehicle_number": "MH-15-P9-9999",
        "vehicle_type": "10-Ton Truck",
        "capacity_tons": 10.0
    })
    assert_true(r_reg_t.status_code == 201, "Transporter registration successful (201)")
    p9_trans_id = r_reg_t.json()["id"]
    created_user_ids.append(p9_trans_id)

    # A.4 Duplicate username rejection
    r_dup_u = requests.post(f"{API_URL}auth/register/", json={
        "username": "p9_test_farmer",
        "email": "diff@farmconnect.test",
        "password": "Password@123",
        "password_confirm": "Password@123",
        "role": "farmer"
    })
    assert_true(r_dup_u.status_code == 400 and "username" in r_dup_u.json(), "Duplicate username rejected with 400")

    # A.5 Duplicate email rejection
    r_dup_e = requests.post(f"{API_URL}auth/register/", json={
        "username": "diff_user",
        "email": "p9_farmer@farmconnect.test",
        "password": "Password@123",
        "password_confirm": "Password@123",
        "role": "farmer"
    })
    assert_true(r_dup_e.status_code == 400 and "email" in r_dup_e.json(), "Duplicate email rejected with 400")

    # A.6 Password mismatch rejection
    r_mismatch = requests.post(f"{API_URL}auth/register/", json={
        "username": "diff_user2",
        "email": "diff2@farmconnect.test",
        "password": "Password@123",
        "password_confirm": "MismatchPass@123",
        "role": "farmer"
    })
    assert_true(r_mismatch.status_code == 400, "Password mismatch rejected with 400")

    # A.7 Invalid Login
    r_inv_login = requests.post(f"{API_URL}auth/login/", json={"username": "p9_test_farmer", "password": "WrongPassword"})
    assert_true(r_inv_login.status_code == 401, "Invalid login credentials rejected with 401")

    # A.8 Valid Login
    r_login = requests.post(f"{API_URL}auth/login/", json={"username": "p9_test_farmer", "password": "Password@123"})
    assert_true(r_login.status_code == 200 and "access" in r_login.json(), "Valid login returns access and refresh tokens (200)")
    p9_farmer_token = r_login.json()["access"]
    p9_farmer_refresh = r_login.json()["refresh"]

    # A.9 Token Refresh
    r_ref = requests.post(f"{API_URL}auth/token/refresh/", json={"refresh": p9_farmer_refresh})
    assert_true(r_ref.status_code == 200 and "access" in r_ref.json(), "Token refresh returns new access token (200)")
    p9_farmer_token = r_ref.json()["access"]

    # A.10 Invalid Refresh Token
    r_inv_ref = requests.post(f"{API_URL}auth/token/refresh/", json={"refresh": "invalid_refresh_token_here"})
    assert_true(r_inv_ref.status_code == 401, "Invalid refresh token rejected with 401")

    # A.11 Authenticated Profile Retrieval
    r_prof = requests.get(f"{API_URL}auth/profile/", headers={"Authorization": f"Bearer {p9_farmer_token}"})
    assert_true(r_prof.status_code == 200 and r_prof.json()["username"] == "p9_test_farmer", "Authenticated profile retrieval succeeds (200)")

    # Login buyer and transporter
    r_b_login = requests.post(f"{API_URL}auth/login/", json={"username": "p9_test_buyer", "password": "Password@123"})
    p9_buyer_token = r_b_login.json()["access"]
    r_t_login = requests.post(f"{API_URL}auth/login/", json={"username": "p9_test_trans", "password": "Password@123"})
    p9_trans_token = r_t_login.json()["access"]

    # Baseline Admin token
    r_adm_login = requests.post(f"{API_URL}auth/login/", json={"username": "admin", "password": "Password@123"})
    admin_token = r_adm_login.json()["access"]


    print("\n--- B. TESTING PUBLIC MARKETPLACE & MANDI TRANSPARENCY ---")
    # B.1 Public categories catalog
    r_cat = requests.get(f"{API_URL}categories/")
    assert_true(r_cat.status_code == 200 and len(r_cat.json()) >= 6, f"Categories catalog public access (returned {len(r_cat.json())} categories)")

    # B.2 Public crops listing with pagination
    r_crops = requests.get(f"{API_URL}crops/")
    assert_true(r_crops.status_code == 200 and "results" in r_crops.json(), "Public crop catalog paginated retrieval (200)")

    # B.3 Search by crop name
    r_search = requests.get(f"{API_URL}crops/?search=Wheat")
    assert_true(r_search.status_code == 200, "Crop search by name verified (200)")

    # B.4 Filter by category
    r_filt = requests.get(f"{API_URL}crops/?category=grains-cereals")
    assert_true(r_filt.status_code == 200, "Category filter verified (200)")

    # B.5 Sort by price ascending & descending
    r_sort_asc = requests.get(f"{API_URL}crops/?sort_by=price_asc")
    r_sort_desc = requests.get(f"{API_URL}crops/?sort_by=price_desc")
    assert_true(r_sort_asc.status_code == 200 and r_sort_desc.status_code == 200, "Price sorting options verified (200)")

    # B.6 Crop details & view counter
    c_first = r_crops.json()["results"][0]
    r_cdet = requests.get(f"{API_URL}crops/{c_first['id']}/")
    assert_true(r_cdet.status_code == 200 and ("mandi_benchmark" in r_cdet.json() or "mandi_benchmarks" in r_cdet.json()), "Single crop details with mandi benchmarks retrieved (200)")

    # B.7 Mandi Price Benchmarks API
    r_mandi = requests.get(f"{API_URL}mandi-prices/")
    assert_true(r_mandi.status_code == 200, "Public Mandi prices endpoint verified (200)")

    # B.8 Mandi Comparison API
    r_mandi_cmp = requests.get(f"{API_URL}mandi-prices/compare/?crop=Wheat")
    assert_true(r_mandi_cmp.status_code == 200, "Mandi benchmark price comparison endpoint verified (200)")


    print("\n--- C. TESTING FARMER WORKFLOWS & INVENTORY CRUD ---")
    # C.1 Create crop listing
    cat_grains = Category.objects.get(slug="grains-cereals")
    r_c_new = requests.post(f"{API_URL}crops/", json={
        "crop_name": "Phase 9 Golden Sorghum",
        "category": cat_grains.id,
        "variety": "Maldandi Sweet Jowar",
        "description": "Rich organic sorghum harvested under drip irrigation.",
        "grade_quality": "Grade A",
        "price_per_unit": 2800.00,
        "unit": "quintal",
        "quantity_available": 100.00,
        "minimum_order_quantity": 5.00,
        "location_city": "Nashik",
        "location_state": "Maharashtra"
    }, headers={"Authorization": f"Bearer {p9_farmer_token}"})
    assert_true(r_c_new.status_code == 201, "Farmer published new crop listing (201)")
    p9_crop_id = r_c_new.json()["id"]
    created_crop_ids.append(p9_crop_id)

    # C.2 Edit crop price and quantity
    r_c_edit = requests.patch(f"{API_URL}crops/{p9_crop_id}/", json={
        "price_per_unit": 2750.00,
        "quantity_available": 90.00
    }, headers={"Authorization": f"Bearer {p9_farmer_token}"})
    assert_true(r_c_edit.status_code == 200 and float(r_c_edit.json()["price_per_unit"]) == 2750.00, "Farmer updated crop price and stock (200)")

    # C.3 Toggle availability to unavailable and back
    r_tog1 = requests.post(f"{API_URL}crops/{p9_crop_id}/toggle_availability/", headers={"Authorization": f"Bearer {p9_farmer_token}"})
    assert_true(r_tog1.status_code == 200 and r_tog1.json()["status"] == "unavailable", "Toggled to unavailable (200)")
    r_tog2 = requests.post(f"{API_URL}crops/{p9_crop_id}/toggle_availability/", headers={"Authorization": f"Bearer {p9_farmer_token}"})
    assert_true(r_tog2.status_code == 200 and r_tog2.json()["status"] == "active", "Toggled back to active (200)")

    # C.4 Ownership guard: other user cannot edit farmer crop
    r_unauth_edit = requests.patch(f"{API_URL}crops/{p9_crop_id}/", json={"price_per_unit": 100.00}, headers={"Authorization": f"Bearer {p9_buyer_token}"})
    assert_true(r_unauth_edit.status_code in [403, 404], "Non-owner blocked from modifying crop (403/404)")

    # C.5 Farmer fetches my_crops
    r_my = requests.get(f"{API_URL}crops/my_crops/", headers={"Authorization": f"Bearer {p9_farmer_token}"})
    assert_true(r_my.status_code == 200 and any(c["id"] == p9_crop_id for c in r_my.json()["results"]), "Farmer my_crops includes newly listed crop (200)")


    print("\n--- D. TESTING BUYER WORKFLOWS & ORDER LIFECYCLE ---")
    # D.1 Oversell attempt blocked
    r_over = requests.post(f"{API_URL}orders/", json={
        "crop_id": p9_crop_id,
        "quantity": 150.00,
        "delivery_address": "Pune Wholesale Market",
        "delivery_city": "Pune",
        "delivery_state": "Maharashtra",
        "contact_phone": "+919876543002"
    }, headers={"Authorization": f"Bearer {p9_buyer_token}"})
    assert_true(r_over.status_code == 400, "Oversell attempt blocked with 400 Bad Request")

    # D.2 Place valid purchase order (Order A: 20 quintals)
    r_ord_a = requests.post(f"{API_URL}orders/", json={
        "crop_id": p9_crop_id,
        "quantity": 20.00,
        "delivery_address": "Pune Wholesale Market",
        "delivery_city": "Pune",
        "delivery_state": "Maharashtra",
        "contact_phone": "+919876543002",
        "payment_method": "cod"
    }, headers={"Authorization": f"Bearer {p9_buyer_token}"})
    assert_true(r_ord_a.status_code == 201, "Buyer placed Order A (201)")
    ord_a_id = r_ord_a.json()["id"]
    created_order_ids.append(ord_a_id)

    # Check atomic stock deduction
    c_check = Crop.objects.get(id=p9_crop_id)
    assert_true(c_check.quantity_available == Decimal("70.00"), "Atomic stock deducted from 90 to 70")

    # D.3 Buyer cancels Order A -> stock restored & transport request auto-cancelled
    tr_a = TransportRequest.objects.get(order_id=ord_a_id)
    assert_true(tr_a.status == TransportStatus.REQUESTED, "TransportRequest auto-generated for Order A in REQUESTED state")

    r_cancel = requests.post(f"{API_URL}orders/{ord_a_id}/cancel_order/", headers={"Authorization": f"Bearer {p9_buyer_token}"})
    assert_true(r_cancel.status_code == 200, "Buyer cancelled Order A (200)")

    c_check.refresh_from_db()
    assert_true(c_check.quantity_available == Decimal("90.00"), "Stock restored back to 90 quintals upon cancellation")

    tr_a.refresh_from_db()
    assert_true(tr_a.status == TransportStatus.CANCELLED, "Linked TransportRequest auto-cancelled when Order A cancelled")

    # Duplicate cancellation blocked
    r_cancel_dup = requests.post(f"{API_URL}orders/{ord_a_id}/cancel_order/", headers={"Authorization": f"Bearer {p9_buyer_token}"})
    assert_true(r_cancel_dup.status_code == 400, "Duplicate order cancellation rejected with 400")

    # D.4 Place Order B (10 quintals) and Farmer Rejects -> stock restored & transport cancelled
    r_ord_b = requests.post(f"{API_URL}orders/", json={
        "crop_id": p9_crop_id,
        "quantity": 10.00,
        "delivery_address": "Mumbai Terminal Yard",
        "delivery_city": "Mumbai",
        "delivery_state": "Maharashtra",
        "contact_phone": "+919876543002",
        "payment_method": "cod"
    }, headers={"Authorization": f"Bearer {p9_buyer_token}"})
    ord_b_id = r_ord_b.json()["id"]
    created_order_ids.append(ord_b_id)

    tr_b = TransportRequest.objects.get(order_id=ord_b_id)
    r_rej = requests.post(f"{API_URL}orders/{ord_b_id}/reject_order/", json={"reason": "Harvest allocated"}, headers={"Authorization": f"Bearer {p9_farmer_token}"})
    assert_true(r_rej.status_code == 200, "Farmer rejected Order B (200)")

    c_check.refresh_from_db()
    assert_true(c_check.quantity_available == Decimal("90.00"), "Stock restored back to 90 quintals after rejection")

    tr_b.refresh_from_db()
    assert_true(tr_b.status == TransportStatus.CANCELLED, "Linked TransportRequest auto-cancelled when Order B rejected")

    # Duplicate rejection blocked
    r_rej_dup = requests.post(f"{API_URL}orders/{ord_b_id}/reject_order/", headers={"Authorization": f"Bearer {p9_farmer_token}"})
    assert_true(r_rej_dup.status_code == 400, "Duplicate rejection blocked with 400")

    # D.5 Buyer cannot accept farmer incoming orders
    r_unauth_acc = requests.post(f"{API_URL}orders/{ord_b_id}/accept_order/", headers={"Authorization": f"Bearer {p9_buyer_token}"})
    assert_true(r_unauth_acc.status_code in [400, 403], "Buyer cannot accept farmer incoming orders (400/403)")


    print("\n--- E. TESTING PRICE NEGOTIATION ENGINE ---")
    # E.1 Buyer creates price negotiation offer
    r_neg = requests.post(f"{API_URL}negotiations/", json={
        "listing": p9_crop_id,
        "offered_price_per_unit": 2500.00,
        "quantity": 15.00,
        "message": "Bulk purchase rate request"
    }, headers={"Authorization": f"Bearer {p9_buyer_token}"})
    assert_true(r_neg.status_code == 201, "Buyer submitted price negotiation offer (201)")
    neg_id = r_neg.json()["id"]
    created_neg_ids.append(neg_id)

    # E.2 Farmer proposes counter-offer
    r_counter = requests.post(f"{API_URL}negotiations/{neg_id}/counter/", json={
        "counter_price_per_unit": 2650.00,
        "farmer_notes": "Best bulk rate possible"
    }, headers={"Authorization": f"Bearer {p9_farmer_token}"})
    assert_true(r_counter.status_code == 200 and r_counter.json()["status"] == "countered", "Farmer submitted counter-offer (200)")

    # E.3 Buyer accepts counter-offer
    r_acc_counter = requests.post(f"{API_URL}negotiations/{neg_id}/accept_counter/", headers={"Authorization": f"Bearer {p9_buyer_token}"})
    assert_true(r_acc_counter.status_code == 200 and r_acc_counter.json()["status"] == "accepted", "Buyer accepted counter-offer (200)")

    # E.4 Buyer converts accepted negotiation into confirmed order
    r_conv = requests.post(f"{API_URL}negotiations/{neg_id}/convert_to_order/", json={
        "delivery_address": "Pune Agrico Godown #4",
        "delivery_city": "Pune",
        "delivery_state": "Maharashtra",
        "contact_phone": "+919876543002",
        "payment_method": "cod",
        "request_transport": True
    }, headers={"Authorization": f"Bearer {p9_buyer_token}"})
    assert_true(r_conv.status_code == 201, "Converted negotiation to confirmed order (201)")
    conv_order_id = r_conv.json()["order_id"]
    created_order_ids.append(conv_order_id)

    # E.5 Repeated conversion rejected
    r_conv_dup = requests.post(f"{API_URL}negotiations/{neg_id}/convert_to_order/", json={}, headers={"Authorization": f"Bearer {p9_buyer_token}"})
    assert_true(r_conv_dup.status_code == 400, "Repeated negotiation conversion attempt blocked with 400")


    print("\n--- F. TESTING TRANSPORTER LOGISTICS WORKFLOWS ---")
    tr_conv = TransportRequest.objects.get(order_id=conv_order_id)
    assert_true(tr_conv.status == TransportStatus.REQUESTED, "TransportRequest created in REQUESTED status")

    # F.1 Transporter cannot claim transport for cancelled order
    r_claim_canc = requests.post(f"{API_URL}logistics/{tr_a.id}/accept_job/", headers={"Authorization": f"Bearer {p9_trans_token}"})
    assert_true(r_claim_canc.status_code in [400, 404], "Transporter cannot claim cancelled shipment (400/404)")

    # F.2 Transporter claims open shipment
    r_claim = requests.post(f"{API_URL}logistics/{tr_conv.id}/accept_job/", headers={"Authorization": f"Bearer {p9_trans_token}"})
    assert_true(r_claim.status_code == 200 and r_claim.json()["status"] == "accepted", "Transporter claimed open shipment (200)")

    # F.3 Second transporter cannot claim already assigned shipment
    baseline_trans_token = requests.post(f"{API_URL}auth/login/", json={"username": "trans_rajesh", "password": "Password@123"}).json()["access"]
    r_double_claim = requests.post(f"{API_URL}logistics/{tr_conv.id}/accept_job/", headers={"Authorization": f"Bearer {baseline_trans_token}"})
    assert_true(r_double_claim.status_code in [400, 404], "Second transporter claim blocked (400/404)")

    # F.4 Invalid status transition rejected (jumping from accepted directly to delivered)
    r_bad_trans = requests.post(f"{API_URL}logistics/{tr_conv.id}/update_status/", json={"status": "delivered"}, headers={"Authorization": f"Bearer {p9_trans_token}"})
    assert_true(r_bad_trans.status_code == 400, "Invalid jump transition (accepted -> delivered) rejected with 400")

    # F.5 Valid sequence: accepted -> picked_up -> in_transit -> delivered
    r_st1 = requests.post(f"{API_URL}logistics/{tr_conv.id}/update_status/", json={"status": "picked_up", "tracking_notes": "Loaded at farm"}, headers={"Authorization": f"Bearer {p9_trans_token}"})
    assert_true(r_st1.status_code == 200 and r_st1.json()["status"] == "picked_up", "Status transition -> picked_up (200)")

    r_st2 = requests.post(f"{API_URL}logistics/{tr_conv.id}/update_status/", json={"status": "in_transit", "tracking_notes": "On highway route"}, headers={"Authorization": f"Bearer {p9_trans_token}"})
    assert_true(r_st2.status_code == 200 and r_st2.json()["status"] == "in_transit", "Status transition -> in_transit (200)")

    r_st3 = requests.post(f"{API_URL}logistics/{tr_conv.id}/update_status/", json={"status": "delivered", "final_charge": 1750.00}, headers={"Authorization": f"Bearer {p9_trans_token}"})
    assert_true(r_st3.status_code == 200 and r_st3.json()["status"] == "delivered", "Status transition -> delivered (200)")

    # Linked order auto-advanced to delivered
    conv_order_obj = Order.objects.get(id=conv_order_id)
    assert_true(conv_order_obj.status == OrderStatus.DELIVERED, "Linked order auto-advanced to DELIVERED in MySQL")


    print("\n--- G. TESTING REVIEWS, RATINGS & FAVORITES ---")
    # G.1 Attempting to review non-delivered order (Order A was cancelled)
    r_rev_bad = requests.post(f"{API_URL}reviews/", json={
        "order": ord_a_id,
        "rating": 5,
        "comment": "Invalid review attempt"
    }, headers={"Authorization": f"Bearer {p9_buyer_token}"})
    assert_true(r_rev_bad.status_code == 400, "Reviewing non-delivered order blocked with 400")

    # G.2 Review delivered order
    r_rev_ok = requests.post(f"{API_URL}reviews/", json={
        "order": conv_order_id,
        "rating": 5,
        "comment": "Exceptional quality sweet jowar! Prompt shipment."
    }, headers={"Authorization": f"Bearer {p9_buyer_token}"})
    assert_true(r_rev_ok.status_code == 201, "Review on delivered order submitted (201)")
    p9_review_id = r_rev_ok.json()["id"]
    created_review_ids.append(p9_review_id)

    # G.3 Duplicate review on same order blocked
    r_rev_dup = requests.post(f"{API_URL}reviews/", json={
        "order": conv_order_id,
        "rating": 4,
        "comment": "Duplicate attempt"
    }, headers={"Authorization": f"Bearer {p9_buyer_token}"})
    assert_true(r_rev_dup.status_code == 400, "Duplicate review on same order blocked with 400")

    # G.4 Favorites toggle
    r_fav_on = requests.post(f"{API_URL}favorites/toggle/", json={"crop_id": p9_crop_id}, headers={"Authorization": f"Bearer {p9_buyer_token}"})
    assert_true(r_fav_on.status_code in [200, 201] and r_fav_on.json()["is_favorited"] is True, "Crop bookmarked to favorites")

    r_fav_off = requests.post(f"{API_URL}favorites/toggle/", json={"crop_id": p9_crop_id}, headers={"Authorization": f"Bearer {p9_buyer_token}"})
    assert_true(r_fav_off.status_code == 200 and r_fav_off.json()["is_favorited"] is False, "Crop un-bookmarked from favorites")


    print("\n--- H. TESTING ADMIN GOVERNANCE, RBAC & SECURITY ---")
    # H.1 Non-admin access to /api/users/ blocked
    r_adm_u_block = requests.get(f"{API_URL}users/", headers={"Authorization": f"Bearer {p9_buyer_token}"})
    assert_true(r_adm_u_block.status_code == 403, "Non-admin blocked from /api/users/ (403)")

    # H.2 Admin accesses /api/users/
    r_adm_u = requests.get(f"{API_URL}users/", headers={"Authorization": f"Bearer {admin_token}"})
    assert_true(r_adm_u.status_code == 200, "Admin accessed /api/users/ (200)")

    # H.3 Admin toggles KYC verification
    r_kyc = requests.post(f"{API_URL}users/{p9_farmer_id}/toggle_verify/", headers={"Authorization": f"Bearer {admin_token}"})
    assert_true(r_kyc.status_code == 200 and r_kyc.json()["is_verified"] is True, "Admin verified farmer KYC")

    # H.4 Category cascade protection: cannot delete category with active crops
    r_cat_del_guard = requests.delete(f"{API_URL}categories/{cat_grains.slug}/", headers={"Authorization": f"Bearer {admin_token}"})
    assert_true(r_cat_del_guard.status_code == 400, "Category with active crops cannot be deleted (cascade guard 400)")

    # H.5 Admin creates and deletes empty category
    r_cat_new = requests.post(f"{API_URL}categories/", json={"name": "P9 Temp Category", "description": "Temp"}, headers={"Authorization": f"Bearer {admin_token}"})
    assert_true(r_cat_new.status_code == 201, "Admin created category (201)")
    p9_cat_slug = r_cat_new.json()["slug"]
    r_cat_del = requests.delete(f"{API_URL}categories/{p9_cat_slug}/", headers={"Authorization": f"Bearer {admin_token}"})
    assert_true(r_cat_del.status_code == 204, "Admin deleted empty category (204)")

    # H.6 Non-admin blocked from admin analytics
    r_ana_block = requests.get(f"{API_URL}analytics/admin/", headers={"Authorization": f"Bearer {p9_farmer_token}"})
    assert_true(r_ana_block.status_code == 403, "Non-admin blocked from admin analytics (403)")

    # H.7 Admin analytics endpoint returns real database aggregations
    r_ana_adm = requests.get(f"{API_URL}analytics/admin/", headers={"Authorization": f"Bearer {admin_token}"})
    assert_true(r_ana_adm.status_code == 200 and "financial_summary" in r_ana_adm.json(), "Admin analytics returns valid database aggregations (200)")

    # H.8 Sensitive Data Exposure Check: public crop detail must NOT leak farmer email or phone
    r_pub_crop = requests.get(f"{API_URL}crops/{p9_crop_id}/")
    crop_data = r_pub_crop.json()
    assert_true("farmer_email" not in crop_data and "farmer_phone" not in crop_data, "Public crop detail does not leak farmer email or phone")

finally:
    print("\n--- I. CLEANING UP TEST ARTIFACTS (PRESERVING BASELINE) ---")
    Review.objects.filter(id__in=created_review_ids).delete()
    TransportRequest.objects.filter(order_id__in=created_order_ids).delete()
    PriceNegotiation.objects.filter(id__in=created_neg_ids).delete()
    Order.objects.filter(id__in=created_order_ids).delete()
    Crop.objects.filter(id__in=created_crop_ids).delete()
    User.objects.filter(id__in=created_user_ids).delete()

final_counts = get_counts()
print(f"=== Final Database Counts: {final_counts} ===")

for k in initial_counts:
    assert_true(initial_counts[k] == final_counts[k], f"DB count for '{k}' preserved: {initial_counts[k]} == {final_counts[k]}")

if errors:
    print(f"\n❌ PHASE 9 TEST SUITE FAILED with {len(errors)} issues:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("\n🎉 ALL PHASE 9 COMPREHENSIVE END-TO-END & SECURITY CHECKS PASSED (100%)!")
    sys.exit(0)
