# Create Deployment Package Script
# This script creates a clean deployment package for the Django E-Click project

Write-Host "Creating deployment package..." -ForegroundColor Green

# Create deployment directory
$deploymentDir = "deployment_package"
if (Test-Path $deploymentDir) {
    Remove-Item -Recurse -Force $deploymentDir
}
New-Item -ItemType Directory -Path $deploymentDir

# Copy project files (excluding database and media)
$excludePatterns = @(
    "*.sqlite3",
    "*.db", 
    "media/*",
    "staticfiles/*",
    "__pycache__/*",
    "*.pyc",
    ".git/*",
    "backups/*",
    "*.log",
    "*.tmp",
    "*.temp"
)

# Copy main project files
Copy-Item -Path "eclick" -Destination "$deploymentDir/" -Recurse -Force
Copy-Item -Path "home" -Destination "$deploymentDir/" -Recurse -Force
Copy-Item -Path "main" -Destination "$deploymentDir/" -Recurse -Force
Copy-Item -Path "templates" -Destination "$deploymentDir/" -Recurse -Force
Copy-Item -Path "static" -Destination "$deploymentDir/" -Recurse -Force

# Copy configuration files
Copy-Item -Path "manage.py" -Destination "$deploymentDir/" -Force
Copy-Item -Path "requirements.txt" -Destination "$deploymentDir/" -Force
Copy-Item -Path "requirements.production.txt" -Destination "$deploymentDir/" -Force
Copy-Item -Path "gunicorn.conf.py" -Destination "$deploymentDir/" -Force
Copy-Item -Path "nginx.conf" -Destination "$deploymentDir/" -Force
Copy-Item -Path "eclick.service" -Destination "$deploymentDir/" -Force
Copy-Item -Path "deploy.sh" -Destination "$deploymentDir/" -Force
Copy-Item -Path "DEPLOYMENT.md" -Destination "$deploymentDir/" -Force
Copy-Item -Path "README.md" -Destination "$deploymentDir/" -Force

# Create empty media and staticfiles directories
New-Item -ItemType Directory -Path "$deploymentDir/media" -Force
New-Item -ItemType Directory -Path "$deploymentDir/staticfiles" -Force

# Create .gitkeep files to preserve empty directories
New-Item -ItemType File -Path "$deploymentDir/media/.gitkeep" -Force
New-Item -ItemType File -Path "$deploymentDir/staticfiles/.gitkeep" -Force

# Remove __pycache__ directories from copied files
Get-ChildItem -Path $deploymentDir -Recurse -Directory -Name "__pycache__" | ForEach-Object {
    Remove-Item -Recurse -Force "$deploymentDir/$_"
}

# Remove .pyc files
Get-ChildItem -Path $deploymentDir -Recurse -Filter "*.pyc" | Remove-Item -Force

Write-Host "Deployment package created in: $deploymentDir" -ForegroundColor Green
Write-Host "Package size: $((Get-ChildItem -Path $deploymentDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB) MB" -ForegroundColor Yellow

# Create zip file
$zipPath = "eclick-deployment.zip"
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}

Compress-Archive -Path "$deploymentDir/*" -DestinationPath $zipPath

Write-Host "Deployment zip created: $zipPath" -ForegroundColor Green
Write-Host "Zip file size: $((Get-Item $zipPath).Length / 1MB) MB" -ForegroundColor Yellow

Write-Host "Deployment package ready!" -ForegroundColor Green
