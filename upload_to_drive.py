import os
import sys
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ['https://www.googleapis.com/auth/drive']


def authenticate():
    """Authenticate using OAuth refresh token (works with personal Google accounts)."""
    client_id = os.environ.get('GDRIVE_CLIENT_ID')
    client_secret = os.environ.get('GDRIVE_CLIENT_SECRET')
    refresh_token = os.environ.get('GDRIVE_REFRESH_TOKEN')

    if not all([client_id, client_secret, refresh_token]):
        print("Error: Missing environment variables.")
        print("Required: GDRIVE_CLIENT_ID, GDRIVE_CLIENT_SECRET, GDRIVE_REFRESH_TOKEN")
        sys.exit(1)

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri='https://oauth2.googleapis.com/token',
        scopes=SCOPES
    )

    # Refresh the access token
    creds.refresh(Request())
    return creds


def upload_file(file_path, folder_id=None):
    creds = authenticate()
    service = build('drive', 'v3', credentials=creds)

    # Print account info for debugging
    try:
        about = service.about().get(fields="user(emailAddress)").execute()
        print(f"Authenticated as: {about['user']['emailAddress']}")
    except Exception as e:
        print(f"Could not determine account details: {e}")

    if folder_id:
        folder_id = folder_id.strip()
        if "drive.google.com" in folder_id:
            parts = folder_id.split("/")
            folder_id = [p for p in parts if p.strip()][-1]
            if "?" in folder_id:
                folder_id = folder_id.split("?")[0]

        masked_id = folder_id[:4] + "..." + folder_id[-4:] if len(folder_id) > 8 else "***"
        print(f"Using Folder ID: {masked_id}")

        try:
            service.files().get(fileId=folder_id).execute()
            print(f"Target folder found and accessible.")
        except Exception as e:
            print(f"Error: Folder '{masked_id}' not found or not accessible.")
            print(f"Details: {e}")
            sys.exit(1)

    file_name = os.path.basename(file_path)
    media = MediaFileUpload(file_path, resumable=True)

    try:
        # Check if file already exists to update instead of duplicating
        if folder_id:
            query = f"name = '{file_name}' and '{folder_id}' in parents and trashed = false"
            results = service.files().list(q=query, fields="files(id)").execute()
            existing = results.get('files', [])

            if existing:
                file_id = existing[0]['id']
                print(f"File '{file_name}' already exists. Updating...")
                updated_file = service.files().update(
                    fileId=file_id,
                    media_body=media
                ).execute()
                print(f"File updated. ID: {updated_file.get('id')}")
                return

        # Upload new file
        print(f"Uploading '{file_name}'...")
        file_metadata = {'name': file_name}
        if folder_id:
            file_metadata['parents'] = [folder_id]

        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        print(f"File uploaded successfully. ID: {file.get('id')}")

    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python upload_to_drive.py <file_path> [folder_id]")
        sys.exit(1)

    file_to_upload = sys.argv[1]

    target_folder_id = None
    if len(sys.argv) > 2:
        target_folder_id = sys.argv[2]

    if not os.path.exists(file_to_upload):
        print(f"Error: File '{file_to_upload}' not found.")
        sys.exit(1)

    upload_file(file_to_upload, target_folder_id)
