@echo off
cd /d "C:\Users\banan\.gemini\antigravity\scratch\renfaire-ticket-scout"
echo Opening Chrome for Testing so you can log into Facebook...
echo After logging in, simply close the Chrome window!
"%USERPROFILE%\AppData\Local\ms-playwright\chromium-1248\chrome-win64\chrome.exe" --user-data-dir="C:\Users\banan\.gemini\antigravity\scratch\renfaire-ticket-scout\.antigravity_chrome_profile" "https://www.facebook.com/login"
