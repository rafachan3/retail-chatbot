import os
import shutil

# Change this to your main folder path
main_folder = "recommendation/images"

# Loop through everything inside the main folder
for root, dirs, files in os.walk(main_folder, topdown=False):
    # Skip the main folder itself
    if root == main_folder:
        continue
    
    # Move files to main folder
    for file in files:
        src = os.path.join(root, file)
        dst = os.path.join(main_folder, file)
        
        shutil.move(src, dst)
    
    # Remove the empty folder
    shutil.rmtree(root)

print("✅ All subfolders removed. Files are now in the main folder.")
