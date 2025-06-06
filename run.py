import uiautomator2 as u2
import time
import os

d = u2.connect()  # auto connects to your device via adb

hashtag = "realhustle"

os.system("adb shell am force-stop com.instagram.android")
time.sleep(2)
os.system("adb shell am start -n com.instagram.android/.activity.MainTabActivity")
time.sleep(6)

print("Tapping Search tab")
d.click(350, 2100)  # Adjust for your device
time.sleep(2)

print("Tapping Search bar")
d.click(100, 250)
time.sleep(1)
d.click(100, 250)
time.sleep(1)

print(f"Typing hashtag {hashtag}")
d(focused=True).set_text(f"#{hashtag}") # Use faster input method for typing

time.sleep(1)

print("Pressing Enter")
d.press("enter")
time.sleep(6)

print("✅ Done searching hashtag.")