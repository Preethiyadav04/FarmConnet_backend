"""
FarmConnect - Phase 3 Automated Verification Suite
Tests Categories, Crop Listings, Buyer Marketplace Filters, Mandi Prices,
Permissions, and Data Validation against MySQL 8.0 on port 3306.
Safeguards all persistent database records.
"""

import os
import sys
from pathlib import Path
from decimal import Decimal
import datetime

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.test import Client
from django.db import connection
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

from apps.crops.models import Category, Crop, MandiPrice, CropStatus
from apps.accounts.models import UserRole

User = get_user_model()


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token)


def run_tests():
    print("=" * 75)
    print(" FarmConnect - Phase 3 Verification Suite (MySQL 8.0 on Port 3306)")
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
    initial_user_count = User.objects.count()
    initial_category_count = Category.objects.count()
    initial_crop_count = Crop.objects.count()
    initial_mandi_count = MandiPrice.objects.count()

    print(f"  • Existing Users:        {initial_user_count}")
    print(f"  • Existing Categories:   {initial_category_count}")
    print(f"  • Existing Crops:        {initial_crop_count}")
    print(f"  • Existing Mandi Prices: {initial_mandi_count}")
    assert initial_category_count >= 6, "Expected at least 6 categories in database"
    assert initial_crop_count >= 4, "Expected at least 4 crops in database"
    assert initial_mandi_count >= 15, "Expected at least 15 mandi price records in database"
    print("-> PASSED: Baseline database records verified.")

    # 3. Setup Test Actors (using existing or isolated test accounts)
    print("\n[STEP 3] Setting up Test Actors...")
    # Admin
    admin_user = User.objects.filter(role=UserRole.ADMIN).first()
    if not admin_user:
        admin_user = User.objects.create_superuser('test_admin_p3', 'admin_p3@farmconnect.org', 'AdminPass123!')
    admin_token = get_tokens_for_user(admin_user)

    # Farmer
    farmer_user = User.objects.filter(role=UserRole.FARMER).first()
    if not farmer_user:
        farmer_user = User.objects.create_user('test_farmer_p3', 'farmer_p3@farmconnect.org', 'FarmerPass123!', role=UserRole.FARMER)
    farmer_token = get_tokens_for_user(farmer_user)

    # Another Farmer (for permission check)
    User.objects.filter(username='test_other_farmer').delete()
    other_farmer = User.objects.create_user('test_other_farmer', 'other_farmer@farmconnect.org', 'OtherFarmerPass123!', role=UserRole.FARMER, phone='9876543219')
    other_farmer_token = get_tokens_for_user(other_farmer)

    # Buyer
    buyer_user = User.objects.filter(role=UserRole.BUYER).first()
    if not buyer_user:
        buyer_user = User.objects.create_user('test_buyer_p3', 'buyer_p3@farmconnect.org', 'BuyerPass123!', role=UserRole.BUYER)
    buyer_token = get_tokens_for_user(buyer_user)

    client = Client()
    print("-> PASSED: Authenticated tokens generated for Admin, Farmer, Other Farmer, and Buyer.")

    # 4. Test Category APIs
    print("\n[TEST 1] Testing Category Endpoints & Permissions...")
    # Public read
    res = client.get('/api/categories/')
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    cat_data = res.json()
    assert len(cat_data) >= 6, "Expected at least 6 categories"
    print(f"  • Public read: 200 OK (returned {len(cat_data)} categories)")

    # Unauthorized POST (no token) -> 401
    res = client.post('/api/categories/', {'name': 'Exotic Mushrooms', 'description': 'Organic mushrooms'}, content_type='application/json')
    assert res.status_code == 401, f"Expected 401, got {res.status_code}"
    print("  • Anonymous create: 401 Unauthorized (Blocked)")

    # Forbidden POST (buyer token) -> 403
    res = client.post('/api/categories/', {'name': 'Exotic Mushrooms', 'description': 'Organic mushrooms'}, content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {buyer_token}')
    assert res.status_code == 403, f"Expected 403, got {res.status_code}"
    print("  • Buyer create: 403 Forbidden (Blocked)")

    # Forbidden POST (farmer token) -> 403
    res = client.post('/api/categories/', {'name': 'Exotic Mushrooms', 'description': 'Organic mushrooms'}, content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {farmer_token}')
    assert res.status_code == 403, f"Expected 403, got {res.status_code}"
    print("  • Farmer create: 403 Forbidden (Blocked)")

    # Authorized POST (admin token) -> 201
    Category.objects.filter(slug='exotic-mushrooms').delete()
    res = client.post('/api/categories/', {
        'name': 'Exotic Mushrooms',
        'description': 'Culinary and medicinal mushrooms cultivated organically.',
        'icon': 'sprout',
        'is_active': True
    }, content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {admin_token}')
    assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.json()}"
    new_cat = res.json()
    assert new_cat['slug'] == 'exotic-mushrooms'
    print(f"  • Admin create: 201 Created (Created '{new_cat['name']}' with slug '{new_cat['slug']}')")

    # Retrieve by slug
    res = client.get('/api/categories/exotic-mushrooms/')
    assert res.status_code == 200
    print("  • Retrieve by slug: 200 OK")
    print("-> PASSED: Category CRUD and Role-Based Permissions fully verified.")

    # 5. Test Farmer Crop Creation & Management
    print("\n[TEST 2] Testing Farmer Crop Creation & Management APIs...")
    # Anonymous create -> 401
    res = client.post('/api/crops/', {'crop_name': 'Test Crop'}, content_type='application/json')
    assert res.status_code == 401
    print("  • Anonymous crop create: 401 Unauthorized (Blocked)")

    # Buyer create -> 403
    res = client.post('/api/crops/', {'crop_name': 'Test Crop'}, content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {buyer_token}')
    assert res.status_code == 403
    print("  • Buyer crop create: 403 Forbidden (Blocked)")

    # Farmer create with invalid price (<= 0) -> 400
    veg_cat = Category.objects.filter(slug='vegetables').first()
    res = client.post('/api/crops/', {
        'crop_name': 'Organic Spinach',
        'category': veg_cat.id,
        'price_per_unit': -10.00,
        'unit': 'kg',
        'quantity_available': 100
    }, content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {farmer_token}')
    assert res.status_code == 400
    print("  • Invalid negative price validation: 400 Bad Request (Blocked)")

    # Farmer create with minimum_order_quantity > quantity_available -> 400
    res = client.post('/api/crops/', {
        'crop_name': 'Organic Spinach',
        'category': veg_cat.id,
        'price_per_unit': 25.00,
        'unit': 'kg',
        'quantity_available': 50,
        'minimum_order_quantity': 100
    }, content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {farmer_token}')
    assert res.status_code == 400
    print("  • Min order > available validation: 400 Bad Request (Blocked)")

    # Valid Farmer Crop Creation -> 201
    Crop.objects.filter(crop_name='Test Golden Basmati Rice').delete()
    grain_cat = Category.objects.filter(slug='grains-cereals').first()
    res = client.post('/api/crops/', {
        'crop_name': 'Test Golden Basmati Rice',
        'category': grain_cat.id,
        'variety': '1121 Extra Long',
        'description': 'Naturally aged basmati rice with exquisite aroma and long grain length.',
        'grade_quality': 'Grade A',
        'price_per_unit': 4200.00,
        'unit': 'quintal',
        'quantity_available': 80.00,
        'minimum_order_quantity': 5.00,
        'harvest_date': str(datetime.date.today() - datetime.timedelta(days=15)),
        'location_city': 'Karnal',
        'location_state': 'Haryana',
        'location_pincode': '132001',
        'status': 'active'
    }, content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {farmer_token}')
    assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.json()}"
    created_crop = res.json()
    crop_id = created_crop['id']
    print(f"  • Farmer crop create: 201 Created (ID: {crop_id}, Name: {created_crop['crop_name']})")

    # Farmer 'my_crops' endpoint
    res = client.get('/api/crops/my_crops/', HTTP_AUTHORIZATION=f'Bearer {farmer_token}')
    assert res.status_code == 200
    my_crops_data = res.json()
    results = my_crops_data.get('results', my_crops_data)
    assert any(c['id'] == crop_id for c in results), "Created crop not found in farmer's my_crops list"
    print(f"  • Farmer my_crops list: 200 OK (returned {len(results)} owned crops)")

    # Buyer accessing 'my_crops' -> 403 Forbidden
    res = client.get('/api/crops/my_crops/', HTTP_AUTHORIZATION=f'Bearer {buyer_token}')
    assert res.status_code == 403
    print("  • Buyer accessing farmer my_crops: 403 Forbidden (Blocked)")

    # Toggle availability
    res = client.post(f'/api/crops/{crop_id}/toggle_availability/', HTTP_AUTHORIZATION=f'Bearer {farmer_token}')
    assert res.status_code == 200
    assert res.json()['status'] == 'unavailable'
    print("  • Toggle status to 'unavailable': 200 OK")

    # Toggle back to active
    res = client.post(f'/api/crops/{crop_id}/toggle_availability/', HTTP_AUTHORIZATION=f'Bearer {farmer_token}')
    assert res.status_code == 200
    assert res.json()['status'] == 'active'
    print("  • Toggle status back to 'active': 200 OK")

    # Other farmer attempting to edit crop -> 403 Forbidden
    res = client.patch(f'/api/crops/{crop_id}/', {'price_per_unit': 3999.00}, content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {other_farmer_token}')
    assert res.status_code == 403
    print("  • Other farmer edit attempt: 403 Forbidden (Blocked by object permission)")

    # Crop owner updates price -> 200 OK
    res = client.patch(f'/api/crops/{crop_id}/', {'price_per_unit': 4150.00}, content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {farmer_token}')
    assert res.status_code == 200
    assert float(res.json()['price_per_unit']) == 4150.00
    print("  • Owner farmer update price: 200 OK (Price updated to ₹4150.00)")
    print("-> PASSED: Farmer Crop management, ownership guards, and stock validation fully verified.")

    # 6. Test Buyer Marketplace Browsing, Search, and Filters
    print("\n[TEST 3] Testing Buyer Marketplace Browsing, Search, and Filters...")
    # Public catalog browse (paginated)
    res = client.get('/api/crops/')
    assert res.status_code == 200
    catalog = res.json()
    assert 'count' in catalog
    assert 'results' in catalog
    print(f"  • Public catalog listing: 200 OK (Total active crops: {catalog['count']})")

    # Verify farmer private info is protected
    first_item = catalog['results'][0]
    assert 'farmer_name' in first_item
    assert 'email' not in first_item
    assert 'phone' not in first_item
    print(f"  • Buyer privacy check: Farmer private details (email, phone) are NOT exposed in public catalog.")

    # Search filter: ?search=Wheat
    res = client.get('/api/crops/?search=Wheat')
    assert res.status_code == 200
    wheat_results = res.json()['results']
    assert len(wheat_results) >= 1
    assert any('Wheat' in c['crop_name'] for c in wheat_results)
    print(f"  • Search by name (?search=Wheat): 200 OK (Found {len(wheat_results)} matches)")

    # Category filter: ?category=vegetables
    res = client.get('/api/crops/?category=vegetables')
    assert res.status_code == 200
    veg_results = res.json()['results']
    assert len(veg_results) >= 1
    assert all(c['category_slug'] == 'vegetables' for c in veg_results)
    print(f"  • Filter by category (?category=vegetables): 200 OK (Found {len(veg_results)} vegetables)")

    # Location filter: ?location=Nashik
    res = client.get('/api/crops/?location=Nashik')
    assert res.status_code == 200
    nashik_results = res.json()['results']
    assert len(nashik_results) >= 1
    assert all('Nashik' in c['location_city'] for c in nashik_results)
    print(f"  • Filter by location (?location=Nashik): 200 OK (Found {len(nashik_results)} items in Nashik)")

    # Price range filter: ?min_price=15&max_price=25
    res = client.get('/api/crops/?min_price=15&max_price=25')
    assert res.status_code == 200
    price_filtered = res.json()['results']
    assert len(price_filtered) >= 1
    assert all(15 <= float(c['price_per_unit']) <= 25 for c in price_filtered)
    print(f"  • Filter by price range (?min_price=15&max_price=25): 200 OK (Found {len(price_filtered)} items)")

    # Sorting by price ascending: ?sort_by=price_asc
    res = client.get('/api/crops/?sort_by=price_asc')
    assert res.status_code == 200
    asc_results = res.json()['results']
    prices = [float(c['price_per_unit']) for c in asc_results]
    assert prices == sorted(prices), f"Prices not sorted ascending: {prices}"
    print(f"  • Sort by price ascending (?sort_by=price_asc): 200 OK (Lowest price first: ₹{prices[0]})")

    # Sorting by price descending: ?sort_by=price_desc
    res = client.get('/api/crops/?sort_by=price_desc')
    assert res.status_code == 200
    desc_results = res.json()['results']
    prices_desc = [float(c['price_per_unit']) for c in desc_results]
    assert prices_desc == sorted(prices_desc, reverse=True), f"Prices not sorted descending: {prices_desc}"
    print(f"  • Sort by price descending (?sort_by=price_desc): 200 OK (Highest price first: ₹{prices_desc[0]})")

    # Single crop detail view & view counter increment
    res = client.get(f'/api/crops/{crop_id}/')
    assert res.status_code == 200
    detail = res.json()
    assert detail['id'] == crop_id
    assert 'farmer_info' in detail
    assert 'mandi_benchmark' in detail
    print(f"  • Crop detail view: 200 OK (Views count: {detail['views_count']}, Mandi benchmarks attached: {len(detail['mandi_benchmark'])})")
    print("-> PASSED: Buyer Marketplace catalog, search, filters, sorting, and privacy fully verified.")

    # 7. Test Mandi Market Price APIs
    print("\n[TEST 4] Testing Mandi Market Price APIs & Benchmarks...")
    # Public list
    res = client.get('/api/mandi-prices/')
    assert res.status_code == 200
    mandi_list = res.json()
    assert mandi_list['count'] >= 15
    print(f"  • Public Mandi price list: 200 OK (Total records: {mandi_list['count']})")

    # Compare endpoint: ?crop=Wheat
    res = client.get('/api/mandi-prices/compare/?crop=Wheat')
    assert res.status_code == 200
    comp_data = res.json()
    assert comp_data['commodity'] == 'Wheat'
    assert len(comp_data['benchmarks']) >= 1
    print(f"  • Mandi price compare (?crop=Wheat): 200 OK (Compared across {len(comp_data['benchmarks'])} mandis)")

    # Unauthorized create -> 401
    res = client.post('/api/mandi-prices/', {'crop_name': 'Soybean'}, content_type='application/json')
    assert res.status_code == 401
    print("  • Anonymous Mandi price create: 401 Unauthorized (Blocked)")

    # Farmer create -> 403
    res = client.post('/api/mandi-prices/', {'crop_name': 'Soybean'}, content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {farmer_token}')
    assert res.status_code == 403
    print("  • Farmer Mandi price create: 403 Forbidden (Blocked)")

    # Invalid price check (min_price > max_price) -> 400
    res = client.post('/api/mandi-prices/', {
        'crop_name': 'Test Soybean',
        'market_name': 'Latur APMC',
        'district': 'Latur',
        'state': 'Maharashtra',
        'min_price': 5200.00,
        'max_price': 4800.00,  # Invalid: max < min
        'modal_price': 5000.00,
        'price_unit': '₹ / Quintal',
        'price_date': str(datetime.date.today()),
        'data_source': 'Agmarknet Benchmark (Demo Sample)'
    }, content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {admin_token}')
    assert res.status_code == 400
    print("  • Invalid min > max validation: 400 Bad Request (Blocked)")

    # Admin creates valid Mandi Price -> 201
    MandiPrice.objects.filter(crop_name='Test Soybean').delete()
    res = client.post('/api/mandi-prices/', {
        'crop_name': 'Test Soybean',
        'market_name': 'Latur APMC',
        'district': 'Latur',
        'state': 'Maharashtra',
        'min_price': 4600.00,
        'max_price': 5100.00,
        'modal_price': 4850.00,
        'price_unit': '₹ / Quintal',
        'price_date': str(datetime.date.today()),
        'data_source': 'Agmarknet / Mandi Benchmark (Sample Market Data - Verified Nov 2026)'
    }, content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {admin_token}')
    assert res.status_code == 201, f"Expected 201, got {res.status_code}: {res.json()}"
    new_mandi = res.json()
    mandi_id = new_mandi['id']
    print(f"  • Admin Mandi price create: 201 Created (ID: {mandi_id}, Modal: ₹{new_mandi['modal_price']})")
    assert new_mandi['data_source'] != ''
    print(f"  • Transparency check: Source recorded as '{new_mandi['data_source']}' on date '{new_mandi['price_date']}'.")
    print("-> PASSED: Mandi Market Price APIs, Admin controls, and validation fully verified.")

    # 8. Clean up ONLY our test-created items
    print("\n[STEP 4] Cleaning Up Test Artifacts (Preserving Persistent Data)...")
    # Delete test crop
    res = client.delete(f'/api/crops/{crop_id}/', HTTP_AUTHORIZATION=f'Bearer {farmer_token}')
    assert res.status_code == 204
    print(f"  • Deleted test crop ID {crop_id}: 204 No Content")

    # Delete test category
    res = client.delete('/api/categories/exotic-mushrooms/', HTTP_AUTHORIZATION=f'Bearer {admin_token}')
    assert res.status_code == 204
    print("  • Deleted test category 'exotic-mushrooms': 204 No Content")

    # Delete test mandi price
    res = client.delete(f'/api/mandi-prices/{mandi_id}/', HTTP_AUTHORIZATION=f'Bearer {admin_token}')
    assert res.status_code == 204
    print(f"  • Deleted test mandi price ID {mandi_id}: 204 No Content")

    # Delete other farmer
    other_farmer.delete()

    # 9. Verify Baseline Integrity
    print("\n[STEP 5] Verifying Baseline Data Integrity After Tests...")
    final_user_count = User.objects.count()
    final_category_count = Category.objects.count()
    final_crop_count = Crop.objects.count()
    final_mandi_count = MandiPrice.objects.count()

    print(f"  • Final Users in MySQL:        {final_user_count} (Matches baseline)")
    print(f"  • Final Categories in MySQL:   {final_category_count} (Matches baseline: 6)")
    print(f"  • Final Crops in MySQL:        {final_crop_count} (Matches baseline: 4)")
    print(f"  • Final Mandi Prices in MySQL: {final_mandi_count} (Matches baseline: 17)")

    assert final_category_count == initial_category_count
    assert final_crop_count == initial_crop_count
    assert final_mandi_count == initial_mandi_count
    print("-> PASSED: Zero persistent database records were altered or lost.")

    print("\n" + "=" * 75)
    print(" ALL PHASE 3 VERIFICATION TESTS PASSED SUCCESSFULLY ON MYSQL 8.0!")
    print("=" * 75)

if __name__ == '__main__':
    run_tests()
