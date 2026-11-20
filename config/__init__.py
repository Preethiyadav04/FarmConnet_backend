"""
FarmConnect Django Configuration Package
Ensures seamless compatibility with MySQL 8.0.x on Django 6+.
"""

try:
    from django.db.backends.mysql.features import DatabaseFeatures
    # Allow MySQL 8.0 (Django 6+ default minimum is 8.4)
    DatabaseFeatures.minimum_database_version = property(lambda self: (8, 0))
except Exception:
    pass
