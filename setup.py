"""Setup script for News Town."""
import subprocess
import sys
from pathlib import Path


def run_command(cmd: str, cwd: Path = None):
    """Run a shell command."""
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result.stdout


def main():
    """Set up News Town environment."""
    print("🏗️  Setting up News Town...")
    
    # Check Python version
    if sys.version_info < (3, 12):
        print("❌ Python 3.12 or higher is required")
        sys.exit(1)
    print("✅ Python version OK")
    
    # Create virtual environment if it doesn't exist
    if not Path("venv").exists():
        print("\n📦 Creating virtual environment...")
        run_command(f"{sys.executable} -m venv venv")
    else:
        print("✅ Virtual environment exists")
    
    # Determine pip command
    if sys.platform == "win32":
        pip_cmd = "venv\\Scripts\\pip"
        python_cmd = "venv\\Scripts\\python"
    else:
        pip_cmd = "venv/bin/pip"
        python_cmd = "venv/bin/python"
    
    # Install dependencies
    print("\n📥 Installing dependencies...")
    run_command(f"{pip_cmd} install -r requirements.txt")
    print("✅ Dependencies installed")
    
    # Check for .env file
    if not Path(".env").exists():
        print("\n⚠️  No .env file found")
        print("📝 Please copy .env.example to .env and add your API keys:")
        print("   - DATABASE_URL")
        print("   - OPENAI_API_KEY")
        print("   - ANTHROPIC_API_KEY")
        return
    print("✅ .env file found")
    
    # Check database
    print("\n🗄️  Checking database...")
    print("   Make sure PostgreSQL is running and create the database:")
    print("   psql -c 'CREATE DATABASE newstown;'")
    print("\n   Then run migrations:")
    print(f"   {python_cmd} -m db.migrate")
    
    print("\n✅ Setup complete!")
    print("\n🚀 To start News Town:")
    print(f"   {python_cmd} main.py")


if __name__ == "__main__":
    main()
