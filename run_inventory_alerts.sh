#!/bin/bash

# --- Diagnostics Setup ---
# Define the log paths using ABSOLUTE paths (replace /home/allen/... as needed)
LOG_DIR="/home/allen/projects/ventura_web/ventura/cron_logs"
LOG_FILE="$LOG_DIR/alerts_output.log"
ERROR_FILE="$LOG_DIR/alerts_errors.log"

# Create log directory if it doesn't exist (this prevents failure)
mkdir -p $LOG_DIR

# Log the start time
echo "--- Job Started: $(date) ---" >> $LOG_FILE 2>&1

# --- Environment Setup (The fix for .env) ---
PROJECT_ROOT="/home/allen/projects/ventura_web/ventura"
VENV_PYTHON="$PROJECT_ROOT/venv/bin/python"

# Change directory to project root so the script can find manage.py and .env
cd $PROJECT_ROOT

# Source the .env file to load all your credentials/variables
# 'set -a' exports variables; 'set +a' turns it off
set -a
source .env
set +a

# --- Command Execution ---
# Execute the Django management command
# Redirect all output (stdout and stderr) to the error log file for debugging
$VENV_PYTHON manage.py sendInventoryAlerts >> $ERROR_FILE 2>&1

# Log the finish time
echo "--- Job Finished: $(date) ---" >> $LOG_FILE 2>&1

# Exit status is handled by the last command