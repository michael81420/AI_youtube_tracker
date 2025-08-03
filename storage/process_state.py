"""
Process state management for inter-process communication.
"""

import json
import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class ProcessStateManager:
    """Manages process state using file-based storage."""
    
    def __init__(self, state_dir: str = "./data"):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(exist_ok=True)
        self.state_file = self.state_dir / "process_state.json"
        self.pid_file = self.state_dir / "youtube_tracker.pid"
        self.stop_signal_file = self.state_dir / "stop_signal.flag"
    
    def write_state(self, state: Dict[str, Any]) -> None:
        """Write current process state to file."""
        try:
            state_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "pid": os.getpid(),
                **state
            }
            
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, indent=2)
                
            # Write PID file
            with open(self.pid_file, 'w') as f:
                f.write(str(os.getpid()))
                
        except Exception as e:
            logger.error(f"Failed to write process state: {e}")
    
    def read_state(self) -> Optional[Dict[str, Any]]:
        """Read current process state from file."""
        try:
            if not self.state_file.exists():
                return None
                
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
            
            # Check if process is still running
            if not self._is_process_running(state_data.get("pid")):
                self.cleanup_state()
                return None
                
            return state_data
            
        except Exception as e:
            logger.error(f"Failed to read process state: {e}")
            return None
    
    def cleanup_state(self) -> None:
        """Clean up state files."""
        try:
            if self.state_file.exists():
                self.state_file.unlink()
            if self.pid_file.exists():
                self.pid_file.unlink()
            if self.stop_signal_file.exists():
                self.stop_signal_file.unlink()
        except Exception as e:
            logger.error(f"Failed to cleanup state: {e}")
    
    def send_stop_signal(self) -> bool:
        """Send stop signal to running process."""
        try:
            # Check if process is running
            state = self.read_state()
            if not state:
                return False
                
            # Create stop signal file
            with open(self.stop_signal_file, 'w') as f:
                f.write(str(datetime.utcnow().isoformat()))
            
            return True
        except Exception as e:
            logger.error(f"Failed to send stop signal: {e}")
            return False
    
    def check_stop_signal(self) -> bool:
        """Check if stop signal has been sent."""
        try:
            return self.stop_signal_file.exists()
        except Exception as e:
            logger.error(f"Failed to check stop signal: {e}")
            return False
    
    def clear_stop_signal(self) -> None:
        """Clear the stop signal."""
        try:
            if self.stop_signal_file.exists():
                self.stop_signal_file.unlink()
        except Exception as e:
            logger.error(f"Failed to clear stop signal: {e}")
    
    def _is_process_running(self, pid: Optional[int]) -> bool:
        """Check if a process is still running."""
        if pid is None:
            return False
            
        try:
            # On Windows
            import psutil
            return psutil.pid_exists(pid)
        except ImportError:
            # Fallback for systems without psutil
            try:
                os.kill(pid, 0)
                return True
            except (OSError, ProcessLookupError):
                return False

# Global instance
process_state_manager = ProcessStateManager()