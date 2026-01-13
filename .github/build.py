import os
import zipfile

archives = {
    "linux-nopython.zip": ["Cassette.py", "Cassette.sh", "requirements.txt", "version", "System"],
    "windows-python.zip": ["Cassette.py", "Cassette.bat", "version", "requirements.txt", "System", "python"],
    "windows-nopython.zip": ["Cassette.py", "Cassette-nopython.bat", "requirements.txt", "version", "System"]
}

def zip_items(archive_name, items):
    with zipfile.ZipFile(archive_name, "w", zipfile.ZIP_DEFLATED) as zipf:
        for item in items:
            if os.path.isfile(item):
                zipf.write(item, arcname=os.path.basename(item))
            
            elif os.path.isdir(item):
                for root, _, files in os.walk(item):
                    for file in files:
                        filepath = os.path.join(root, file)
                        arcname = os.path.relpath(filepath, start=os.path.dirname(item))
                        zipf.write(filepath, arcname=arcname)
            
            else:
                print(f"⚠️ {item} not found.")

def main():
    for archive_name, items in archives.items():
        print(f"Creating {archive_name}...")
        zip_items(archive_name, items)

if __name__ == "__main__":
    main()