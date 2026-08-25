Write-Host "Starting SAB web server..." -ForegroundColor Cyan
Write-Host "Open http://localhost:3000 in your browser" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop" -ForegroundColor Gray
Write-Host ""
python -m sab web --port 3000
