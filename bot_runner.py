import subprocess
import sys
import os

print("🤖 Bot Runner - Starting...")
print(f"Python: {sys.executable}")
print(f"Working dir: {os.getcwd()}")

# Verifică că API key-ul există
api_key = os.getenv("TYPEFULLY_API_KEY", "")
print(f"API Key loaded: {'YES' if api_key else 'NO'}")
print(f"API Key length: {len(api_key)}")
print(f"API Key first 10: {api_key[:10] if api_key else 'EMPTY'}")

print("\n" + "="*60)
print("Running typefully_bot.py...")
print("="*60 + "\n")

# Rulează botul ca subprocess separat
result = subprocess.run(
    [sys.executable, "typefully_bot.py"],
    env=os.environ.copy(),  # Pass environment variables
    capture_output=True,
    text=True
)

# Print output
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr, file=sys.stderr)

# Exit with same code
sys.exit(result.returncode)