import os
import time

# Step 1: Launch Instagram
os.system("adb shell am start -n com.instagram.android/.activity.MainTabActivity")
time.sleep(8)

# Step 2: Tap bottom search tab
os.system("adb shell input tap 180 1515")
time.sleep(3)

# Step 3: Tap the top search input field (Y value depends on your device screen)
# Try a slightly lower Y coordinate than before (e.g., 250–300)
os.system("adb shell input tap 350 160")
time.sleep(2)

# Step 4: Type the hashtag #grindseason
os.system('adb shell input text "%23grindseason"')
time.sleep(2)

# Step 5: Tap first search result (adjust Y if needed)
os.system("adb shell input tap 360 500")
