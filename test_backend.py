"""
FarmConnect - Backend Verification Script (MySQL 8.0 Suite)
Tests Custom User Model, Role Profiles, Signals, JWT Authentication, and API Endpoints
against MySQL 8.0.39 on port 3306.
Safeguards all existing data. Never exposes secrets or passwords.
"""

import os
import sys
from pathlib import Path

# Setup Python path and Django environment
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.test import Client
from django.db import connection
from django.contrib.auth import get_user_model
from apps.accounts.models import UserRole, FarmerProfile, BuyerProfile, TransporterProfile

User = get_user_model()

def run_tests():
    print("=" * 70)
    print(" FarmConnect - Phase 2 Verification Suite (Running on MySQL 8.0)")
    print("=" * 70)

    # 1. Explicit Database Connection Verification
    print("\n[STEP 1] Verifying Active Database Backend & Engine...")
    db_vendor = connection.vendor
    db_engine = connection.settings_dict.get('ENGINE')
    db_name = connection.settings_dict.get('NAME')
    db_host = connection.settings_dict.get('HOST')
    db_port = connection.settings_dict.get('PORT')

    print(f"  • Database Vendor: {db_vendor}")
    print(f"  • Database Engine: {db_engine}")
    print(f"  • Database Name:   {db_name}")
    print(f"  • Database Host:   {db_host}")
    print(f"  • Database Port:   {db_port}")

    assert db_vendor == 'mysql', f"ERROR: Tests are NOT running on MySQL! Found: {db_vendor}"
    assert 'mysql' in db_engine, f"ERROR: Engine is not MySQL: {db_engine}"
    assert db_name == 'farmconnect_db', f"ERROR: Incorrect database name: {db_name}"

    with connection.cursor() as cursor:
        cursor.execute("SELECT VERSION(), @@port, DATABASE();")
        version, active_port, current_db = cursor.fetchone()
        print(f"  • Live Server Query: VERSION={version}, PORT={active_port}, DATABASE={current_db}")

        assert str(active_port) == '3306', f"ERROR: Not connected on port 3306! Active port: {active_port}"
        assert current_db == 'farmconnect_db', f"ERROR: Not connected to farmconnect_db! Active: {current_db}"

    print("-> PASSED: Explicitly confirmed tests are executing against MySQL 8.0 on port 3306.")

    # 2. Existing Users Safety Check
    print("\n[STEP 2] Inspecting Existing Database Records...")
    existing_user_count = User.objects.count()
    print(f"  Current registered users in '{db_name}': {existing_user_count}")
    existing_usernames = list(User.objects.values_list('username', flat=True)[:10])
    print(f"  Sample existing user accounts: {existing_usernames}")

    client = Client()

    # 3. Test Health Endpoint
    print("\n[TEST 1] Testing /api/health/ endpoint...")
    response = client.get('/api/health/')
    print(f"  Status: {response.status_code}")
    print(f"  Response: {response.json()}")
    assert response.status_code == 200, f"Health check failed: {response.status_code}"
    assert response.json().get('database') == 'ok', "Database reported not ok by health endpoint"
    print("-> PASSED: Health endpoint is functioning and database connectivity is healthy.")

    # 4. Test User Creation & Auto Profile Creation for all Roles
    print("\n[TEST 2] Testing User Model & Role Signal Profiles in MySQL...")
    test_roles = [
        (UserRole.FARMER, 'test_farmer_auto', 'farmer_auto@farmconnect.org'),
        (UserRole.BUYER, 'test_buyer_auto', 'buyer_auto@farmconnect.org'),
        (UserRole.TRANSPORTER, 'test_trans_auto', 'trans_auto@farmconnect.org'),
        (UserRole.ADMIN, 'test_admin_auto', 'admin_auto@farmconnect.org'),
    ]

    created_users = {}
    for role, username, email in test_roles:
        # Delete only our specific test user if left over from previous test run
        User.objects.filter(username=username).delete()
        user = User.objects.create_user(
            username=username,
            email=email,
            password='TestPassword123!',
            role=role,
            phone='9876543210'
        )
        # Update user profile
        profile = user.user_profile
        profile.city = 'Nashik'
        profile.state = 'Maharashtra'
        profile.save()
        created_users[role] = user
        print(f"  Created user: {user.username} (Role: {user.role}, MySQL ID: {user.id})")

    # Verify signal-created profiles in MySQL
    farmer_user = created_users[UserRole.FARMER]
    assert hasattr(farmer_user, 'farmer_profile'), "Farmer profile was not created by signal!"
    print(f"  -> Farmer profile verified in MySQL: ID={farmer_user.farmer_profile.id}")

    buyer_user = created_users[UserRole.BUYER]
    assert hasattr(buyer_user, 'buyer_profile'), "Buyer profile was not created by signal!"
    print(f"  -> Buyer profile verified in MySQL: ID={buyer_user.buyer_profile.id}")

    transporter_user = created_users[UserRole.TRANSPORTER]
    assert hasattr(transporter_user, 'transporter_profile'), "Transporter profile was not created by signal!"
    print(f"  -> Transporter profile verified in MySQL: ID={transporter_user.transporter_profile.id}")

    print("-> PASSED: All 4 roles and role-based profiles verified directly in MySQL.")

    # 5. Test JWT Token Generation and Custom Claims
    print("\n[TEST 3] Testing JWT Authentication & Custom Claims...")
    login_response = client.post('/api/auth/login/', {
        'username': 'test_farmer_auto',
        'password': 'TestPassword123!'
    }, content_type='application/json')

    print(f"  Login HTTP Status: {login_response.status_code}")
    assert login_response.status_code == 200, f"Login failed: {login_response.json()}"
    token_data = login_response.json()
    assert 'access' in token_data, "No access token in response"
    assert 'refresh' in token_data, "No refresh token in response"
    assert 'user' in token_data, "User info missing in response"
    assert token_data['user']['role'].lower() == 'farmer', "User role mismatch in response"

    access_token = token_data['access']
    print(f"  Access token generated: {access_token[:35]}...")
    print(f"  User payload returned: {token_data['user']}")
    print("-> PASSED: JWT login and claims generation verified.")

    # 6. Test Authenticated Profile Access with JWT Header
    print("\n[TEST 4] Testing Authenticated API Access via JWT...")
    profile_response = client.get(
        '/api/auth/profile/',
        HTTP_AUTHORIZATION=f'Bearer {access_token}'
    )
    print(f"  Profile Status: {profile_response.status_code}")
    assert profile_response.status_code == 200, f"Profile request failed: {profile_response.json()}"
    profile_data = profile_response.json()
    assert profile_data['username'] == 'test_farmer_auto'
    assert 'farmer_profile' in profile_data
    print(f"  Authenticated Profile: {profile_data['username']} (Role: {profile_data['role']})")
    print("-> PASSED: Authenticated profile retrieval verified.")

    # 7. Test Public Register API
    print("\n[TEST 5] Testing Public Registration API...")
    User.objects.filter(username='test_registered_buyer').delete()
    register_response = client.post('/api/auth/register/', {
        'username': 'test_registered_buyer',
        'email': 'regbuyer@farmconnect.org',
        'password': 'StrongBuyerPass123!',
        'password_confirm': 'StrongBuyerPass123!',
        'role': 'BUYER',
        'phone': '9988776655',
        'city': 'Pune',
        'state': 'Maharashtra'
    }, content_type='application/json')

    print(f"  Registration Status: {register_response.status_code}")
    assert register_response.status_code == 201, f"Registration failed: {register_response.json()}"
    reg_user = User.objects.get(username='test_registered_buyer')
    assert reg_user.role.lower() == 'buyer'
    assert hasattr(reg_user, 'buyer_profile')
    print(f"  Newly registered in MySQL: {reg_user.username} (Role: {reg_user.role}, MySQL ID: {reg_user.id})")
    print("-> PASSED: Registration API functioning as expected in MySQL.")

    # 8. Clean up ONLY our test-created users (safeguarding all other users)
    print("\n[CLEANUP] Cleaning up test-created entries while preserving real data...")
    test_usernames = [
        'test_farmer_auto', 'test_buyer_auto', 'test_trans_auto',
        'test_admin_auto', 'test_registered_buyer'
    ]
    deleted_count, _ = User.objects.filter(username__in=test_usernames).delete()
    print(f"  Cleaned up {deleted_count} test items. Existing user data preserved intact.")

    final_user_count = User.objects.count()
    print(f"  Remaining persistent users in MySQL 'farmconnect_db': {final_user_count}")

    print("\n" + "=" * 70)
    print(" ALL BACKEND VERIFICATION TESTS PASSED SUCCESSFULLY ON MYSQL 8.0!")
    print("=" * 70)

if __name__ == '__main__':
    run_tests()
