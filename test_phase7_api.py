import urllib.request
import urllib.error
import json
import time

BASE_URL = "http://127.0.0.1:8000/api/"

def request(method, endpoint, data=None, token=None):
    url = BASE_URL + endpoint
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.getcode()
            res_body = resp.read().decode("utf-8")
            return status, json.loads(res_body) if res_body else {}
    except urllib.error.HTTPError as e:
        res_body = e.read().decode("utf-8")
        try:
            parsed = json.loads(res_body)
        except Exception:
            parsed = res_body
        return e.code, parsed
    except Exception as e:
        return 0, str(e)

print("=" * 70)
print(" FarmConnect - Phase 7 Live Django API Integration Suite")
print("=" * 70)

# 1. Health check
status, health = request("GET", "health/")
print(f"[TEST 1] Backend Health Check: HTTP {status} -> {health}")
assert status == 200 and health.get("database") == "ok", "Database connection unhealthy"

# 2. Farmer registration
farmer_payload = {
    "username": "phase7_temp_farmer",
    "email": "temp_farmer@farmconnect.org",
    "password": "FarmPassword123!",
    "password_confirm": "FarmPassword123!",
    "first_name": "Kailash",
    "last_name": "Patil",
    "role": "farmer",
    "phone": "9822001122",
    "full_name": "Kailash Patil",
    "city": "Nashik",
    "state": "Maharashtra",
    "farm_name": "Kailash Agro Orchards",
    "farm_size_acres": 12.5
}
status, reg_farmer = request("POST", "auth/register/", farmer_payload)
print(f"[TEST 2] Farmer Registration: HTTP {status} -> User ID {reg_farmer.get('id')}, Role={reg_farmer.get('role')}")
assert status == 201, f"Farmer registration failed: {reg_farmer}"

# 3. Buyer registration
buyer_payload = {
    "username": "phase7_temp_buyer",
    "email": "temp_buyer@farmconnect.org",
    "password": "BuyerPassword123!",
    "password_confirm": "BuyerPassword123!",
    "first_name": "Manish",
    "last_name": "Gupta",
    "role": "buyer",
    "phone": "9822003344",
    "full_name": "Manish Gupta",
    "city": "Mumbai",
    "state": "Maharashtra",
    "business_name": "Gupta Wholesale Mart",
    "buyer_type": "wholesaler",
    "gst_number": "27AAAAA0000A1Z5"
}
status, reg_buyer = request("POST", "auth/register/", buyer_payload)
print(f"[TEST 3] Buyer Registration: HTTP {status} -> User ID {reg_buyer.get('id')}, Role={reg_buyer.get('role')}")
assert status == 201, f"Buyer registration failed: {reg_buyer}"

# 4. Transporter registration
trans_payload = {
    "username": "phase7_temp_trans",
    "email": "temp_trans@farmconnect.org",
    "password": "TransPassword123!",
    "password_confirm": "TransPassword123!",
    "first_name": "Jagdish",
    "last_name": "Yadav",
    "role": "transporter",
    "phone": "9822005566",
    "full_name": "Jagdish Yadav",
    "city": "Pune",
    "state": "Maharashtra",
    "vehicle_type": "Commercial Truck (10-Wheel)",
    "vehicle_number": "MH-12-PQ-9988",
    "max_capacity_tons": 16.0
}
status, reg_trans = request("POST", "auth/register/", trans_payload)
print(f"[TEST 4] Transporter Registration: HTTP {status} -> User ID {reg_trans.get('id')}, Role={reg_trans.get('role')}")
assert status == 201, f"Transporter registration failed: {reg_trans}"

# 5. Valid Login
login_payload = {
    "username": "phase7_temp_farmer",
    "password": "FarmPassword123!"
}
status, login_res = request("POST", "auth/login/", login_payload)
print(f"[TEST 5] Valid Login: HTTP {status} -> Access Token Received, User={login_res.get('user', {}).get('username')}, Role={login_res.get('user', {}).get('role')}")
assert status == 200 and "access" in login_res, f"Valid login failed: {login_res}"
access_token = login_res["access"]
refresh_token = login_res["refresh"]

# 6. Invalid Login
status, bad_login = request("POST", "auth/login/", {"username": "phase7_temp_farmer", "password": "WrongPassword999!"})
print(f"[TEST 6] Invalid Login: HTTP {status} -> {bad_login.get('detail', bad_login)}")
assert status == 401, f"Expected 401 for invalid login, got {status}"

# 7. JWT Token Refresh
status, refresh_res = request("POST", "auth/token/refresh/", {"refresh": refresh_token})
print(f"[TEST 7] Token Refresh: HTTP {status} -> New Access Token Generated")
assert status == 200 and "access" in refresh_res, f"Token refresh failed: {refresh_res}"
new_access_token = refresh_res["access"]

# 8. Authenticated Profile Fetch
status, profile = request("GET", "auth/profile/", token=new_access_token)
print(f"[TEST 8] Authenticated Profile Retrieval: HTTP {status} -> {profile.get('username')} ({profile.get('role')})")
assert status == 200 and profile.get("username") == "phase7_temp_farmer", "Profile retrieval mismatch"

# 9. Role Profile Retrieval & Verification
farmer_prof = profile.get("farmer_profile", {})
print(f"  Farmer Profile Data in MySQL: farm_name='{farmer_prof.get('farm_name')}', acres={farmer_prof.get('farm_size_acres')}")
assert farmer_prof.get("farm_name") == "Kailash Agro Orchards", f"FarmerProfile mismatch: {farmer_prof}"

# 10. Public Category Listing
status, categories = request("GET", "categories/")
print(f"[TEST 10] Categories API: HTTP {status} -> Total {len(categories)} categories")
assert status == 200 and len(categories) >= 6, f"Categories failed: {categories}"

# 11. Public Crop Listing
status, crops_res = request("GET", "crops/")
print(f"[TEST 11] Crops Catalog API: HTTP {status} -> Total {crops_res.get('count')} crops available")
assert status == 200 and crops_res.get("count") >= 4, f"Crops catalog failed: {crops_res}"

# 12. Search & Category Filter
status, filtered_crops = request("GET", "crops/?category=pulses-legumes")
print(f"[TEST 12] Category Filter (?category=pulses-legumes): HTTP {status} -> {filtered_crops.get('count')} results")
assert status == 200 and filtered_crops.get("count") >= 1, "Category filter returned no crops"

# 13. Single Crop Details
crop_id = crops_res["results"][0]["id"]
status, crop_detail = request("GET", f"crops/{crop_id}/")
print(f"[TEST 13] Single Crop Detail (ID={crop_id}): HTTP {status} -> Name: '{crop_detail.get('crop_name')}', Farmer: '{crop_detail.get('farmer_info', {}).get('farm_name')}'")
assert status == 200 and crop_detail.get("crop_name"), f"Crop detail failed: {crop_detail}"

# 14. Mandi Price Benchmarks
status, mandi_res = request("GET", "mandi-prices/")
print(f"[TEST 14] Mandi Price Benchmarks: HTTP {status} -> Total {mandi_res.get('count')} benchmarks in database")
assert status == 200 and mandi_res.get("count") >= 17, f"Mandi prices failed: {mandi_res}"

# 15. Cross-Mandi Price Comparison
status, compare_res = request("GET", "mandi-prices/compare/?crop=Onion")
print(f"[TEST 15] Mandi Compare (?crop=Onion): HTTP {status} -> {compare_res.get('total_records')} comparative records for '{compare_res.get('commodity')}'")
assert status == 200 and compare_res.get("total_records") >= 1, "Mandi compare returned no records"

# 16. Clean up temporary test users created in this test run
print("\n[CLEANUP] Removing temporary test users created during Phase 7 testing...")
import os, sys, django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
temp_usernames = ["phase7_temp_farmer", "phase7_temp_buyer", "phase7_temp_trans"]
deleted_count = User.objects.filter(username__in=temp_usernames).delete()
print(f"  Successfully deleted {deleted_count[0]} items related to temporary test accounts.")
remaining = User.objects.count()
print(f"  Remaining persistent user accounts in MySQL: {remaining}")
assert remaining == 5, f"Expected 5 persistent users, found {remaining}"

print("=" * 70)
print(" ALL 15 PHASE 7 API INTEGRATION TESTS PASSED SUCCESSFULLY! ")
print("=" * 70)
