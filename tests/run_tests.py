#!/usr/bin/env python
"""
Test runner script for E-Click Project Management System
"""
import os
import sys
import subprocess
import glob

def run_all_tests():
    """Run all test files in the tests directory"""
    print("🧪 Running all tests for E-Click Project Management System")
    print("=" * 60)
    
    # Get all test files
    test_files = glob.glob("test_*.py")
    
    if not test_files:
        print("❌ No test files found!")
        return
    
    print(f"📁 Found {len(test_files)} test files:")
    for test_file in test_files:
        print(f"   - {test_file}")
    
    print("\n🚀 Running tests...")
    print("-" * 60)
    
    # Run each test file
    for test_file in test_files:
        print(f"\n🔍 Running {test_file}...")
        try:
            result = subprocess.run([sys.executable, test_file], 
                                  capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                print(f"✅ {test_file} - PASSED")
                if result.stdout:
                    print(f"   Output: {result.stdout.strip()}")
            else:
                print(f"❌ {test_file} - FAILED")
                if result.stderr:
                    print(f"   Error: {result.stderr.strip()}")
                    
        except subprocess.TimeoutExpired:
            print(f"⏰ {test_file} - TIMEOUT (30s)")
        except Exception as e:
            print(f"💥 {test_file} - ERROR: {e}")
    
    print("\n" + "=" * 60)
    print("🏁 Test run completed!")

def run_specific_test(test_name):
    """Run a specific test file"""
    test_file = f"test_{test_name}.py"
    if not os.path.exists(test_file):
        print(f"❌ Test file {test_file} not found!")
        return
    
    print(f"🧪 Running specific test: {test_file}")
    print("=" * 60)
    
    try:
        result = subprocess.run([sys.executable, test_file], 
                              capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print(f"✅ {test_file} - PASSED")
            if result.stdout:
                print(f"Output:\n{result.stdout}")
        else:
            print(f"❌ {test_file} - FAILED")
            if result.stderr:
                print(f"Error:\n{result.stderr}")
                
    except subprocess.TimeoutExpired:
        print(f"⏰ {test_file} - TIMEOUT (30s)")
    except Exception as e:
        print(f"💥 {test_file} - ERROR: {e}")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        # Run specific test
        test_name = sys.argv[1]
        run_specific_test(test_name)
    else:
        # Run all tests
        run_all_tests()
