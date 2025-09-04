# Deployment script voor GitHub Pages site

git add .
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
git commit -m "Update site on $timestamp"
git pull origin main --rebase
git push origin main