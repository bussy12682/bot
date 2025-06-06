import uiautomator2 as u2
import time

d = u2.connect()

print("🚀 Tapping bottom nav bar in small steps to find Search button...")

for x in range(100, 600, 25):  # More precise than before
    print(f"🟡 Tapping x={x}, y=2400")
    d.click(x, 2400)
    time.sleep(2)
    response = input("❓ Did it open Search/Explore page? (yes/no): ").strip().lower()
    if response == "yes":
        print(f"✅ Found the Search tab at x={x}, y=2400")
        break