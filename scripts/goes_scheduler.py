#!/usr/bin/env python3
"""
GOES Scheduler Service

Replaces blind polling with predictive scheduling based on learned arrival times.
Handles failure tracking and automatic relearning after consecutive failures.
Generates composite images from raw channel data.

Features:
- Schedule Learning: Observes frame arrivals and learns the publication interval
- Predictive Polling: Sleeps until expected arrival time instead of constant polling
- Resilience: Tracks failures and relearns schedule after 3 consecutive misses
- Composites: Generates Nighttime Microphysics, Day Convection, and Split Window

Configuration: /etc/goes-scheduler.json
State: /var/lib/goes-publisher/schedule_state.json
"""

import glob
import json
import logging
import os
import re
import shutil
import signal
import statistics
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

# Import composite generation
from goes_composites import generate_all_composites

# ============================================================================
# Configuration
# ============================================================================

DEFAULT_CONFIG = {
    "satellites": {
        "GOES-19": {
            "root": "/home/pi/sat/GOES-19/IMAGES/GOES-19/Full Disk",
            "anchor": "product.cbor",
            "channels": {
                "CH2": "G19_2_*.png",
                "CH7": "G19_7_*.png",
                "CH8": "G19_8_*.png",
                "CH13": "G19_13_*.png"
            }
        }
    },
    "composites": {
        "nighttime_microphysics": True,
        "day_convection": True,
        "split_window": True
    },
    "schedule": {
        "learning_observations": 6,
        "relearn_threshold": 3,
        "tolerance_min_seconds": 30,
        "tolerance_max_seconds": 120,
        "default_interval_seconds": 600,
        "fallback_poll_seconds": 60
    },
    "retention_days": 2,
    "web_root": "/var/www/goes",
    "state_file": "/var/lib/goes-publisher/schedule_state.json",
    "config_file": "/etc/goes-scheduler.json"
}

# ============================================================================
# Logging
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('goes-scheduler')

# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class Observation:
    """A single frame arrival observation."""
    timestamp_dir: str
    arrival_utc: str


@dataclass
class SatelliteState:
    """State for a single satellite's schedule."""
    learned_interval_seconds: float = 600.0
    interval_stddev_seconds: float = 0.0
    last_arrival_utc: Optional[str] = None
    next_expected_utc: Optional[str] = None
    observations: List[Dict] = field(default_factory=list)
    consecutive_failures: int = 0
    last_published_dir: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            'learned_interval_seconds': self.learned_interval_seconds,
            'interval_stddev_seconds': self.interval_stddev_seconds,
            'last_arrival_utc': self.last_arrival_utc,
            'next_expected_utc': self.next_expected_utc,
            'observations': self.observations,
            'consecutive_failures': self.consecutive_failures,
            'last_published_dir': self.last_published_dir
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'SatelliteState':
        return cls(
            learned_interval_seconds=data.get('learned_interval_seconds', 600.0),
            interval_stddev_seconds=data.get('interval_stddev_seconds', 0.0),
            last_arrival_utc=data.get('last_arrival_utc'),
            next_expected_utc=data.get('next_expected_utc'),
            observations=data.get('observations', []),
            consecutive_failures=data.get('consecutive_failures', 0),
            last_published_dir=data.get('last_published_dir')
        )


@dataclass
class SchedulerState:
    """Global scheduler state."""
    version: int = 1
    mode: str = "learning"  # "learning", "learned", "relearning"
    satellites: Dict[str, SatelliteState] = field(default_factory=dict)
    updated_utc: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            'version': self.version,
            'mode': self.mode,
            'satellites': {k: v.to_dict() for k, v in self.satellites.items()},
            'updated_utc': self.updated_utc
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'SchedulerState':
        state = cls(
            version=data.get('version', 1),
            mode=data.get('mode', 'learning'),
            updated_utc=data.get('updated_utc')
        )
        for sat_name, sat_data in data.get('satellites', {}).items():
            state.satellites[sat_name] = SatelliteState.from_dict(sat_data)
        return state

def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override into base. Dict values are merged recursively."""
    merged = base.copy()
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged

# ============================================================================
# Main Scheduler
# ============================================================================

class GoesScheduler:
    """Main scheduler service class."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config = self._load_config(config_path)
        self.state = self._load_state()
        self.running = True
        self._last_cleanup_utc = 0.0

        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def _load_config(self, config_path: Optional[Path] = None) -> Dict:
        """Load configuration from file or use defaults."""
        if config_path is None:
            config_path = Path(DEFAULT_CONFIG['config_file'])

        if config_path.exists():
            try:
                with open(config_path) as f:
                    user_config = json.load(f)
                # Deep merge so partial user configs don't clobber nested defaults
                config = _deep_merge(DEFAULT_CONFIG, user_config)
                logger.info(f"Loaded configuration from {config_path}")
                return config
            except Exception as e:
                logger.warning(f"Failed to load config from {config_path}: {e}")

        logger.info("Using default configuration")
        return DEFAULT_CONFIG.copy()

    def _load_state(self) -> SchedulerState:
        """Load scheduler state from file or create new."""
        state_path = Path(self.config['state_file'])

        if state_path.exists():
            try:
                with open(state_path) as f:
                    data = json.load(f)
                state = SchedulerState.from_dict(data)
                logger.info(f"Loaded state from {state_path}, mode={state.mode}")
                return state
            except Exception as e:
                logger.warning(f"Failed to load state from {state_path}: {e}")

        logger.info("Starting with fresh state in learning mode")
        return SchedulerState()

    def _save_state(self):
        """Persist scheduler state to file."""
        state_path = Path(self.config['state_file'])
        state_path.parent.mkdir(parents=True, exist_ok=True)

        self.state.updated_utc = datetime.now(timezone.utc).isoformat()

        try:
            # Write atomically via temp file
            tmp_path = state_path.with_suffix('.tmp')
            with open(tmp_path, 'w') as f:
                json.dump(self.state.to_dict(), f, indent=2)
            tmp_path.rename(state_path)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def _now_utc(self) -> datetime:
        """Get current UTC time."""
        return datetime.now(timezone.utc)

    def _parse_timestamp_dir(self, dirname: str) -> Optional[datetime]:
        """Parse timestamp directory name to datetime.

        Expected format: YYYY-MM-DD_HH-MM-SS
        """
        try:
            return datetime.strptime(dirname, "%Y-%m-%d_%H-%M-%S").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            return None

    def _find_newest_complete_dir(self, sat_config: Dict) -> Optional[str]:
        """Find the newest directory containing anchor file and all channels.

        Args:
            sat_config: Satellite configuration dict

        Returns:
            Directory name (not full path) or None
        """
        root = Path(sat_config['root'])
        anchor = sat_config['anchor']
        channels = sat_config['channels']

        if not root.exists():
            logger.debug(f"Satellite root does not exist: {root}")
            return None

        # List directories, sort by name descending (newest first)
        try:
            dirs = sorted(
                [d.name for d in root.iterdir() if d.is_dir()],
                reverse=True
            )
        except Exception as e:
            logger.error(f"Failed to list directories in {root}: {e}")
            return None

        for dirname in dirs:
            dir_path = root / dirname

            # Check anchor file exists
            if not (dir_path / anchor).exists():
                continue

            # Check all channels exist
            all_channels_present = True
            for ch_name, ch_pattern in channels.items():
                matches = list(dir_path.glob(ch_pattern))
                if not matches:
                    all_channels_present = False
                    break

            if all_channels_present:
                return dirname

        return None

    def _get_channel_paths(self, sat_config: Dict, dirname: str) -> Dict[str, Path]:
        """Get paths to all channel files in a directory.

        Returns dict mapping channel name to file path.
        """
        root = Path(sat_config['root'])
        dir_path = root / dirname
        channels = sat_config['channels']

        paths = {}
        for ch_name, ch_pattern in channels.items():
            matches = list(dir_path.glob(ch_pattern))
            if matches:
                # Take first match (should only be one)
                paths[ch_name] = matches[0]

        return paths

    def _extract_timestamp_from_filename(self, path: Path) -> Optional[str]:
        """Extract timestamp from filename for output naming.

        Looks for pattern like _YYYYMMDDTHHMMSSZ in filename.
        """
        match = re.search(r'_(\d{8}T\d{6}Z)', path.name)
        if match:
            return match.group(1)
        return None

    def _record_arrival(self, sat_name: str, sat_state: SatelliteState,
                        dirname: str):
        """Record a new frame arrival for schedule learning."""
        now = self._now_utc()
        now_str = now.isoformat()

        # Add observation
        sat_state.observations.append({
            'timestamp_dir': dirname,
            'arrival_utc': now_str
        })

        # Keep only recent observations
        max_obs = self.config['schedule']['learning_observations'] * 2
        if len(sat_state.observations) > max_obs:
            sat_state.observations = sat_state.observations[-max_obs:]

        sat_state.last_arrival_utc = now_str
        sat_state.last_published_dir = dirname

        # Calculate schedule from observations
        self._update_schedule(sat_name, sat_state)

    def _update_schedule(self, sat_name: str, sat_state: SatelliteState):
        """Update learned schedule from observations."""
        sched_config = self.config['schedule']
        min_obs = sched_config['learning_observations']

        if len(sat_state.observations) < 2:
            logger.debug(f"{sat_name}: Not enough observations to learn schedule")
            return

        # Calculate intervals between observations
        intervals = []
        for i in range(1, len(sat_state.observations)):
            prev = datetime.fromisoformat(sat_state.observations[i-1]['arrival_utc'])
            curr = datetime.fromisoformat(sat_state.observations[i]['arrival_utc'])
            interval = (curr - prev).total_seconds()
            # Filter out unreasonably short or long intervals
            if 60 < interval < 3600:  # Between 1 min and 1 hour
                intervals.append(interval)

        if not intervals:
            logger.warning(f"{sat_name}: No valid intervals found")
            return

        # Calculate mean and stddev
        mean_interval = statistics.mean(intervals)
        stddev = statistics.stdev(intervals) if len(intervals) > 1 else 0.0

        sat_state.learned_interval_seconds = mean_interval
        sat_state.interval_stddev_seconds = stddev

        # Calculate next expected arrival
        if sat_state.last_arrival_utc:
            last = datetime.fromisoformat(sat_state.last_arrival_utc)
            next_expected = last.timestamp() + mean_interval
            sat_state.next_expected_utc = datetime.fromtimestamp(
                next_expected, tz=timezone.utc
            ).isoformat()

        logger.info(
            f"{sat_name}: Learned interval={mean_interval:.1f}s, "
            f"stddev={stddev:.1f}s, observations={len(sat_state.observations)}"
        )

        # Check if we can transition to learned mode
        if (self.state.mode in ('learning', 'relearning') and
            len(sat_state.observations) >= min_obs and
            stddev < 30.0):
            logger.info(f"Transitioning to 'learned' mode")
            self.state.mode = 'learned'

    def _is_overdue(self, sat_state: SatelliteState) -> bool:
        """Check if expected frame is overdue."""
        if not sat_state.next_expected_utc:
            return False

        sched_config = self.config['schedule']
        tolerance = min(
            max(sat_state.interval_stddev_seconds * 3, sched_config['tolerance_min_seconds']),
            sched_config['tolerance_max_seconds']
        )

        expected = datetime.fromisoformat(sat_state.next_expected_utc)
        deadline = expected.timestamp() + tolerance
        now = self._now_utc().timestamp()

        return now > deadline

    def _record_failure(self, sat_name: str, sat_state: SatelliteState):
        """Record a failure (expected frame didn't arrive)."""
        sat_state.consecutive_failures += 1
        threshold = self.config['schedule']['relearn_threshold']

        logger.warning(
            f"{sat_name}: Failure #{sat_state.consecutive_failures} "
            f"(threshold={threshold})"
        )

        if sat_state.consecutive_failures >= threshold:
            logger.error(
                f"{sat_name}: {threshold} consecutive failures, "
                f"entering relearning mode"
            )
            self.state.mode = 'relearning'
            sat_state.observations = []
            sat_state.learned_interval_seconds = self.config['schedule']['default_interval_seconds']
            sat_state.interval_stddev_seconds = 0.0
            sat_state.next_expected_utc = None

    def _publish_data(self, sat_name: str, sat_config: Dict, dirname: str):
        """Publish data to web directory."""
        web_root = Path(self.config['web_root'])
        sat_web_root = web_root / 'current' / sat_name
        sat_web_root.mkdir(parents=True, exist_ok=True)

        channel_paths = self._get_channel_paths(sat_config, dirname)

        # Copy channel files
        for ch_name, src_path in channel_paths.items():
            try:
                dst_path = sat_web_root / src_path.name
                shutil.copy2(src_path, dst_path)
                # Set permissions
                os.chmod(dst_path, 0o644)
                logger.debug(f"Published {src_path.name} to {dst_path}")
            except Exception as e:
                logger.error(f"Failed to publish {src_path}: {e}")

        return channel_paths

    def _cleanup_old_published(self, sat_name: str):
        """Remove published images older than retention_days."""
        retention_days = self.config.get('retention_days', 2)
        if retention_days <= 0:
            return

        web_root = Path(self.config['web_root'])
        sat_web_root = web_root / 'current' / sat_name
        if not sat_web_root.exists():
            return

        cutoff = self._now_utc() - timedelta(days=retention_days)
        cutoff_str = cutoff.strftime('%Y%m%dT%H%M%SZ')
        removed = 0

        for png in sat_web_root.glob('*.png'):
            # Extract timestamp from filename: ..._YYYYMMDDTHHMMSSZ.png
            match = re.search(r'_(\d{8}T\d{6}Z)', png.name)
            if not match:
                continue
            ts = match.group(1)
            # YYYYMMDDTHHMMSSZ sorts lexicographically == chronologically
            if ts < cutoff_str:
                try:
                    png.unlink()
                    removed += 1
                except Exception as e:
                    logger.error(f"Failed to remove old file {png}: {e}")

        if removed:
            logger.info(f"{sat_name}: Cleaned up {removed} published images older than {retention_days} days")

    def _maybe_run_cleanup(self):
        """Run cleanup for all satellites at most once per hour."""
        now = time.time()
        if now - self._last_cleanup_utc < 3600:
            return
        self._last_cleanup_utc = now
        for sat_name in self.config['satellites']:
            self._cleanup_old_published(sat_name)

    def _generate_composites(self, sat_name: str, channel_paths: Dict[str, Path]):
        """Generate composite images."""
        if not channel_paths:
            return

        web_root = Path(self.config['web_root'])
        output_dir = web_root / 'current' / sat_name

        # Extract timestamp from first channel file
        timestamp = None
        for path in channel_paths.values():
            timestamp = self._extract_timestamp_from_filename(path)
            if timestamp:
                break

        if not timestamp:
            timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

        try:
            outputs = generate_all_composites(
                channel_paths,
                output_dir,
                timestamp,
                enabled=self.config.get('composites', {})
            )

            # Set permissions on generated files
            for path in outputs.values():
                os.chmod(path, 0o644)

            logger.info(f"Generated {len(outputs)} composite(s) for {sat_name}")
        except Exception as e:
            logger.error(f"Failed to generate composites for {sat_name}: {e}")

    def _write_meta(self, dirname: str):
        """Write meta.json with current timestamp."""
        web_root = Path(self.config['web_root'])
        meta_path = web_root / 'meta.json'

        meta = {
            'timestamp_dir': dirname,
            'updated_utc': self._now_utc().isoformat(),
            'mode': self.state.mode
        }

        try:
            with open(meta_path, 'w') as f:
                json.dump(meta, f, indent=2)
            os.chmod(meta_path, 0o644)
        except Exception as e:
            logger.error(f"Failed to write meta.json: {e}")

    def _notify_update(self):
        """Touch trigger file to notify SSE service."""
        trigger_path = Path(self.config['web_root']) / '.trigger'
        try:
            trigger_path.touch()
        except Exception as e:
            logger.error(f"Failed to touch trigger file: {e}")

    def _calculate_sleep_time(self) -> float:
        """Calculate how long to sleep before next check."""
        sched_config = self.config['schedule']

        if self.state.mode in ('learning', 'relearning'):
            # During learning, poll at fallback interval
            return sched_config['fallback_poll_seconds']

        # In learned mode, sleep until just before expected arrival
        min_sleep = 10.0
        max_sleep = sched_config['fallback_poll_seconds']

        for sat_state in self.state.satellites.values():
            if sat_state.next_expected_utc:
                expected = datetime.fromisoformat(sat_state.next_expected_utc)
                tolerance = min(
                    max(sat_state.interval_stddev_seconds * 3,
                        sched_config['tolerance_min_seconds']),
                    sched_config['tolerance_max_seconds']
                )

                # Wake up at start of tolerance window
                check_time = expected.timestamp() - tolerance
                now = self._now_utc().timestamp()
                sleep_time = check_time - now

                if sleep_time > 0:
                    return max(min_sleep, min(sleep_time, max_sleep))

        return max_sleep

    def process_satellite(self, sat_name: str, sat_config: Dict):
        """Process one satellite - check for new data, publish, generate composites."""
        # Initialize state if needed
        if sat_name not in self.state.satellites:
            self.state.satellites[sat_name] = SatelliteState()

        sat_state = self.state.satellites[sat_name]

        # Check for new data
        newest_dir = self._find_newest_complete_dir(sat_config)

        if newest_dir and newest_dir != sat_state.last_published_dir:
            # New data arrived
            logger.info(f"{sat_name}: New frame detected: {newest_dir}")
            self._record_arrival(sat_name, sat_state, newest_dir)

            # Publish data
            channel_paths = self._publish_data(sat_name, sat_config, newest_dir)

            # Generate composites
            self._generate_composites(sat_name, channel_paths)

            # Clean up old published images
            self._cleanup_old_published(sat_name)

            # Update meta and trigger SSE
            self._write_meta(newest_dir)
            self._notify_update()

            sat_state.consecutive_failures = 0

        elif self.state.mode == 'learned' and self._is_overdue(sat_state):
            # Expected data didn't arrive
            self._record_failure(sat_name, sat_state)

    def run(self):
        """Main service loop."""
        logger.info("GOES Scheduler starting...")
        logger.info(f"Mode: {self.state.mode}")
        logger.info(f"Satellites: {list(self.config['satellites'].keys())}")

        while self.running:
            try:
                # Process each satellite
                for sat_name, sat_config in self.config['satellites'].items():
                    self.process_satellite(sat_name, sat_config)

                # Periodic cleanup even when no new data arrives
                self._maybe_run_cleanup()

                # Save state
                self._save_state()

                # Calculate sleep time
                sleep_time = self._calculate_sleep_time()
                logger.debug(f"Sleeping for {sleep_time:.1f}s")

                # Sleep in small increments to allow signal handling
                sleep_end = time.time() + sleep_time
                while time.time() < sleep_end and self.running:
                    time.sleep(min(1.0, sleep_end - time.time()))

            except Exception as e:
                logger.exception(f"Error in main loop: {e}")
                time.sleep(10)

        logger.info("GOES Scheduler stopped")
        self._save_state()


def main():
    """Entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='GOES Scheduler Service')
    parser.add_argument('--config', '-c', type=Path,
                        help='Path to configuration file')
    parser.add_argument('--debug', '-d', action='store_true',
                        help='Enable debug logging')
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    scheduler = GoesScheduler(config_path=args.config)
    scheduler.run()


if __name__ == '__main__':
    main()
