# OAuth2 Setup for mocdatapty@gmail.com Account

This guide will help you set up OAuth2 authentication for the `mocdatapty@gmail.com` account to send emails through the E-Click system.

## ⚠️ IMPORTANT: No SMTP Fallback

The system has been configured to **ONLY use OAuth2** for the `mocdatapty@gmail.com` account. There is **NO fallback** to SMTP or any other email method.

## Prerequisites

1. Access to the `mocdatapty@gmail.com` Google account
2. Access to Google Cloud Console
3. Python 3.7+ with required packages

## Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Note down your Project ID

## Step 2: Enable Gmail API

1. In your Google Cloud project, go to "APIs & Services" > "Library"
2. Search for "Gmail API"
3. Click on "Gmail API" and then click "Enable"

## Step 3: Create OAuth2 Credentials

1. Go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "OAuth 2.0 Client IDs"
3. Choose "Desktop application" as the application type
4. Fill in the details:
   - Name: `E-Click Email Service - mocdatapty`
   - Description: `OAuth2 client for E-Click email functionality using mocdatapty@gmail.com`
5. Click "Create"

## Step 4: Download and Configure Credentials

1. After creating the OAuth2 client, click "Download JSON"
2. Rename the downloaded file to `credentials.json`
3. **Place the `credentials.json` file in the `home/` directory** of your Django project
4. **DO NOT commit this file to version control**

## Step 5: Configure Gmail Account

1. Log into `mocdatapty@gmail.com`
2. Enable "Less secure app access" (for testing) or set up OAuth2 properly
3. If using a Google Workspace account, ensure API access is enabled

## Step 6: Test OAuth2 Authentication

1. Start your Django development server
2. Try to send a project report
3. The system will open a browser window for OAuth2 authentication
4. Log in with `mocdatapty@gmail.com` credentials
5. Grant the necessary permissions

## File Structure

After setup, your project should have:

```
Django-E-Click-master/
├── home/
│   ├── credentials.json          # Your OAuth2 credentials (DO NOT commit)
│   ├── credentials_template.json # Template file (safe to commit)
│   ├── services.py              # Email service (updated)
│   └── ...
├── eclick/
│   └── settings.py              # Updated with OAuth2 config
└── OAUTH2_SETUP_MOCDATAPTY.md   # This file
```

## Troubleshooting

### "OAuth2 Gmail service not initialized" Error

This means the `credentials.json` file is missing or invalid:

1. **Check file location**: Ensure `credentials.json` is in the `home/` directory
2. **Verify file format**: The file should contain valid JSON with OAuth2 credentials
3. **Check permissions**: Ensure the file is readable by the Django application

### "Invalid credentials" Error

1. **Verify OAuth2 setup**: Ensure the credentials were created correctly in Google Cloud Console
2. **Check scopes**: Ensure the Gmail API is enabled and the correct scopes are configured
3. **Re-authenticate**: Delete the `token.pickle` file and re-authenticate

### "Permission denied" Error

1. **Check account access**: Ensure `mocdatapty@gmail.com` has access to the Google Cloud project
2. **Verify API enablement**: Ensure Gmail API is enabled in the project
3. **Check OAuth consent screen**: Ensure the OAuth consent screen is configured

## Security Notes

1. **Never commit credentials to version control**
   - Add `credentials.json` to your `.gitignore` file
   - Use environment variables for sensitive data in production

2. **Use environment variables in production**
   ```python
   import os
   
   GOOGLE_OAUTH2_CLIENT_ID = os.environ.get('GOOGLE_OAUTH2_CLIENT_ID')
   GOOGLE_OAUTH2_CLIENT_SECRET = os.environ.get('GOOGLE_OAUTH2_CLIENT_SECRET')
   ```

3. **Regular credential rotation**
   - Rotate your OAuth2 client secrets regularly
   - Monitor API usage in Google Cloud Console

## Next Steps

Once OAuth2 is working:

1. **Test email functionality**: Send a test project report
2. **Verify sender email**: Ensure emails are sent from `mocdatapty@gmail.com`
3. **Monitor usage**: Check Google Cloud Console for API usage
4. **Set up monitoring**: Configure alerts for API quotas and errors

## Support

If you encounter issues:

1. Check the Django logs for error messages
2. Verify your Google Cloud project settings
3. Test with the provided test email functionality
4. Review Google Cloud Console for API usage and errors
5. Ensure `mocdatapty@gmail.com` has proper access and permissions
