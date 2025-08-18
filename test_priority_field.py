#!/usr/bin/env python
import os
import sys
import django

# Add the project directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eclick.settings')
django.setup()

from home.models import Project

def test_priority_field():
    """Test that the priority field is working correctly"""
    try:
        # Try to create a project with priority
        project = Project.objects.create(
            name='Test Project',
            client='Test Client',
            client_email='test@example.com',
            priority='high'
        )
        print(f"✅ Successfully created project with priority: {project.priority}")
        print(f"   Priority display: {project.get_priority_display()}")
        
        # Clean up
        project.delete()
        print("✅ Test project deleted successfully")
        
        # Test that the field exists
        field_names = [field.name for field in Project._meta.fields]
        if 'priority' in field_names:
            print("✅ Priority field exists in Project model")
        else:
            print("❌ Priority field missing from Project model")
            
        print("\n🎉 Priority field test completed successfully!")
        
    except Exception as e:
        print(f"❌ Error testing priority field: {e}")
        return False
    
    return True

if __name__ == '__main__':
    test_priority_field()
