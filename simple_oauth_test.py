#!/usr/bin/env python3
"""
Simple OAuth test using the exact port configuration
"""

import os
from google_auth_oauthlib.flow import InstalledAppFlow
import pickle

# Gmail API scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def main():
    print("🔐 Testing OAuth Flow with Fixed Port...")
    
    # Path to credentials file
    credentials_path = os.path.join('home', 'credentials.json')
    
    if not os.path.exists(credentials_path):
        print(f"❌ Credentials file not found at: {credentials_path}")
        return
    
    print(f"✅ Found credentials file")
    
    try:
        # Create flow with fixed port
        flow = InstalledAppFlow.from_client_secrets_file(
            credentials_path, SCOPES)
        
        print("🌐 Starting OAuth flow on port 55691...")
        print("📋 Please complete the authorization in your browser")
        
        # Use the exact port that's configured in Google Cloud Console
        creds = flow.run_local_server(
            port=55691,
            prompt='consent',
            access_type='offline'
        )
        
        # Save credentials
        token_path = os.path.join('home', 'token.pickle')
        with open(token_path, 'wb') as token:
            pickle.dump(creds, token)
        
        print("✅ OAuth flow completed successfully!")
        print("💾 Token saved to home/token.pickle")
        print("🎉 You can now use the email service!")
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        print("\n🔧 If you get a redirect_uri_mismatch error:")
        print("1. Go to Google Cloud Console")
        print("2. Add http://localhost:55691/ to your redirect URIs")
        print("3. Wait a few minutes for changes to take effect")

if __name__ == "__main__":
    main() 