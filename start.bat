@echo off
echo Starting SAB web server...
echo Open http://localhost:3000 in your browser
echo Press Ctrl+C to stop
echo.
python -m sab web --port 3000
pause
