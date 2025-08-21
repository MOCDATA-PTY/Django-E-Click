# Profile Picture Organization System

## 📁 Folder Structure

The profile picture system now organizes images into a clean, hierarchical structure:

```
media/
├── admin/                    # Admin/Staff profile pictures
│   ├── admin/              # admin user's pictures
│   ├── manager1/           # manager user's pictures
│   └── staff1/             # staff user's pictures
├── users/                   # Regular user profile pictures
│   ├── john_doe/           # john_doe user's pictures
│   ├── jane_smith/         # jane_smith user's pictures
│   └── developer1/         # developer user's pictures
└── clients/                 # Client profile pictures
    ├── client1/             # client1's pictures
    ├── client2/             # client2's pictures
    └── client3/             # client3's pictures
```

## 🔧 How It Works

### Automatic Organization
- **Admin/Staff Users**: Profile pictures automatically go to `admin/username/`
- **Regular Users**: Profile pictures automatically go to `users/username/`
- **Clients**: Profile pictures automatically go to `clients/username/`

### 🚀 **Automatic Folder Creation**
- **User Creation**: When a user is created, their folder is automatically created
- **Client Creation**: When a client is created, their folder is automatically created
- **Admin Status Changes**: If a user's admin status changes, folders are automatically reorganized
- **Profile Picture Upload**: Folders are ensured to exist before any file upload

### Upload Paths
The system uses custom upload functions that automatically detect user type and create folders:

```python
def user_profile_picture_path(instance, filename):
    """Automatically routes to admin/ or users/ based on user permissions"""
    if instance.user.is_staff or instance.user.is_superuser:
        base_folder = 'admin'
    else:
        base_folder = 'users'
    
    # Ensure the folder exists
    user_folder = os.path.join(settings.MEDIA_ROOT, base_folder, instance.user.username)
    os.makedirs(user_folder, exist_ok=True)
    
    return f'{base_folder}/{instance.user.username}/{filename}'

def client_profile_picture_path(instance, filename):
    """Routes client pictures to clients/username/"""
    # Ensure the folder exists
    client_folder = os.path.join(settings.MEDIA_ROOT, 'clients', instance.username)
    os.makedirs(client_folder, exist_ok=True)
    
    return f'clients/{instance.username}/{filename}'
```

## 📋 Model Updates

### UserProfile Model
```python
class UserProfile(models.Model):
    profile_picture = models.ImageField(
        upload_to=user_profile_picture_path,  # Automatic routing + folder creation
        blank=True, 
        null=True
    )
```

### Client Model
```python
class Client(models.Model):
    profile_picture = models.ImageField(
        upload_to=client_profile_picture_path,  # Client routing + folder creation
        blank=True, 
        null=True
    )
```

## 🔄 Automatic Folder Management

### Django Signals
The system uses Django signals to automatically manage folders:

```python
@receiver(post_save, sender=User)
def create_user_profile_and_folders(sender, instance, created, **kwargs):
    """Create UserProfile and folders when a User is created"""
    if created:
        # Create UserProfile
        UserProfile.objects.get_or_create(user=instance)
        
        # Create folders automatically
        is_admin = instance.is_staff or instance.is_superuser
        create_user_folders(instance, is_admin)

@receiver(post_save, sender=Client)
def create_client_folders_on_creation(sender, instance, created, **kwargs):
    """Create folders when a Client is created"""
    if created:
        create_client_folders(instance)
```

### Folder Creation Functions
```python
def create_user_folders(user, is_admin=False):
    """Create profile picture folders for a user"""
    if is_admin or user.is_staff or user.is_superuser:
        base_folder = 'admin'
    else:
        base_folder = 'users'
    
    user_folder = os.path.join(settings.MEDIA_ROOT, base_folder, user.username)
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def create_client_folders(client):
    """Create profile picture folders for a client"""
    client_folder = os.path.join(settings.MEDIA_ROOT, 'clients', client.username)
    os.makedirs(client_folder, exist_ok=True)
    return client_folder
```

## 🚀 Benefits

1. **Organized Structure**: Clear separation between user types
2. **Easy Management**: Each user has their own folder
3. **Scalable**: System automatically creates folders as needed
4. **Clean URLs**: Organized paths like `/media/admin/admin/profile.jpg`
5. **Easy Backup**: Can backup specific user types separately
6. **🆕 Automatic**: No manual folder creation needed
7. **🆕 Self-Healing**: Folders are created automatically when users are created
8. **🆕 Smart Routing**: Automatically detects user type and routes to correct folder

## 🔄 Migration & Setup

### For Existing Users
Use the management command to set up folders for all existing users:

```bash
# Set up folders for all existing users
python manage.py setup_user_folders

# Set up folders and clean up empty ones
python manage.py setup_user_folders --cleanup
```

### For New Users
**No action needed!** Folders are created automatically when:
- A new user is created
- A new client is created
- A user's admin status changes
- A profile picture is uploaded

## 📝 Requirements

The system requires these packages (already in requirements.txt):

```txt
# Core Django
Django==5.0.14

# Image Processing
Pillow==10.1.0

# Static Files
whitenoise==6.9.0

# Other dependencies...
```

## 🎯 Usage Examples

### Creating Users (Folders Created Automatically)
```python
# Create admin user - folder created automatically
admin_user = User.objects.create_user(
    username='admin',
    email='admin@example.com',
    password='admin123',
    is_staff=True,
    is_superuser=True
)
# Folder automatically created: media/admin/admin/

# Create regular user - folder created automatically
regular_user = User.objects.create_user(
    username='john_doe',
    email='john@example.com',
    password='pass123'
)
# Folder automatically created: media/users/john_doe/

# Create client - folder created automatically
client = Client.objects.create(
    username='client1',
    email='client1@example.com'
)
# Folder automatically created: media/clients/client1/
```

### Uploading Profile Pictures (Folders Ensured)
```python
# Upload profile picture - folder automatically created if needed
admin_user.profile.profile_picture = uploaded_file
admin_user.profile.save()
# File goes to: media/admin/admin/filename.jpg

# Upload client picture - folder automatically created if needed
client.profile_picture = uploaded_file
client.save()
# File goes to: media/clients/client1/filename.jpg
```

### Accessing Profile Pictures
```python
# Get profile picture URL
profile_picture_url = user.profile.profile_picture.url
# Returns: /media/admin/admin/profile.jpg or /media/users/john_doe/profile.jpg

# Get profile picture path
profile_picture_path = user.profile.profile_picture.path
# Returns: /full/path/to/media/admin/admin/profile.jpg
```

## 🔒 Security Considerations

- Profile pictures are stored in the `media/` directory
- Access is controlled through Django's media serving
- File uploads are validated for security
- Users can only access their own profile pictures
- Folders are created with proper permissions

## 🧹 Maintenance

### Automatic Cleanup
The system automatically:
- Creates folders when users are created
- Reorganizes folders when admin status changes
- Removes empty folders when users are deleted

### Manual Cleanup
```bash
# Clean up empty folders
python manage.py setup_user_folders --cleanup
```

### Backup Strategy
```bash
# Backup admin pictures
tar -czf admin_pictures.tar.gz media/admin/

# Backup user pictures
tar -czf user_pictures.tar.gz media/users/

# Backup client pictures
tar -czf client_pictures.tar.gz media/clients/
```

## 🧪 Testing

Test the automatic folder creation system:

```bash
# Test folder creation
python test_folder_creation.py

# Test management commands
python manage.py setup_user_folders --cleanup
```

## 📞 Support

For questions or issues with the profile picture system:
1. Check the Django logs
2. Verify folder permissions
3. Ensure media directory is writable
4. Run the setup command: `python manage.py setup_user_folders`
5. Contact the development team

## 🔄 Recent Updates

- ✅ **Automatic folder creation** when users are created
- ✅ **Smart routing** based on user permissions
- ✅ **Self-healing** folder system
- ✅ **Django signals** for automatic management
- ✅ **Management commands** for setup and maintenance
