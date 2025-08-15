#!/usr/bin/env python3
"""
Enhanced OAuth flow test with proper configuration
"""

import os
import sys
import django
from pathlib import Path

# Add Django project to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eclick.settings')
django.setup()

from django.conf import settings
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle

def test_oauth_flow():
    """Test the OAuth flow with proper configuration"""
    try:
        print("🔧 Checking OAuth configuration...")
        
        # Check if credentials file exists
        credentials_path = os.path.join('home', 'credentials.json')
        if not os.path.exists(credentials_path):
            print(f"❌ Credentials file not found at: {credentials_path}")
            print("📝 Please download credentials.json from Google Cloud Console")
            return
        
        print(f"✅ Found credentials file at: {credentials_path}")
        
        # Check environment variables
        client_id = os.getenv('GOOGLE_OAUTH2_CLIENT_ID') or settings.GOOGLE_OAUTH2_CLIENT_ID
        if not client_id:
            print("⚠️  GOOGLE_OAUTH2_CLIENT_ID not set in environment or settings")
        
        # Use scopes from settings - Google automatically adds 'openid' scope
        scopes = getattr(settings, 'GMAIL_SCOPES', [
            'https://www.googleapis.com/auth/gmail.send',
            'https://www.googleapis.com/auth/gmail.compose',
            'https://www.googleapis.com/auth/gmail.modify',
            'https://www.googleapis.com/auth/userinfo.email',
            'openid'  # Google automatically adds this
        ])
        
        print(f"📋 Using scopes: {scopes}")
        
        # Check token file
        token_path = os.path.join('home', 'token.pickle')
        creds = None
        
        if os.path.exists(token_path):
            print("✅ Found existing token file")
            try:
                with open(token_path, 'rb') as token:
                    creds = pickle.load(token)
            except Exception as e:
                print(f"⚠️  Error loading token: {e}")
                creds = None
        
        # Handle credentials
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                print("🔄 Refreshing expired token...")
                try:
                    creds.refresh(Request())
                    print("✅ Token refreshed successfully")
                except Exception as e:
                    print(f"❌ Error refreshing token: {e}")
                    creds = None
            
            if not creds:
                print("🔐 Starting OAuth flow...")
                print("🌐 This will open a browser window for authentication")
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_path, scopes)
                
                # Use port from settings or default
                port = 55691
                if hasattr(settings, 'OAUTH2_REDIRECT_URI'):
                    try:
                        port = int(settings.OAUTH2_REDIRECT_URI.split(':')[1].split('/')[0])
                    except:
                        pass
                
                print(f"🔗 Using redirect URI: http://localhost:{port}/")
                # Use the exact redirect URI that matches Google Cloud Console
                creds = flow.run_local_server(port=port, prompt='consent', redirect_uri_trailing_slash=False)
                
                print("✅ OAuth flow completed successfully!")
            
            # Save credentials
            try:
                with open(token_path, 'wb') as token:
                    pickle.dump(creds, token)
                print("💾 Token saved for future use")
            except Exception as e:
                print(f"⚠️  Warning: Could not save token: {e}")
        else:
            print("✅ Using existing valid token")
        
        print("🎉 OAuth setup completed successfully!")
        print(f"📧 Gmail access configured for: {creds.client_id}")
        
    except Exception as e:
        print(f"❌ Error during OAuth flow: {str(e)}")
        print("\n🔧 Troubleshooting tips:")
        print("1. Make sure http://localhost:55691/ is in your Google Cloud Console redirect URIs")
        print("2. Check that your credentials.json file is valid")
        print("3. Ensure you're using the correct Google account")
        print("4. Verify your .env file has the correct OAuth credentials")

if __name__ == "__main__":
    test_oauth_flow() 