import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import django
import requests

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.accounts.models import User, FarmerProfile, BuyerProfile, TransporterProfile
from apps.crops.models import Category, Crop, MandiPrice
from apps.orders.models import Order, OrderItem, Payment, PriceNegotiation
from apps.reviews.models import Review
from apps.logistics.models import TransportRequest

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

initial_counts = get_counts()
print(f"Initial DB Counts: {initial_counts}")

errors = []

def assert_true(cond, msg):
    if not cond:
        print(f"❌ FAIL: {msg}")
        errors.append(msg)
    else:
        print(f"✅ PASS: {msg}")

# --- Test 1: Role-Based Registration & Profile Validation ---
farmer_payload = {
    "username": "temp_verify_farmer",
    "email": "temp_farmer@farmconnect.test",
    "password": "StrongPassword123!",
    "password_confirm": "StrongPassword123!",
    "role": "farmer",
    "phone": "+919876543210",
    "farm_name": "Sunrise Agro Farms",
    "farm_size_acres": 15.5
}
buyer_payload = {
    "username": "temp_verify_buyer",
    "email": "temp_buyer@farmconnect.test",
    "password": "StrongPassword123!",
    "password_confirm": "StrongPassword123!",
    "role": "buyer",
    "phone": "+919876543211",
    "business_name": "Sunrise Fresh Markets",
    "buyer_type": "wholesaler"
}
trans_payload = {
    "username": "temp_verify_trans",
    "email": "temp_trans@farmconnect.test",
    "password": "StrongPassword123!",
    "password_confirm": "StrongPassword123!",
    "role": "transporter",
    "phone": "+919876543212",
    "vehicle_type": "truck_multi_axle",
    "vehicle_number": "MH-15-TR-9999",
    "max_capacity_tons": 18.0
}

# 1.1 Farmer Registration & Login
r = requests.post(f"{API_URL}auth/register/", json=farmer_payload)
farmer_data = r.json()
assert_true(r.status_code == 201, f"Farmer registration status 201 (got {r.status_code})")
assert_true("farmer_profile" in farmer_data and farmer_data["farmer_profile"]["farm_name"] == "Sunrise Agro Farms", "FarmerProfile correctly saved with farm_name")

r_login = requests.post(f"{API_URL}auth/login/", json={"username": "temp_verify_farmer", "password": "StrongPassword123!"})
assert_true(r_login.status_code == 200, "Farmer login returns 200 with tokens")
farmer_tokens = r_login.json()
assert_true("access" in farmer_tokens and "refresh" in farmer_tokens, "Farmer login returned access and refresh tokens")

# 1.2 Buyer Registration & Login
r = requests.post(f"{API_URL}auth/register/", json=buyer_payload)
assert_true(r.status_code == 201, f"Buyer registration status 201 (got {r.status_code})")
buyer_data = r.json()
assert_true("buyer_profile" in buyer_data and buyer_data["buyer_profile"]["business_name"] == "Sunrise Fresh Markets", "BuyerProfile correctly saved with business_name")

r_login = requests.post(f"{API_URL}auth/login/", json={"username": "temp_verify_buyer", "password": "StrongPassword123!"})
assert_true(r_login.status_code == 200, "Buyer login returns 200 with tokens")
buyer_tokens = r_login.json()

# 1.3 Transporter Registration & Login
r = requests.post(f"{API_URL}auth/register/", json=trans_payload)
assert_true(r.status_code == 201, f"Transporter registration status 201 (got {r.status_code})")
trans_data = r.json()
assert_true("transporter_profile" in trans_data and trans_data["transporter_profile"]["vehicle_number"] == "MH-15-TR-9999", "TransporterProfile correctly saved with vehicle_number")

r_login = requests.post(f"{API_URL}auth/login/", json={"username": "temp_verify_trans", "password": "StrongPassword123!"})
assert_true(r_login.status_code == 200, "Transporter login returns 200 with tokens")
trans_tokens = r_login.json()

# --- Test 2: JWT Session & Token Rotation Verification ---
# 2.1 Access profile with valid access token
headers = {"Authorization": f"Bearer {farmer_tokens['access']}"}
r_prof = requests.get(f"{API_URL}auth/profile/", headers=headers)
assert_true(r_prof.status_code == 200 and r_prof.json()["username"] == "temp_verify_farmer", "Valid access token accesses profile")

# 2.2 Access profile with invalid token -> 401
r_inv = requests.get(f"{API_URL}auth/profile/", headers={"Authorization": "Bearer invalid_token_12345"})
assert_true(r_inv.status_code == 401, "Invalid access token rejected with HTTP 401")

# 2.3 Token refresh
r_ref = requests.post(f"{API_URL}auth/token/refresh/", json={"refresh": farmer_tokens["refresh"]})
assert_true(r_ref.status_code == 200 and "access" in r_ref.json(), "Token refresh returns new access token")
new_access = r_ref.json()["access"]

# 2.4 New access token works
r_prof_new = requests.get(f"{API_URL}auth/profile/", headers={"Authorization": f"Bearer {new_access}"})
assert_true(r_prof_new.status_code == 200, "Rotated access token accesses profile")

# 2.5 Invalid refresh token rejected
r_ref_inv = requests.post(f"{API_URL}auth/token/refresh/", json={"refresh": "invalid_refresh_xyz"})
assert_true(r_ref_inv.status_code == 401, "Invalid refresh token rejected with HTTP 401")

# --- Test 3: Public Crop API Privacy Verification ---
r_crop = requests.get(f"{API_URL}crops/1/")
assert_true(r_crop.status_code == 200, "Public crop detail endpoint returns 200")
crop_detail = r_crop.json()
farmer_info = crop_detail.get("farmer_info", {})
assert_true("email" not in farmer_info, "Farmer email is NOT exposed in public crop API")
assert_true("phone" not in farmer_info, "Farmer phone is NOT exposed in public crop API")
assert_true("phone_number" not in farmer_info, "Farmer phone_number is NOT exposed in public crop API")

# Check required model fields on CropDetail
for field in ['crop_name', 'variety', 'category', 'grade_quality', 'price_per_unit', 'unit', 'quantity_available', 'minimum_order_quantity', 'location']:
    assert_true(field in crop_detail, f"Crop detail includes '{field}'")

# --- Test 4: Pagination Verification (Backend-Side) ---
# Query with page_size=2
r_page1 = requests.get(f"{API_URL}crops/?page=1&page_size=2")
assert_true(r_page1.status_code == 200, "Crops pagination page 1 returns 200")
data_page1 = r_page1.json()
assert_true(data_page1["count"] == 4, f"Total count is 4 (got {data_page1['count']})")
assert_true(len(data_page1["results"]) == 2, f"Page 1 returns exactly 2 items (got {len(data_page1['results'])})")
assert_true(data_page1["next"] is not None, "Page 1 next link is present")
assert_true(data_page1["previous"] is None, "Page 1 previous link is null")
page1_ids = [c["id"] for c in data_page1["results"]]

# Query page 2
r_page2 = requests.get(f"{API_URL}crops/?page=2&page_size=2")
assert_true(r_page2.status_code == 200, "Crops pagination page 2 returns 200")
data_page2 = r_page2.json()
assert_true(len(data_page2["results"]) == 2, f"Page 2 returns exactly 2 items (got {len(data_page2['results'])})")
assert_true(data_page2["next"] is None, "Page 2 next link is null (last page)")
assert_true(data_page2["previous"] is not None, "Page 2 previous link is present")
page2_ids = [c["id"] for c in data_page2["results"]]

# Verify no overlap
assert_true(set(page1_ids).isdisjoint(set(page2_ids)), f"Page 1 and Page 2 records are distinct: {page1_ids} vs {page2_ids}")

# Category filter with pagination
r_cat = requests.get(f"{API_URL}crops/?category=vegetables&page=1&page_size=1")
assert_true(r_cat.status_code == 200, "Category filter with pagination returns 200")
data_cat = r_cat.json()
assert_true(data_cat["count"] == 2, f"Vegetables count is 2 (got {data_cat['count']})")
assert_true(len(data_cat["results"]) == 1, "Page 1 of vegetables with page_size=1 returns 1 item")

# --- Cleanup Test Accounts ---
User.objects.filter(username__startswith="temp_verify_").delete()
final_counts = get_counts()
print(f"Final DB Counts: {final_counts}")

for k in initial_counts:
    assert_true(initial_counts[k] == final_counts[k], f"DB count for '{k}' preserved: {initial_counts[k]} == {final_counts[k]}")

if errors:
    print(f"\n❌ FAILED with {len(errors)} errors:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("\n🎉 ALL PHASE 7 FINAL VERIFICATION TESTS PASSED SUCCESSFULLY!")
    sys.exit(0)
