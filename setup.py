#!/usr/bin/env python3
"""
Setup script for Delta Exchange Dashboard
"""

import os
import sys
import subprocess
from pathlib import Path

def install_requirements():
    """Install required packages"""
    print("📦 Installing required packages...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Packages installed successfully!")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install packages: {e}")
        return False
    return True

def check_env_file():
    """Check if .env file exists and has required variables"""
    env_file = Path(".env")
    
    if not env_file.exists():
        print("📝 Creating .env file from template...")
        try:
            # Copy from .env.example
            example_file = Path(".env.example")
            if example_file.exists():
                with open(example_file, 'r') as f:
                    content = f.read()
                with open(env_file, 'w') as f:
                    f.write(content)
                print("✅ .env file created!")
                print("⚠️  Please edit .env file and add your API credentials before running the app.")
                return False
            else:
                print("❌ .env.example file not found!")
                return False
        except Exception as e:
            print(f"❌ Failed to create .env file: {e}")
            return False
    
    # Check if required variables are set
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv('DELTA_API_KEY')
    api_secret = os.getenv('DELTA_API_SECRET')
    
    if not api_key or not api_secret or api_key == 'your_api_key_here':
        print("⚠️  Please set your DELTA_API_KEY and DELTA_API_SECRET in the .env file")
        return False
    
    print("✅ Environment variables configured!")
    return True

def run_streamlit():
    """Run the Streamlit application"""
    print("🚀 Starting Streamlit application...")
    try:
        subprocess.run([sys.executable, "-m", "streamlit", "run", "streamlit_app.py"])
    except KeyboardInterrupt:
        print("\n👋 Application stopped by user")
    except Exception as e:
        print(f"❌ Failed to start application: {e}")

def main():
    """Main setup function"""
    print("🔧 Setting up Delta Exchange Dashboard...")
    print("=" * 50)
    
    # Install requirements
    if not install_requirements():
        return
    
    print("\n" + "=" * 50)
    
    # Check environment
    env_ready = check_env_file()
    
    print("\n" + "=" * 50)
    
    if env_ready:
        print("🎉 Setup complete! Starting application...")
        run_streamlit()
    else:
        print("📋 Setup Instructions:")
        print("1. Edit the .env file and add your Delta Exchange API credentials")
        print("2. Run this script again or use: streamlit run streamlit_app.py")
        print("\n💡 You can get API keys from: https://www.delta.exchange/app/account/api")

if __name__ == "__main__":
    main()
