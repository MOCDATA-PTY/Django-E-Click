-- MySQL Database Setup Script for E-Click Project
-- Ubuntu/Debian Hostinger Server
-- Database already exists: E-click-Project-management
-- Admin user already exists: admin

-- Verify existing database and user
SHOW DATABASES LIKE 'E-click-Project-management';
SELECT User, Host FROM mysql.user WHERE User = 'admin';

-- Verify admin user privileges
SHOW GRANTS FOR 'admin'@'%';

-- Set secure SQL mode for production (if not already set)
SET GLOBAL sql_mode = 'STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO,ONLY_FULL_GROUP_BY';

-- Verify database access and permissions
USE `E-click-Project-management`;
SHOW TABLES;

-- Test admin user permissions
-- This should work if the user has proper privileges
SELECT 'Database connection test successful' as status;
