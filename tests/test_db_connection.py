#!/usr/bin/env python3
"""
Database Connection Test Script
Tests connection to E-click-Project-management database
"""

import mysql.connector
from mysql.connector import Error

def test_mysql_connection():
    """Test MySQL connection with provided credentials"""
    
    # Database configuration
    config = {
        'host': 'localhost',
        'user': 'admin',
        'password': 'mk7z@Geg123',
        'database': 'E-click-Project-management',
        'charset': 'utf8mb4',
        'autocommit': True
    }
    
    try:
        print("🔌 Testing MySQL connection...")
        
        # Establish connection
        connection = mysql.connector.connect(**config)
        
        if connection.is_connected():
            db_info = connection.get_server_info()
            print(f"✅ Successfully connected to MySQL Server version {db_info}")
            
            # Get cursor
            cursor = connection.cursor()
            
            # Execute a test query
            cursor.execute("SELECT DATABASE();")
            database = cursor.fetchone()
            print(f"📊 Connected to database: {database[0]}")
            
            # Test basic operations
            cursor.execute("SHOW TABLES;")
            tables = cursor.fetchall()
            print(f"📋 Found {len(tables)} tables in database")
            
            if tables:
                print("📝 Tables:")
                for table in tables[:5]:  # Show first 5 tables
                    print(f"   - {table[0]}")
                if len(tables) > 5:
                    print(f"   ... and {len(tables) - 5} more")
            
            # Test Django-specific operations
            print("\n🧪 Testing Django-compatible operations...")
            
            # Test CREATE TABLE (should work with admin privileges)
            test_table_name = "django_test_table"
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {test_table_name} (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    test_column VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print(f"✅ CREATE TABLE test passed")
            
            # Test INSERT
            cursor.execute(f"INSERT INTO {test_table_name} (test_column) VALUES ('Django connection test')")
            print(f"✅ INSERT test passed")
            
            # Test SELECT
            cursor.execute(f"SELECT * FROM {test_table_name} ORDER BY id DESC LIMIT 1")
            result = cursor.fetchone()
            print(f"✅ SELECT test passed: {result}")
            
            # Test UPDATE
            cursor.execute(f"UPDATE {test_table_name} SET test_column = 'Updated test' WHERE id = {result[0]}")
            print(f"✅ UPDATE test passed")
            
            # Test DELETE
            cursor.execute(f"DELETE FROM {test_table_name} WHERE id = {result[0]}")
            print(f"✅ DELETE test passed")
            
            # Clean up test table
            cursor.execute(f"DROP TABLE {test_table_name}")
            print(f"✅ DROP TABLE test passed")
            
            print("\n🎉 All database tests passed! Django should work correctly.")
            
        else:
            print("❌ Failed to connect to MySQL")
            
    except Error as e:
        print(f"❌ Error connecting to MySQL: {e}")
        print("\n🔧 Troubleshooting tips:")
        print("1. Make sure MySQL server is running")
        print("2. Verify credentials are correct")
        print("3. Check if admin user has proper privileges")
        print("4. Ensure firewall allows connections")
        
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()
            print("🔌 MySQL connection closed")

if __name__ == "__main__":
    test_mysql_connection()
