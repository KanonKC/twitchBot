rm -rf dist/*
pyinstaller --noconsole --onefile main.py
echo "✅ Build complete"