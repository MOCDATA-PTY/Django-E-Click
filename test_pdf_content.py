#!/usr/bin/env python
import os
import sys
import django

# Add the project directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eclick.settings')
django.setup()

from home.views import generate_exact_pdf_report

def test_pdf_content():
    """Test PDF content generation"""
    try:
        print("=== Testing PDF Content ===")
        
        # Generate PDF
        print("1. Generating PDF...")
        pdf_file = generate_exact_pdf_report(days_filter=30)
        print(f"   PDF generated: {pdf_file}")
        
        # Check PDF file
        if os.path.exists(pdf_file):
            file_size = os.path.getsize(pdf_file)
            print(f"   PDF file size: {file_size} bytes")
            
            if file_size > 0:
                print("   ✅ PDF generation successful!")
                
                # Read first few bytes to check if it's a valid PDF
                with open(pdf_file, 'rb') as f:
                    first_bytes = f.read(10)
                    print(f"   First 10 bytes: {first_bytes}")
                    
                    # Check if it starts with PDF signature
                    if first_bytes.startswith(b'%PDF'):
                        print("   ✅ Valid PDF file (starts with %PDF)")
                    else:
                        print("   ❌ Not a valid PDF file")
                
                # Try to read the PDF content (this might not work with binary files)
                try:
                    with open(pdf_file, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read(1000)
                        print(f"   First 1000 chars: {content[:200]}...")
                except:
                    print("   PDF is binary (expected)")
                
                # Clean up
                try:
                    os.unlink(pdf_file)
                    print("   🧹 PDF file cleaned up")
                except:
                    pass
                    
            else:
                print("   ❌ PDF file is empty!")
        else:
            print("   ❌ PDF file was not created!")
            
    except Exception as e:
        print(f"❌ Error during testing: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_pdf_content()
