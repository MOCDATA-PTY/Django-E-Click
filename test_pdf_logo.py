#!/usr/bin/env python3
"""
Test script to check if the E-Click logo is being added to PDF reports
This script will generate a test PDF and show us exactly what's happening
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

# Now import Django models and functions
from home.models import Client, Project, Task, SubTask
from home.views import generate_client_specific_pdf_report
from django.contrib.auth.models import User

def test_pdf_generation():
    """Test PDF generation with logo"""
    print("🔍 Testing PDF Generation with Logo")
    print("=" * 50)
    
    # Check if logo file exists
    logo_path = os.path.join(current_dir, 'home', 'Logo.png')
    print(f"Logo path: {logo_path}")
    print(f"Logo exists: {os.path.exists(logo_path)}")
    
    if os.path.exists(logo_path):
        print(f"Logo file size: {os.path.getsize(logo_path)} bytes")
    else:
        print("❌ Logo file not found!")
        return
    
    # Check if we have any clients
    try:
        clients = Client.objects.all()
        print(f"Found {clients.count()} clients")
        
        if clients.exists():
            client = clients.first()
            print(f"Using client: {client.username}")
            
            # Try to generate PDF
            print("\n📄 Generating PDF report...")
            try:
                pdf_path = generate_client_specific_pdf_report(client.id)
                print(f"PDF generated at: {pdf_path}")
                print(f"PDF exists: {os.path.exists(pdf_path)}")
                
                if os.path.exists(pdf_path):
                    print(f"PDF file size: {os.path.getsize(pdf_path)} bytes")
                    
                    # Check PDF content (basic check)
                    with open(pdf_path, 'rb') as f:
                        content = f.read()
                        print(f"PDF starts with: {content[:100]}")
                        
                        # Check if it's a valid PDF
                        if content.startswith(b'%PDF'):
                            print("✅ Valid PDF generated")
                        else:
                            print("❌ Invalid PDF content")
                            
                else:
                    print("❌ PDF file not created")
                    
            except Exception as e:
                print(f"❌ Error generating PDF: {str(e)}")
                import traceback
                traceback.print_exc()
        else:
            print("❌ No clients found in database")
            
    except Exception as e:
        print(f"❌ Error accessing database: {str(e)}")
        import traceback
        traceback.print_exc()

def test_logo_paths():
    """Test all logo paths used in the code"""
    print("\n🔍 Testing Logo Paths")
    print("=" * 30)
    
    # Test different logo paths
    paths_to_test = [
        os.path.join(current_dir, 'home', 'Logo.png'),
        os.path.join(current_dir, 'static', 'images', 'E Click Logo (1).png'),
        os.path.join(current_dir, 'static', 'images', 'E-CLICK LOGO FINGER.png'),
    ]
    
    for path in paths_to_test:
        exists = os.path.exists(path)
        size = os.path.getsize(path) if exists else 0
        print(f"{'✅' if exists else '❌'} {path}")
        if exists:
            print(f"   Size: {size} bytes")

def test_reportlab_imports():
    """Test if ReportLab imports work"""
    print("\n🔍 Testing ReportLab Imports")
    print("=" * 30)
    
    try:
        from reportlab.platypus import Image
        print("✅ reportlab.platypus.Image imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import reportlab.platypus.Image: {e}")
    
    try:
        from reportlab.lib.pagesizes import A4
        print("✅ reportlab.lib.pagesizes.A4 imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import reportlab.lib.pagesizes.A4: {e}")

if __name__ == "__main__":
    print("🚀 Starting PDF Logo Test")
    print("=" * 50)
    
    # Test logo paths
    test_logo_paths()
    
    # Test ReportLab imports
    test_reportlab_imports()
    
    # Test PDF generation
    test_pdf_generation()
    
    print("\n�� Test completed!")
