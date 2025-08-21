#!/usr/bin/env python3
"""
Test script to verify PDF generation functionality
"""

import os
import sys
import django

# Add the project directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eclick.settings')
django.setup()

from home.views import generate_project_summary_pdf
from home.models import Project

def test_pdf_generation():
    """Test the PDF generation function"""
    try:
        print("🔍 Testing PDF generation...")
        
        # Get the first available project
        project = Project.objects.first()
        if not project:
            print("❌ No projects found in database")
            return False
        
        print(f"📋 Using project: {project.name}")
        
        # Test PDF generation
        pdf_path = generate_project_summary_pdf(
            project=project,
            client_name="Test Client",
            total_tasks=10,
            completed_tasks=5,
            task_completion_rate=50.0,
            team_size=3,
            recent_tasks=2,
            recent_subtasks=1,
            generated_time="Test Time"
        )
        
        print(f"📄 PDF generated at: {pdf_path}")
        
        # Check if file exists
        if os.path.exists(pdf_path):
            file_size = os.path.getsize(pdf_path)
            print(f"✅ PDF file created successfully! Size: {file_size} bytes")
            
            # Clean up
            os.unlink(pdf_path)
            print("🧹 Temporary PDF file cleaned up")
            return True
        else:
            print("❌ PDF file was not created")
            return False
            
    except Exception as e:
        print(f"❌ Error during PDF generation: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_pdf_generation()
    if success:
        print("\n🎉 PDF generation test PASSED!")
    else:
        print("\n💥 PDF generation test FAILED!")
