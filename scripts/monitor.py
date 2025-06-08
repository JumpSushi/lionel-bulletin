#!/usr/bin/env python3
"""
System monitoring script for KGV Bulletin Service
Monitors system health, performance, and logs
"""

import psutil
import sqlite3
import requests
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
import logging

class SystemMonitor:
    def __init__(self, app_dir='/opt/kgv-bulletin'):
        self.app_dir = Path(app_dir)
        self.db_path = self.app_dir / 'instance' / 'bulletin_service.db'
        self.log_file = Path('/var/log/kgv-bulletin/monitor.log')
        self.metrics_file = Path('/var/log/kgv-bulletin/metrics.json')
        
        # Setup logging
        self.setup_logging()
    
    def setup_logging(self):
        """Setup logging configuration"""
        self.log_file.parent.mkdir(exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def get_system_metrics(self):
        """Get system performance metrics"""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_available = memory.available / (1024 * 1024)  # MB
            
            # Disk usage
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            disk_free = disk.free / (1024 * 1024 * 1024)  # GB
            
            # Load average (Linux/Unix only)
            try:
                load_avg = os.getloadavg()
                load_1min = load_avg[0]
            except:
                load_1min = 0
            
            # Network I/O
            net_io = psutil.net_io_counters()
            
            # Process information for our service
            app_process = None
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if 'gunicorn' in proc.info['name'] and 'kgv-bulletin' in ' '.join(proc.info['cmdline'] or []):
                        app_process = proc
                        break
                except:
                    continue
            
            app_memory = 0
            app_cpu = 0
            if app_process:
                try:
                    app_memory = app_process.memory_info().rss / (1024 * 1024)  # MB
                    app_cpu = app_process.cpu_percent()
                except:
                    pass
            
            return {
                'timestamp': datetime.utcnow().isoformat(),
                'cpu': {
                    'percent': cpu_percent,
                    'count': cpu_count,
                    'load_1min': load_1min
                },
                'memory': {
                    'percent': memory_percent,
                    'available_mb': memory_available,
                    'app_usage_mb': app_memory
                },
                'disk': {
                    'percent': disk_percent,
                    'free_gb': disk_free
                },
                'network': {
                    'bytes_sent': net_io.bytes_sent,
                    'bytes_recv': net_io.bytes_recv
                },
                'application': {
                    'cpu_percent': app_cpu,
                    'memory_mb': app_memory,
                    'running': app_process is not None
                }
            }
        except Exception as e:
            self.logger.error(f"Error getting system metrics: {e}")
            return None
    
    def get_database_metrics(self):
        """Get database performance metrics"""
        try:
            if not self.db_path.exists():
                return None
            
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # Database size
            db_size = self.db_path.stat().st_size / (1024 * 1024)  # MB
            
            # Table counts
            tables = ['user', 'bulletin_item', 'email_log', 'email_subscription', 'bulletin_filter', 'admin_action']
            table_counts = {}
            
            for table in tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    table_counts[table] = cursor.fetchone()[0]
                except:
                    table_counts[table] = 0
            
            # Recent activity (last 24 hours)
            yesterday = datetime.utcnow() - timedelta(days=1)
            yesterday_str = yesterday.strftime('%Y-%m-%d %H:%M:%S')
            
            recent_bulletins = 0
            recent_emails = 0
            recent_users = 0
            
            try:
                cursor.execute("SELECT COUNT(*) FROM bulletin_item WHERE created_at > ?", (yesterday_str,))
                recent_bulletins = cursor.fetchone()[0]
            except:
                pass
            
            try:
                cursor.execute("SELECT COUNT(*) FROM email_log WHERE sent_at > ?", (yesterday_str,))
                recent_emails = cursor.fetchone()[0]
            except:
                pass
            
            try:
                cursor.execute("SELECT COUNT(*) FROM user WHERE created_at > ?", (yesterday_str,))
                recent_users = cursor.fetchone()[0]
            except:
                pass
            
            conn.close()
            
            return {
                'size_mb': db_size,
                'table_counts': table_counts,
                'recent_activity': {
                    'bulletins_24h': recent_bulletins,
                    'emails_24h': recent_emails,
                    'users_24h': recent_users
                }
            }
        except Exception as e:
            self.logger.error(f"Error getting database metrics: {e}")
            return None
    
    def check_service_health(self):
        """Check application service health"""
        try:
            # Check if service is running
            import subprocess
            result = subprocess.run(['systemctl', 'is-active', 'kgv-bulletin'], 
                                  capture_output=True, text=True)
            service_active = result.stdout.strip() == 'active'
            
            # Check HTTP health endpoint
            http_healthy = False
            response_time = None
            
            try:
                start_time = time.time()
                response = requests.get('http://localhost:8000/health', timeout=10)
                response_time = time.time() - start_time
                http_healthy = response.status_code == 200
            except:
                pass
            
            return {
                'service_active': service_active,
                'http_healthy': http_healthy,
                'response_time': response_time
            }
        except Exception as e:
            self.logger.error(f"Error checking service health: {e}")
            return None
    
    def check_disk_space(self):
        """Check for low disk space warnings"""
        warnings = []
        
        # Check root filesystem
        root_usage = psutil.disk_usage('/')
        root_percent = root_usage.percent
        root_free_gb = root_usage.free / (1024 * 1024 * 1024)
        
        if root_percent > 90:
            warnings.append(f"Root filesystem critically low: {root_percent:.1f}% used")
        elif root_percent > 80:
            warnings.append(f"Root filesystem low: {root_percent:.1f}% used")
        
        if root_free_gb < 0.5:
            warnings.append(f"Root filesystem critically low: {root_free_gb:.2f}GB free")
        
        # Check log directory
        try:
            log_dir = Path('/var/log/kgv-bulletin')
            if log_dir.exists():
                log_size = sum(f.stat().st_size for f in log_dir.rglob('*') if f.is_file())
                log_size_mb = log_size / (1024 * 1024)
                
                if log_size_mb > 100:
                    warnings.append(f"Log directory large: {log_size_mb:.1f}MB")
        except:
            pass
        
        return warnings
    
    def save_metrics(self, metrics):
        """Save metrics to file for historical tracking"""
        try:
            self.metrics_file.parent.mkdir(exist_ok=True)
            
            # Load existing metrics
            historical_metrics = []
            if self.metrics_file.exists():
                try:
                    with open(self.metrics_file, 'r') as f:
                        historical_metrics = json.load(f)
                except:
                    historical_metrics = []
            
            # Add current metrics
            historical_metrics.append(metrics)
            
            # Keep only last 24 hours of metrics (assuming 5-minute intervals)
            max_entries = 24 * 12  # 288 entries
            if len(historical_metrics) > max_entries:
                historical_metrics = historical_metrics[-max_entries:]
            
            # Save back to file
            with open(self.metrics_file, 'w') as f:
                json.dump(historical_metrics, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"Error saving metrics: {e}")
    
    def generate_report(self):
        """Generate comprehensive system report"""
        self.logger.info("Generating system report...")
        
        # Collect all metrics
        system_metrics = self.get_system_metrics()
        database_metrics = self.get_database_metrics()
        health_status = self.check_service_health()
        disk_warnings = self.check_disk_space()
        
        report = {
            'timestamp': datetime.utcnow().isoformat(),
            'system': system_metrics,
            'database': database_metrics,
            'health': health_status,
            'warnings': disk_warnings
        }
        
        # Save metrics
        self.save_metrics(report)
        
        # Log important information
        if system_metrics:
            self.logger.info(f"System: CPU {system_metrics['cpu']['percent']:.1f}%, "
                           f"Memory {system_metrics['memory']['percent']:.1f}%, "
                           f"Disk {system_metrics['disk']['percent']:.1f}%")
        
        if health_status:
            if health_status['service_active'] and health_status['http_healthy']:
                self.logger.info("Service: Healthy")
            else:
                self.logger.warning(f"Service: Issues detected - "
                                  f"Active: {health_status['service_active']}, "
                                  f"HTTP: {health_status['http_healthy']}")
        
        if disk_warnings:
            for warning in disk_warnings:
                self.logger.warning(f"Disk: {warning}")
        
        return report
    
    def run_continuous_monitoring(self, interval=300):
        """Run continuous monitoring with specified interval (seconds)"""
        self.logger.info(f"Starting continuous monitoring (interval: {interval}s)")
        
        try:
            while True:
                self.generate_report()
                time.sleep(interval)
        except KeyboardInterrupt:
            self.logger.info("Monitoring stopped by user")
        except Exception as e:
            self.logger.error(f"Monitoring error: {e}")

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='KGV Bulletin Service System Monitor')
    parser.add_argument('--app-dir', default='/opt/kgv-bulletin', help='Application directory')
    parser.add_argument('--continuous', action='store_true', help='Run continuous monitoring')
    parser.add_argument('--interval', type=int, default=300, help='Monitoring interval in seconds')
    parser.add_argument('--report-only', action='store_true', help='Generate single report and exit')
    
    args = parser.parse_args()
    
    monitor = SystemMonitor(args.app_dir)
    
    if args.continuous:
        monitor.run_continuous_monitoring(args.interval)
    else:
        report = monitor.generate_report()
        if args.report_only:
            print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
