import os
import sys
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import json

# Expects the service account JSON key to be in the environment variable 'GDRIVE_SERVICE_ACCOUNT_KEY'
# or as a file path provided as an argument (for local testing)
SERVICE_ACCOUNT_ENV_VAR = 'GDRIVE_SERVICE_ACCOUNT_KEY'
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def authenticate():
    creds = None
    if SERVICE_ACCOUNT_ENV_VAR in os.environ:
        try:
            # Parse the JSON string from the environment variable
            service_account_info = json.loads(os.environ[SERVICE_ACCOUNT_ENV_VAR])
            creds = service_account.Credentials.from_service_account_info(
                service_account_info, scopes=SCOPES)
        except json.JSONDecodeError:
           print(f"Error: {SERVICE_ACCOUNT_ENV_VAR} environment variable is not valid JSON.")
           sys.exit(1)
    else:
        print(f"Error: Environment variable {SERVICE_ACCOUNT_ENV_VAR} not found.")
        sys.exit(1)
    
    return creds

def upload_file(file_path, folder_id=None):
    creds = authenticate()
    service = build('drive', 'v3', credentials=creds)

    # Print the service account email for debugging
    try:
        about = service.about().get(fields="user(emailAddress)").execute()
        print(f"Authenticated as: {about['user']['emailAddress']}")
        
        # DEBUG: List all folders this account can see
        print("\n=== DEBUG: Visible Folders ===")
        results = service.files().list(
            q="mimeType = 'application/vnd.google-apps.folder' and trashed = false",
            pageSize=10, fields="nextPageToken, files(id, name)").execute()
        items = results.get('files', [])
        if not items:
            print("No visible folders found. ensure you have shared the folder with the service account.")
        else:
            for item in items:
                print(f"Found folder: {item['name']} ({item['id']})")
        print("==============================\n")

    except Exception as e:
        print(f"Could not determine Service Account details: {e}")

    if folder_id:
        # Sanitize folder_id in case user pasted the full URL
        folder_id = folder_id.strip()
        if "drive.google.com" in folder_id:
            parts = folder_id.split("/")
            # Get the last non-empty part
            folder_id = [p for p in parts if p.strip()][-1]
            if "?" in folder_id:
                folder_id = folder_id.split("?")[0]
        
        # Print masked folder ID for debugging
        masked_id = folder_id[:4] + "..." + folder_id[-4:] if len(folder_id) > 8 else "***"
        print(f"Using Folder ID: {masked_id}")

        try:
            # Verify folder exists and is accessible
            service.files().get(fileId=folder_id).execute()
            print(f"Target folder '{masked_id}' found and accessible.")
        except Exception as e:
            print(f"Error: Target folder with ID '{masked_id}' not found or not accessible.")
            print(f"Details: {e}")
            print("Please ensure the folder exists and is shared with the Service Account email.")
            sys.exit(1)

    file_name = os.path.basename(file_path)
    
    file_metadata = {'name': file_name}
    if folder_id:
        file_metadata['parents'] = [folder_id]

    media = MediaFileUpload(file_path, resumable=True)

    try:
        # Check if file already exists in the folder to update it instead of creating a duplicate
        if folder_id:
             query = f"name = '{file_name}' and '{folder_id}' in parents and trashed = false"
             results = service.files().list(q=query, fields="files(id)").execute()
             items = results.get('files', [])
             
             if items:
                 # Update existing file
                 file_id = items[0]['id']
                 print(f"File '{file_name}' already exists with ID: {file_id}. Updating...")
                 # When updating, we don't need 'parents' in metadata usually, 
                 # but we might want to keep the name.
                 # Using the update method:
                 updated_file = service.files().update(
                     fileId=file_id,
                     media_body=media
                 ).execute()
                 print(f"File updated. ID: {updated_file.get('id')}")
                 return

        # Create new file
        print(f"Uploading '{file_name}'...")
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        print(f"File uploaded. ID: {file.get('id')}")

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
    # Alternatively, you can set the folder ID in the environment or hardcode it here
    # if target_folder_id is None:
    #     target_folder_id = os.environ.get('GDRIVE_FOLDER_ID')

    if not os.path.exists(file_to_upload):
        print(f"Error: File '{file_to_upload}' not found.")
        sys.exit(1)

    upload_file(file_to_upload, target_folder_id)
