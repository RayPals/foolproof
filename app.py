import sys
import os
import subprocess
from datetime import datetime
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QTextEdit
from PyQt5.QtCore import QThread, pyqtSignal

class MaintenanceThread(QThread):
    # Signal to send log messages to the GUI
    log_signal = pyqtSignal(str)

    def run(self):
        self.log_signal.emit(self.format_log('Starting maintenance tasks.'))

        # Check for Windows Update module and run Windows Update scan
        self.log_signal.emit(self.format_log('Checking for Windows updates...'))
        try:
            start_time = datetime.now()
            subprocess.run(['powershell', '-Command', 'Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Force'], check=True, shell=True)
            subprocess.run(['powershell', '-Command', 'Install-Module -Name PSWindowsUpdate -Force -Scope CurrentUser'], check=True, shell=True)
            subprocess.run(['powershell', '-Command', 'Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force'], check=True, shell=True)
            result = subprocess.run(['powershell', '-Command', 'Get-WindowsUpdate -AcceptAll'], capture_output=True, text=True, shell=True)
            end_time = datetime.now()
            self.log_signal.emit(self.format_log(f'Windows Update scan completed in {end_time - start_time}.'))
            self.log_signal.emit(self.format_log(f'Windows Update scan result: {result.stdout if result.stdout else "No new updates found."}'))
        except Exception as e:
            self.log_signal.emit(self.format_log(f'Error during Windows Update scan: {e}'))

        # Run defrag/trim
        self.log_signal.emit(self.format_log('Defragmenting/Trimming the OS drive...'))
        try:
            start_time = datetime.now()
            subprocess.run(['defrag', 'C:', '/O'], check=True)
            end_time = datetime.now()
            self.log_signal.emit(self.format_log(f'Defragmentation/Trimming completed in {end_time - start_time}.'))
        except Exception as e:
            self.log_signal.emit(self.format_log(f'Error during defragmentation/trim: {e}'))

        # Run Disk Cleanup
        self.log_signal.emit(self.format_log('Performing Disk Cleanup...'))
        try:
            start_time = datetime.now()
            subprocess.run(['cleanmgr', '/sagerun:1'], check=True)
            end_time = datetime.now()
            self.log_signal.emit(self.format_log(f'Disk Cleanup completed in {end_time - start_time}.'))
        except Exception as e:
            self.log_signal.emit(self.format_log(f'Error during Disk Cleanup: {e}'))

        # Run full antivirus scan with Windows Defender
        self.log_signal.emit(self.format_log('Running full antivirus scan...'))
        try:
            start_time = datetime.now()
            defender_path = os.path.join(os.environ['ProgramFiles'], 'Windows Defender', 'MpCmdRun.exe')
            subprocess.run([defender_path, '-Scan', '-ScanType', '2'], check=True)
            end_time = datetime.now()
            self.log_signal.emit(self.format_log(f'Antivirus scan completed in {end_time - start_time}.'))
        except Exception as e:
            self.log_signal.emit(self.format_log(f'Error during antivirus scan: {e}'))

        self.log_signal.emit(self.format_log('Maintenance tasks completed.'))

    def format_log(self, message):
        """Helper method to format log messages with a timestamp."""
        return f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {message}'

class MaintenanceApp(QWidget):
    def __init__(self):
        super().__init__()

        # Set up the window
        self.setWindowTitle('FoolProof')  # Updated the window title to 'FoolProof'
        self.setGeometry(100, 100, 500, 400)

        # Create a QVBoxLayout to hold the text box and button
        self.layout = QVBoxLayout()

        # Create a QTextEdit widget for logging
        self.log_textbox = QTextEdit()
        self.log_textbox.setReadOnly(True)  # Make it read-only
        self.layout.addWidget(self.log_textbox)

        # Create a QPushButton widget
        self.start_button = QPushButton('Start Maintenance')
        self.start_button.clicked.connect(self.run_maintenance_tasks)
        self.layout.addWidget(self.start_button)

        # Set the layout for the main window
        self.setLayout(self.layout)

        # Initialize log file
        self.log_file_path = 'log.txt'
        with open(self.log_file_path, 'w') as f:
            f.write(self.format_log('Maintenance Log Started\n'))

    def run_maintenance_tasks(self):
        self.log_message('Starting maintenance...')

        # Disable the start button to prevent multiple clicks
        self.start_button.setEnabled(False)

        # Create and start the maintenance thread
        self.maintenance_thread = MaintenanceThread()
        self.maintenance_thread.log_signal.connect(self.log_message)
        self.maintenance_thread.finished.connect(self.on_maintenance_finished)
        self.maintenance_thread.start()

    def log_message(self, message):
        # Append log messages to the text box
        self.log_textbox.append(message)
        # Write log messages to a file
        with open(self.log_file_path, 'a') as f:
            f.write(message + '\n')

    def format_log(self, message):
        """Helper method to format log messages with a timestamp."""
        return f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] {message}'

    def on_maintenance_finished(self):
        # Re-enable the start button when maintenance is done
        self.start_button.setEnabled(True)
        # Log a summary message
        self.log_message(self.format_log('All maintenance tasks are completed.'))

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MaintenanceApp()
    window.show()
    sys.exit(app.exec_())
