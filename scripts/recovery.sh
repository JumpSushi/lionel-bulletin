#!/bin/bash
# Recovery script for KGV Bulletin Service
# Use this script to restore from backups

set -e

# Configuration
APP_NAME="kgv-bulletin"
BACKUP_DIR="/var/backups/${APP_NAME}"
DB_PATH="/opt/${APP_NAME}/instance/bulletin_service.db"
APP_DIR="/opt/${APP_NAME}"
LOG_FILE="/var/log/${APP_NAME}/recovery.log"

# Create log directory if it doesn't exist
mkdir -p "$(dirname "${LOG_FILE}")"

# Function to log messages
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "${LOG_FILE}"
}

# Function to list available backups
list_backups() {
    log_message "Available backups:"
    echo
    echo "Database backups:"
    find "${BACKUP_DIR}" -name "database_*.gz" -type f -printf '%TY-%Tm-%Td %TH:%TM  %f\n' | sort -r
    echo
    echo "Application backups:"
    find "${BACKUP_DIR}" -name "app_*.tar.gz" -type f -printf '%TY-%Tm-%Td %TH:%TM  %f\n' | sort -r
    echo
    echo "Configuration backups:"
    find "${BACKUP_DIR}" -name "configs_*.tar.gz" -type f -printf '%TY-%Tm-%Td %TH:%TM  %f\n' | sort -r
    echo
}

# Function to restore database
restore_database() {
    local backup_file=$1
    
    if [ ! -f "${backup_file}" ]; then
        log_message "ERROR: Database backup file not found: ${backup_file}"
        exit 1
    fi
    
    log_message "Restoring database from: ${backup_file}"
    
    # Stop the service
    log_message "Stopping ${APP_NAME} service"
    systemctl stop ${APP_NAME} || true
    sleep 2
    
    # Backup current database
    if [ -f "${DB_PATH}" ]; then
        local current_backup="${DB_PATH}.pre-restore.$(date +%Y%m%d_%H%M%S)"
        log_message "Backing up current database to: ${current_backup}"
        cp "${DB_PATH}" "${current_backup}"
    fi
    
    # Restore from backup
    log_message "Decompressing and restoring database"
    gunzip -c "${backup_file}" > "${DB_PATH}"
    
    # Set proper permissions
    chown ${APP_NAME}:${APP_NAME} "${DB_PATH}"
    chmod 660 "${DB_PATH}"
    
    log_message "Database restore completed"
}

# Function to restore application files
restore_app_files() {
    local backup_file=$1
    
    if [ ! -f "${backup_file}" ]; then
        log_message "ERROR: Application backup file not found: ${backup_file}"
        exit 1
    fi
    
    log_message "Restoring application files from: ${backup_file}"
    
    # Stop the service
    log_message "Stopping ${APP_NAME} service"
    systemctl stop ${APP_NAME} || true
    sleep 2
    
    # Backup current application directory
    local current_backup="/tmp/${APP_NAME}_current_$(date +%Y%m%d_%H%M%S).tar.gz"
    log_message "Backing up current application to: ${current_backup}"
    tar -czf "${current_backup}" -C "$(dirname "${APP_DIR}")" "$(basename "${APP_DIR}")"
    
    # Restore from backup
    log_message "Extracting application files"
    tar -xzf "${backup_file}" -C "$(dirname "${APP_DIR}")"
    
    # Set proper permissions
    chown -R ${APP_NAME}:${APP_NAME} "${APP_DIR}"
    
    log_message "Application files restore completed"
}

# Function to restore configuration files
restore_configs() {
    local backup_file=$1
    
    if [ ! -f "${backup_file}" ]; then
        log_message "ERROR: Configuration backup file not found: ${backup_file}"
        exit 1
    fi
    
    log_message "Restoring configuration files from: ${backup_file}"
    
    # Extract configuration files
    tar -xzf "${backup_file}" -C /
    
    # Reload systemd and nginx
    systemctl daemon-reload
    systemctl reload nginx || true
    
    log_message "Configuration files restore completed"
}

# Function to verify system after restore
verify_system() {
    log_message "Verifying system after restore"
    
    # Check if database file exists and is readable
    if [ -f "${DB_PATH}" ] && [ -r "${DB_PATH}" ]; then
        log_message "✓ Database file exists and is readable"
    else
        log_message "✗ Database file missing or not readable"
        return 1
    fi
    
    # Check if application directory exists
    if [ -d "${APP_DIR}" ]; then
        log_message "✓ Application directory exists"
    else
        log_message "✗ Application directory missing"
        return 1
    fi
    
    # Check if main application file exists
    if [ -f "${APP_DIR}/app.py" ]; then
        log_message "✓ Main application file exists"
    else
        log_message "✗ Main application file missing"
        return 1
    fi
    
    # Try to start the service
    log_message "Starting ${APP_NAME} service"
    systemctl start ${APP_NAME}
    sleep 10
    
    # Check if service is running
    if systemctl is-active --quiet ${APP_NAME}; then
        log_message "✓ Service is running"
    else
        log_message "✗ Service failed to start"
        journalctl -u ${APP_NAME} --no-pager -n 20
        return 1
    fi
    
    # Check if service responds to health check
    sleep 5
    if curl -f http://localhost:8000/health > /dev/null 2>&1; then
        log_message "✓ Service responds to health check"
    else
        log_message "✗ Service does not respond to health check"
        return 1
    fi
    
    log_message "System verification completed successfully"
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTION] [BACKUP_FILE]"
    echo
    echo "Options:"
    echo "  -l, --list                 List available backups"
    echo "  -d, --database FILE        Restore database from backup file"
    echo "  -a, --app FILE             Restore application files from backup file"
    echo "  -c, --config FILE          Restore configuration files from backup file"
    echo "  -f, --full DATE            Restore full system from backups of specific date (YYYYMMDD)"
    echo "  -h, --help                 Show this help message"
    echo
    echo "Examples:"
    echo "  $0 --list"
    echo "  $0 --database /var/backups/kgv-bulletin/database_20231201_143022.db.gz"
    echo "  $0 --full 20231201"
    echo
}

# Function to restore full system
restore_full_system() {
    local date=$1
    
    log_message "Starting full system restore for date: ${date}"
    
    # Find backups for the specified date
    local db_backup=$(find "${BACKUP_DIR}" -name "database_${date}_*.gz" -type f | head -1)
    local app_backup=$(find "${BACKUP_DIR}" -name "app_${date}_*.tar.gz" -type f | head -1)
    local config_backup=$(find "${BACKUP_DIR}" -name "configs_${date}_*.tar.gz" -type f | head -1)
    
    # Check if backups exist
    if [ -z "${db_backup}" ]; then
        log_message "ERROR: No database backup found for date ${date}"
        exit 1
    fi
    
    if [ -z "${app_backup}" ]; then
        log_message "ERROR: No application backup found for date ${date}"
        exit 1
    fi
    
    log_message "Found backups:"
    log_message "  Database: ${db_backup}"
    log_message "  Application: ${app_backup}"
    [ -n "${config_backup}" ] && log_message "  Configuration: ${config_backup}"
    
    # Perform restore
    restore_database "${db_backup}"
    restore_app_files "${app_backup}"
    [ -n "${config_backup}" ] && restore_configs "${config_backup}"
    
    # Verify system
    verify_system
    
    log_message "Full system restore completed successfully"
}

# Main script
main() {
    if [ $# -eq 0 ]; then
        show_usage
        exit 1
    fi
    
    # Check if running as root
    if [ "$(id -u)" -ne 0 ]; then
        log_message "ERROR: This script must be run as root"
        exit 1
    fi
    
    # Check if backup directory exists
    if [ ! -d "${BACKUP_DIR}" ]; then
        log_message "ERROR: Backup directory not found: ${BACKUP_DIR}"
        exit 1
    fi
    
    case "$1" in
        -l|--list)
            list_backups
            ;;
        -d|--database)
            if [ -z "$2" ]; then
                log_message "ERROR: Database backup file not specified"
                exit 1
            fi
            restore_database "$2"
            verify_system
            ;;
        -a|--app)
            if [ -z "$2" ]; then
                log_message "ERROR: Application backup file not specified"
                exit 1
            fi
            restore_app_files "$2"
            verify_system
            ;;
        -c|--config)
            if [ -z "$2" ]; then
                log_message "ERROR: Configuration backup file not specified"
                exit 1
            fi
            restore_configs "$2"
            ;;
        -f|--full)
            if [ -z "$2" ]; then
                log_message "ERROR: Date not specified"
                exit 1
            fi
            restore_full_system "$2"
            ;;
        -h|--help)
            show_usage
            ;;
        *)
            log_message "ERROR: Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
}

# Error handling
trap 'echo "ERROR: Recovery script failed at line $LINENO"; exit 1' ERR

# Run main function
main "$@"
