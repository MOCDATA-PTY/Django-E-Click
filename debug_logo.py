#!/usr/bin/env python3
"""
Debug script to check logo path issues in Django
"""

import os
import sys
import django
from pathlib import Path

# Add the Django project to the Python path
current_dir = Path.cwd()
sys.path.insert(0, str(current_dir))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eclick.settings')
django.setup()

# Now import Django settings
from django.conf import settings

def debug_logo_paths():
    """Debug logo path issues"""
    print("🔍 Debugging Logo Paths in Django")
    print("=" * 50)
    
    print(f"Current working directory: {os.getcwd()}")
    print(f"Current directory (Path): {current_dir}")
    print(f"settings.BASE_DIR: {settings.BASE_DIR}")
    
    # Test different logo paths
    paths_to_test = [
        # Django settings path
        os.path.join(settings.BASE_DIR, 'home', 'Logo.png'),
        # Current directory path
        os.path.join(current_dir, 'home', 'Logo.png'),
        # Absolute path
        str(current_dir / 'home' / 'Logo.png'),
    ]
    
    print("\n📁 Testing Logo Paths:")
    for i, path in enumerate(paths_to_test):
        exists = os.path.exists(path)
        size = os.path.getsize(path) if exists else 0
        print(f"{i+1}. {'✅' if exists else '❌'} {path}")
        if exists:
            print(f"   Size: {size} bytes")
        else:
            print(f"   Does not exist")
    
    # Test if we can read the logo file
    logo_path = os.path.join(settings.BASE_DIR, 'home', 'Logo.png')
    print(f"\n🔍 Testing logo file access:")
    print(f"Logo path: {logo_path}")
    print(f"Exists: {os.path.exists(logo_path)}")
    
    if os.path.exists(logo_path):
        try:
            with open(logo_path, 'rb') as f:
                content = f.read(100)
                print(f"Can read file: ✅")
                print(f"First 100 bytes: {content[:50]}...")
        except Exception as e:
            print(f"❌ Error reading file: {e}")
    else:
        print("❌ Logo file not found at Django settings path")
        
        # Try alternative path
        alt_path = os.path.join(current_dir, 'home', 'Logo.png')
        if os.path.exists(alt_path):
            print(f"✅ Logo found at alternative path: {alt_path}")
            print(f"Recommendation: Use current_dir instead of settings.BASE_DIR")

if __name__ == "__main__":
    debug_logo_paths()
