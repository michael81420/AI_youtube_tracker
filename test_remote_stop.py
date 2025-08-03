#!/usr/bin/env python3
"""
Test script for remote stop functionality.
"""

import asyncio
import subprocess
import time
import sys

async def test_remote_stop():
    """Test the remote stop functionality."""
    print("Testing remote stop functionality...")
    
    # Start the system in background
    print("1. Starting YouTube Tracker in background...")
    start_process = subprocess.Popen(
        [sys.executable, "main.py", "start"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Wait a bit for system to start
    await asyncio.sleep(3)
    
    # Check if process is still running
    if start_process.poll() is not None:
        print("ERROR: Start process exited early")
        return False
    
    print("2. System started, checking status...")
    
    # Check status
    status_result = subprocess.run(
        [sys.executable, "main.py", "status"],
        capture_output=True,
        text=True
    )
    
    if "Running: Yes" in status_result.stdout:
        print("[SUCCESS] Status shows system is running")
    else:
        print("[ERROR] Status shows system is not running")
        print("Status output:", status_result.stdout)
    
    print("3. Sending stop signal...")
    
    # Send stop command
    stop_result = subprocess.run(
        [sys.executable, "main.py", "stop"],
        capture_output=True,
        text=True
    )
    
    print("Stop command output:", stop_result.stdout)
    
    # Wait for process to stop
    try:
        start_process.wait(timeout=10)
        print("[SUCCESS] Start process exited successfully")
        return True
    except subprocess.TimeoutExpired:
        print("[ERROR] Start process did not exit within 10 seconds")
        start_process.terminate()
        return False

if __name__ == "__main__":
    asyncio.run(test_remote_stop())