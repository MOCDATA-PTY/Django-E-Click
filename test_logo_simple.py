#!/usr/bin/env python3
"""
Simple test script to check if the logo can be loaded by ReportLab
This tests the basic functionality without Django
"""

import os
from pathlib import Path

def test_logo_loading():
    """Test if the logo can be loaded by ReportLab"""
    print("🔍 Testing Logo Loading with ReportLab")
    print("=" * 50)
    
    # Check current directory
    current_dir = Path.cwd()
    print(f"Current directory: {current_dir}")
    
    # Test logo path
    logo_path = os.path.join(current_dir, 'home', 'Logo.png')
    print(f"Logo path: {logo_path}")
    print(f"Logo exists: {os.path.exists(logo_path)}")
    
    if not os.path.exists(logo_path):
        print("❌ Logo file not found!")
        return False
    
    # Check file size
    file_size = os.path.getsize(logo_path)
    print(f"Logo file size: {file_size} bytes")
    
    if file_size == 0:
        print("❌ Logo file is empty!")
        return False
    
    # Try to import ReportLab
    try:
        from reportlab.platypus import Image
        print("✅ ReportLab Image imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import ReportLab: {e}")
        print("Please install ReportLab: pip install reportlab")
        return False
    
    # Try to create an Image object
    try:
        logo_img = Image(logo_path, width=80, height=40)
        print("✅ Logo Image object created successfully")
        print(f"Image width: {logo_img._width}")
        print(f"Image height: {logo_img._height}")
        return True
    except Exception as e:
        print(f"❌ Failed to create Image object: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_pdf_creation():
    """Test creating a simple PDF with the logo"""
    print("\n📄 Testing PDF Creation with Logo")
    print("=" * 40)
    
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        import tempfile
        
        # Create a temporary PDF
        temp_dir = tempfile.gettempdir()
        pdf_path = os.path.join(temp_dir, "test_logo.pdf")
        
        # Create PDF document
        doc = SimpleDocTemplate(pdf_path, pagesize=A4)
        story = []
        
        # Get styles
        styles = getSampleStyleSheet()
        
        # Add title
        story.append(Paragraph("Test PDF with Logo", styles['Title']))
        story.append(Spacer(1, 20))
        
        # Add logo
        logo_path = os.path.join(Path.cwd(), 'home', 'Logo.png')
        if os.path.exists(logo_path):
            from reportlab.platypus import Image
            logo_img = Image(logo_path, width=100, height=50)
            story.append(logo_img)
            story.append(Spacer(1, 20))
            print("✅ Logo added to PDF story")
        else:
            story.append(Paragraph("Logo not found", styles['Normal']))
            print("❌ Logo not found for PDF")
        
        # Add some text
        story.append(Paragraph("This is a test PDF to verify logo loading.", styles['Normal']))
        
        # Build PDF
        doc.build(story)
        
        # Check if PDF was created
        if os.path.exists(pdf_path):
            file_size = os.path.getsize(pdf_path)
            print(f"✅ PDF created successfully: {pdf_path}")
            print(f"PDF file size: {file_size} bytes")
            
            # Check PDF content
            with open(pdf_path, 'rb') as f:
                content = f.read()
                if content.startswith(b'%PDF'):
                    print("✅ Valid PDF content")
                else:
                    print("❌ Invalid PDF content")
            
            # Clean up
            try:
                os.remove(pdf_path)
                print("✅ Test PDF cleaned up")
            except:
                print("⚠️ Could not clean up test PDF")
            
            return True
        else:
            print("❌ PDF was not created")
            return False
            
    except Exception as e:
        print(f"❌ Error creating PDF: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Starting Simple Logo Test")
    print("=" * 50)
    
    # Test logo loading
    logo_loaded = test_logo_loading()
    
    if logo_loaded:
        # Test PDF creation
        pdf_created = test_pdf_creation()
        
        if pdf_created:
            print("\n🎉 All tests passed! Logo should work in PDFs.")
        else:
            print("\n❌ PDF creation failed.")
    else:
        print("\n❌ Logo loading failed.")
    
    print("\n�� Test completed!")
