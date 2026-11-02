1.Download the Official Installer:1 min.Download the correct interactive installer package from the Google Cloud SDK Documentation. Alternatively, run this command in PowerShell to fetch it automatically:PowerShell(New-Object Net.WebClient).DownloadFile("https://dl.google.com/dl/cloudsdk/channels/rapid/GoogleCloudSDKInstaller.exe", "$env:Temp\GoogleCloudSDKInstaller.exe")
& $env:Temp\GoogleCloudSDKInstaller.exe
Verification: Ensure the setup wizard opens successfully on your desktop.2.Run Through Setup:2-3 min.Complete the installation wizard steps. Keep the options checked to Add to PATH, Install bundled Python, and leave the box checked to Start gcloud init when the installation finishes.Verification: A terminal window should automatically launch running initialization scripts once the installer completes.3.Authorize Your Account:1 min.If the initialization window didn't open automatically, open your terminal (Command Prompt or PowerShell) and run:Bashgcloud init
Follow the browser prompt that appears to sign in with your Google account, and click Allow to grant permissions.Verification: Run gcloud auth list in your terminal to confirm your active account is listed.How to Install Google Cloud SDK (GCP CLI) on Windows 11









# 1. Define the temporary folder and installer path
$TempDir = "$env:TEMP\gcloud-install"
$InstallerPath = Join-Path $TempDir "google-cloud-sdk.msi"

# 2. Create the directory if it doesn't exist
New-Item -ItemType Directory -Force -Path $TempDir | Out-Null

# 3. Download the latest MSI
Write-Host "Downloading Google Cloud SDK..." -ForegroundColor Yellow
$uri = "https://dl.google.com/dl/cloudsdk/channels/rapid/google-cloud-sdk-latest-x64.msi"
Invoke-WebRequest -Uri $uri -OutFile $InstallerPath -UseBasicParsing

# 4. Install silently (mquiet = quiet, /qb = basic UI, REBOOT=ReallySuppress = no reboot prompt)
Write-Host "Installing..." -ForegroundColor Yellow
Start-Process msiexec.exe -ArgumentList "/i", $InstallerPath, "/qn", "REBOOT=ReallySuppress", "/norestart" -Wait

# 5. Cleanup
Remove-Item -Recurse -Force $TempDir

Write-Host "Installation Complete!" -ForegroundColor Green
Write-Host "Please restart your PowerShell terminal and run: gcloud version" -ForegroundColor Cyan