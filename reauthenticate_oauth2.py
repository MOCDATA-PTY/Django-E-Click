#!/usr/bin/env python3
"""
OAuth2 Re-authentication Script for E-Click Gmail Service

This script helps you re-authenticate with Google OAuth2 using the updated scopes
that include both gmail.send and gmail.readonly permissions.

Run this script to update your OAuth2 token with the correct scopes.
"""

import os
import sys
import pickle
from pathlib import Path

def main():
    print("🔐 OAuth2 Re-authentication Script for E-Click Gmail Service")
    print("=" * 60)
    
    # Check if we're in the right directory
    current_dir = Path.cwd()
    home_dir = current_dir / "home"
    
    if not home_dir.exists():
        print("❌ Error: Please run this script from the Django-E-Click-master directory")
        print(f"   Current directory: {current_dir}")
        print("   Expected to find: home/ directory")
        return False
    
    # Check for credentials file
    credentials_path = home_dir / "credentials.json"
    if not credentials_path.exists():
        print("❌ Error: OAuth2 credentials file not found!")
        print(f"   Expected location: {credentials_path}")
        print("   Please ensure you have the credentials.json file from Google Cloud Console")
        return False
    
    # Check for existing token
    token_path = home_dir / "token.pickle"
    if token_path.exists():
        print("⚠️  Found existing OAuth2 token")
        print(f"   Location: {token_path}")
        
        try:
            # Try to load the existing token to see if it's valid
            with open(token_path, 'rb') as f:
                creds = pickle.load(f)
            
            print(f"   Token expires: {creds.expiry}")
            print("   Token will be updated with new scopes")
            
        except Exception as e:
            print(f"   Warning: Could not read existing token: {e}")
    
    print("\n📋 Updated OAuth2 Scopes:")
    print("   • https://www.googleapis.com/auth/gmail.send")
    print("   • https://www.googleapis.com/auth/gmail.readonly")
    
    print("\n🚀 Starting OAuth2 flow...")
    print("   This will open your browser for authentication")
    print("   Please complete the authentication process")
    
    try:
        # Import required modules
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        
        # Define the updated scopes
        SCOPES = [
            'https://www.googleapis.com/auth/gmail.send',
            'https://www.googleapis.com/auth/gmail.readonly'
        ]
        
        # Create the flow
        flow = InstalledAppFlow.from_client_secrets_file(
            str(credentials_path), 
            SCOPES
        )
        
        # Run the flow
        print("\n🌐 Opening browser for authentication...")
        creds = flow.run_local_server(port=55691, prompt='consent')
        
        # Save the new credentials
        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)
        
        print("✅ OAuth2 authentication completed successfully!")
        print(f"   New token saved to: {token_path}")
        
        # Test the service
        print("\n🧪 Testing Gmail service...")
        try:
            service = build('gmail', 'v1', credentials=creds)
            
            # Test getting user profile
            user_info = service.users().getProfile(userId='me').execute()
            email = user_info.get('emailAddress', 'Unknown')
            print(f"   ✅ Successfully authenticated as: {email}")
            
            # Test sending capability (just check if we can access the service)
            print("   ✅ Gmail service initialized successfully")
            
        except Exception as e:
            print(f"   ❌ Error testing service: {e}")
            return False
        
        print("\n🎉 OAuth2 re-authentication completed successfully!")
        print("   You can now use the client report functionality")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Please ensure you have the required packages installed:")
        print("   pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client")
        return False
        
    except Exception as e:
        print(f"❌ Authentication error: {e}")
        print("   Please check your credentials and try again")
        return False

if __name__ == "__main__":
    success = main()
    if not success:
        print("\n❌ OAuth2 re-authentication failed")
        sys.exit(1)
    else:
        print("\n✅ OAuth2 re-authentication successful!")
        print("   You can now close this script and try sending client reports again")
