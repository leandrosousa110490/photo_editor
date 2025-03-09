import sys
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QLabel, QPushButton, 
                           QVBoxLayout, QHBoxLayout, QWidget, QFileDialog,
                           QSpinBox, QComboBox, QSlider, QMessageBox, QGroupBox,
                           QSizePolicy, QProgressBar, QCheckBox)
from PyQt5.QtGui import QPixmap, QImage, QPalette, QColor, QIcon, QPainter, QBrush
from PyQt5.QtCore import Qt, QSize, QTimer, QThread, pyqtSignal, QRect
from PIL import Image, ImageQt
import numpy as np
import subprocess
import logging
import importlib
import site
import traceback
import io
import base64  # For SVG encoding

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'image_editor.log')
)
logger = logging.getLogger('ImageEditor')

# Global variables for optional modules
REMBG_AVAILABLE = False
SVGLIB_AVAILABLE = False

# Function to check for svglib
def initialize_svglib():
    global SVGLIB_AVAILABLE
    try:
        # Check if the module exists without importing it first
        if importlib.util.find_spec('svglib') is None:
            logger.warning("svglib package not found in system path")
            return False
            
        # Try importing
        logger.info("Attempting to import svglib module")
        import svglib.svglib
        from reportlab.graphics import renderPM
        
        # Log the path where svglib was found
        svglib_path = sys.modules['svglib'].__file__
        logger.info(f"svglib successfully imported from: {svglib_path}")
        SVGLIB_AVAILABLE = True
        return True
    except ImportError as e:
        logger.error(f"ImportError for svglib: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error loading svglib: {str(e)}")
        logger.error(traceback.format_exc())
        return False

# Function to check for rembg and initialize it
def initialize_rembg():
    global REMBG_AVAILABLE
    global remove
    global new_session
    
    REMBG_AVAILABLE = False
    try:
        # Check if the module exists without importing it first
        if importlib.util.find_spec('rembg') is None:
            logger.warning("rembg package not found in system path")
            return False
            
        # Now try importing
        logger.info("Attempting to import rembg module")
        from rembg import remove
        from rembg.session_factory import new_session
        
        # Log the path where rembg was found
        rembg_path = sys.modules['rembg'].__file__
        logger.info(f"rembg successfully imported from: {rembg_path}")
        
        # Verify it works by creating a session
        try:
            logger.info("Attempting to create rembg session")
            session = new_session("u2net")
            logger.info("rembg session created successfully")
            REMBG_AVAILABLE = True
            return True
        except Exception as e:
            logger.error(f"Error creating rembg session: {str(e)}")
            logger.error(traceback.format_exc())
            return False
            
    except ImportError as e:
        logger.error(f"ImportError for rembg: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error loading rembg: {str(e)}")
        logger.error(traceback.format_exc())
        return False

# Initial check for optional libraries
REMBG_AVAILABLE = False
SVGLIB_AVAILABLE = False
initialize_rembg()
initialize_svglib()

class TransparentBackgroundLabel(QLabel):
    """Custom QLabel that shows a checkered background for transparent images."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.dark_mode = False
        
    def set_dark_mode(self, is_dark):
        self.dark_mode = is_dark
        
    def paintEvent(self, event):
        # Draw the checkered pattern first
        painter = QPainter(self)
        
        # Set appropriate colors based on mode
        if self.dark_mode:
            color1 = QColor(50, 50, 50)  # Dark gray
            color2 = QColor(70, 70, 70)  # Medium gray
        else:
            color1 = QColor(240, 240, 240)  # Light gray 
            color2 = QColor(255, 255, 255)  # White
        
        # Draw checkered background for transparent images
        size = 10  # Size of each checker square
        for i in range(0, self.width(), size):
            for j in range(0, self.height(), size):
                rect = QRect(i, j, size, size)
                if (i // size + j // size) % 2 == 0:
                    painter.fillRect(rect, color1)
                else:
                    painter.fillRect(rect, color2)
                    
        # Then let the normal QLabel drawing happen
        painter.end()
        super().paintEvent(event)

class BackgroundRemovalThread(QThread):
    """Thread for background removal to prevent UI freezing."""
    finished = pyqtSignal(object)
    progress = pyqtSignal(int)
    error = pyqtSignal(str)
    
    def __init__(self, image):
        super().__init__()
        self.image = image
    
    def run(self):
        try:
            if not REMBG_AVAILABLE:
                self.error.emit("rembg library not available")
                return
                
            self.progress.emit(10)
            # Convert PIL Image to numpy array for rembg
            img_array = np.array(self.image)
            
            self.progress.emit(30)
            # Remove background
            session = new_session("u2net")
            self.progress.emit(50)
            output_array = remove(img_array, session=session)
            
            self.progress.emit(80)
            # Convert back to PIL Image
            output_image = Image.fromarray(output_array)
            
            self.progress.emit(100)
            self.finished.emit(output_image)
        except Exception as e:
            logger.error(f"Background removal error: {str(e)}")
            self.error.emit(str(e))

class ImageEditorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        # Check if system is using dark mode based on palette instead of colorScheme
        app = QApplication.instance()
        palette = app.palette()
        window_color = palette.color(QPalette.Window)
        # If window background is dark (brightness < 128), assume dark mode
        brightness = (window_color.red() + window_color.green() + window_color.blue()) / 3
        self.is_dark_mode = brightness < 128
        
        self.initUI()
        
        # Initialize variables
        self.current_image = None
        self.current_image_path = None
        self.original_size = (0, 0)
        self.temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
        self.temp_preview_path = os.path.join(self.temp_dir, "temp_preview.png")
        
        # Log initialization
        logger.info(f"Application started. Dark mode: {self.is_dark_mode}")
        logger.info(f"rembg available: {REMBG_AVAILABLE}")
        
    def initUI(self):
        # Set window properties
        self.setWindowTitle('Picture Editor')
        self.setGeometry(100, 100, 1000, 700)
        
        # Set appropriate style based on dark mode
        if self.is_dark_mode:
            self.setStyleSheet("""
                QMainWindow, QWidget {
                    background-color: #2D2D30;
                    color: #FFFFFF;
                }
                QLabel {
                    color: #FFFFFF;
                }
                QPushButton {
                    background-color: #007ACC;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #005999;
                }
                QPushButton:pressed {
                    background-color: #004C80;
                }
                QComboBox, QSpinBox {
                    background-color: #333337;
                    color: white;
                    border: 1px solid #555555;
                    padding: 5px;
                    border-radius: 3px;
                }
                QGroupBox {
                    color: white;
                    border: 1px solid #555555;
                    border-radius: 5px;
                    margin-top: 10px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px;
                }
                QProgressBar {
                    border: 1px solid #555555;
                    border-radius: 3px;
                    text-align: center;
                    background-color: #333337;
                }
                QProgressBar::chunk {
                    background-color: #007ACC;
                }
                QCheckBox {
                    color: #FFFFFF;
                }
            """)
        else:
            self.setStyleSheet("""
                QMainWindow, QWidget {
                    background-color: #F0F0F0;
                    color: #000000;
                }
                QPushButton {
                    background-color: #0078D7;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #106EBE;
                }
                QPushButton:pressed {
                    background-color: #005A9E;
                }
                QComboBox, QSpinBox {
                    background-color: #FFFFFF;
                    color: black;
                    border: 1px solid #CCCCCC;
                    padding: 5px;
                    border-radius: 3px;
                }
                QGroupBox {
                    color: #000000;
                    border: 1px solid #CCCCCC;
                    border-radius: 5px;
                    margin-top: 10px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px;
                }
                QProgressBar {
                    border: 1px solid #CCCCCC;
                    border-radius: 3px;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background-color: #0078D7;
                }
            """)
        
        # Create main widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Add theme toggle button at the top
        theme_layout = QHBoxLayout()
        self.theme_btn = QPushButton("Toggle Dark/Light Mode")
        self.theme_btn.clicked.connect(self.toggle_theme)
        theme_layout.addStretch(1)
        theme_layout.addWidget(self.theme_btn)
        main_layout.addLayout(theme_layout)
        
        # Image display area - Use custom label for transparent images
        self.image_label = TransparentBackgroundLabel("No image loaded")
        self.image_label.set_dark_mode(self.is_dark_mode)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(400, 300)
        bg_color = "#1E1E1E" if self.is_dark_mode else "#FFFFFF"
        self.image_label.setStyleSheet(f"border: 2px dashed #555555; background-color: {bg_color};")
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout.addWidget(self.image_label)
        
        # Control panels
        controls_layout = QHBoxLayout()
        
        # Image loading panel
        load_group = QGroupBox("Image Source")
        load_layout = QVBoxLayout(load_group)
        self.load_btn = QPushButton("Load Image")
        self.load_btn.clicked.connect(self.load_image)
        load_layout.addWidget(self.load_btn)
        
        # Image info
        self.info_label = QLabel("Size: N/A")
        load_layout.addWidget(self.info_label)
        controls_layout.addWidget(load_group)
        
        # Resize panel
        resize_group = QGroupBox("Resize Options")
        resize_layout = QVBoxLayout(resize_group)
        
        # Width control
        width_layout = QHBoxLayout()
        width_layout.addWidget(QLabel("Width:"))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 9999)
        self.width_spin.valueChanged.connect(self.update_height_maintain_ratio)
        width_layout.addWidget(self.width_spin)
        resize_layout.addLayout(width_layout)
        
        # Height control
        height_layout = QHBoxLayout()
        height_layout.addWidget(QLabel("Height:"))
        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 9999)
        self.height_spin.valueChanged.connect(self.update_width_maintain_ratio)
        height_layout.addWidget(self.height_spin)
        resize_layout.addLayout(height_layout)
        
        # Maintain aspect ratio
        self.maintain_ratio = True
        self.ratio_btn = QPushButton("Maintain Ratio: ON")
        self.ratio_btn.setCheckable(True)
        self.ratio_btn.setChecked(True)
        self.ratio_btn.clicked.connect(self.toggle_aspect_ratio)
        resize_layout.addWidget(self.ratio_btn)
        
        # Preview button
        self.preview_btn = QPushButton("Preview Changes")
        self.preview_btn.clicked.connect(self.preview_changes)
        resize_layout.addWidget(self.preview_btn)
        
        controls_layout.addWidget(resize_group)
        
        # Format panel
        format_group = QGroupBox("Format Options")
        format_layout = QVBoxLayout(format_group)
        
        format_layout.addWidget(QLabel("Output Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["JPEG", "PNG", "BMP", "TIFF", "GIF", "WEBP", "ICO", "SVG"])
        self.format_combo.currentTextChanged.connect(self.format_changed)
        format_layout.addWidget(self.format_combo)
        
        # Background removal option
        self.remove_bg_check = QCheckBox("Remove Background")
        rembg_status = "Available" if REMBG_AVAILABLE else "Not Available"
        self.remove_bg_check.setEnabled(REMBG_AVAILABLE)
        self.remove_bg_check.setToolTip(f"Background removal: {rembg_status}")
        format_layout.addWidget(self.remove_bg_check)
        
        # Simple status label for rembg
        self.rembg_status_label = QLabel(f"Background Removal: {'Available' if REMBG_AVAILABLE else 'Not Available'}")
        self.rembg_status_label.setStyleSheet(
            "color: #00AA00; font-weight: bold;" if REMBG_AVAILABLE else "color: #FF5500; font-weight: bold;"
        )
        format_layout.addWidget(self.rembg_status_label)
        
        # Icon size options (for ICO format)
        self.ico_options_group = QGroupBox("Icon Options")
        self.ico_options_layout = QVBoxLayout(self.ico_options_group)
        
        # Size selection for icons
        self.ico_options_layout.addWidget(QLabel("Icon Sizes:"))
        self.ico_sizes_layout = QHBoxLayout()
        
        # Checkboxes for common icon sizes
        self.size_16 = QCheckBox("16×16")
        self.size_16.setChecked(True)
        self.size_32 = QCheckBox("32×32") 
        self.size_32.setChecked(True)
        self.size_48 = QCheckBox("48×48")
        self.size_64 = QCheckBox("64×64")
        self.size_128 = QCheckBox("128×128")
        self.size_256 = QCheckBox("256×256")
        
        self.ico_sizes_layout.addWidget(self.size_16)
        self.ico_sizes_layout.addWidget(self.size_32)
        self.ico_sizes_layout.addWidget(self.size_48)
        self.ico_sizes_layout.addWidget(self.size_64)
        self.ico_sizes_layout.addWidget(self.size_128)
        self.ico_sizes_layout.addWidget(self.size_256)
        
        self.ico_options_layout.addLayout(self.ico_sizes_layout)
        format_layout.addWidget(self.ico_options_group)
        self.ico_options_group.setVisible(False)
        
        # SVG Options
        self.svg_options_group = QGroupBox("SVG Options")
        self.svg_options_layout = QVBoxLayout(self.svg_options_group)
        
        # Quality option for SVG export
        self.svg_options_layout.addWidget(QLabel("Image Quality for SVG:"))
        quality_layout = QHBoxLayout()
        self.svg_quality_slider = QSlider(Qt.Horizontal)
        self.svg_quality_slider.setRange(1, 100)
        self.svg_quality_slider.setValue(85)
        self.svg_quality_slider.setTickPosition(QSlider.TicksBelow)
        quality_layout.addWidget(self.svg_quality_slider)
        self.svg_quality_value = QLabel("85%")
        quality_layout.addWidget(self.svg_quality_value)
        self.svg_options_layout.addLayout(quality_layout)
        self.svg_quality_slider.valueChanged.connect(self.update_svg_quality_label)
        
        # Add a status indicator for svglib
        self.svglib_status_label = QLabel(f"SVG Library: {'Available' if SVGLIB_AVAILABLE else 'Not Available'}")
        self.svglib_status_label.setStyleSheet(
            "color: #00AA00; font-weight: bold;" if SVGLIB_AVAILABLE else "color: #FF5500; font-weight: bold;"
        )
        self.svg_options_layout.addWidget(self.svglib_status_label)
        
        # Add button to install SVG dependencies
        self.install_svg_deps_btn = QPushButton("Install SVG Dependencies")
        self.install_svg_deps_btn.clicked.connect(self.install_svg_dependencies)
        self.svg_options_layout.addWidget(self.install_svg_deps_btn)
        
        format_layout.addWidget(self.svg_options_group)
        self.svg_options_group.setVisible(False)
        
        # Quality slider for JPEG
        quality_layout = QHBoxLayout()
        quality_layout.addWidget(QLabel("Quality:"))
        self.quality_slider = QSlider(Qt.Horizontal)
        self.quality_slider.setRange(1, 100)
        self.quality_slider.setValue(85)
        self.quality_slider.setTickPosition(QSlider.TicksBelow)
        self.quality_slider.setTickInterval(10)
        quality_layout.addWidget(self.quality_slider)
        self.quality_value = QLabel("85%")
        quality_layout.addWidget(self.quality_value)
        format_layout.addLayout(quality_layout)
        self.quality_slider.valueChanged.connect(self.update_quality_label)
        
        controls_layout.addWidget(format_group)
        
        # Save panel
        save_group = QGroupBox("Save Options")
        save_layout = QVBoxLayout(save_group)
        
        self.save_btn = QPushButton("Save Image")
        self.save_btn.clicked.connect(self.save_image)
        save_layout.addWidget(self.save_btn)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        save_layout.addWidget(self.progress_bar)
        
        controls_layout.addWidget(save_group)
        
        main_layout.addLayout(controls_layout)
        
        # Status bar
        self.statusBar().showMessage('Ready')
    
    def toggle_theme(self):
        """Switch between dark and light modes."""
        self.is_dark_mode = not self.is_dark_mode
        self.image_label.set_dark_mode(self.is_dark_mode)
        
        # Apply the appropriate style
        if self.is_dark_mode:
            self.setStyleSheet("""
                QMainWindow, QWidget {
                    background-color: #2D2D30;
                    color: #FFFFFF;
                }
                QLabel {
                    color: #FFFFFF;
                }
                QPushButton {
                    background-color: #007ACC;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #005999;
                }
                QPushButton:pressed {
                    background-color: #004C80;
                }
                QComboBox, QSpinBox {
                    background-color: #333337;
                    color: white;
                    border: 1px solid #555555;
                    padding: 5px;
                    border-radius: 3px;
                }
                QGroupBox {
                    color: white;
                    border: 1px solid #555555;
                    border-radius: 5px;
                    margin-top: 10px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px;
                }
                QProgressBar {
                    border: 1px solid #555555;
                    border-radius: 3px;
                    text-align: center;
                    background-color: #333337;
                }
                QProgressBar::chunk {
                    background-color: #007ACC;
                }
                QCheckBox {
                    color: #FFFFFF;
                }
            """)
            
            # Update image label background
            self.image_label.setStyleSheet("border: 2px dashed #555555; background-color: #1E1E1E;")
        else:
            self.setStyleSheet("""
                QMainWindow, QWidget {
                    background-color: #F0F0F0;
                    color: #000000;
                }
                QPushButton {
                    background-color: #0078D7;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #106EBE;
                }
                QPushButton:pressed {
                    background-color: #005A9E;
                }
                QComboBox, QSpinBox {
                    background-color: #FFFFFF;
                    color: black;
                    border: 1px solid #CCCCCC;
                    padding: 5px;
                    border-radius: 3px;
                }
                QGroupBox {
                    color: #000000;
                    border: 1px solid #CCCCCC;
                    border-radius: 5px;
                    margin-top: 10px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px;
                }
                QProgressBar {
                    border: 1px solid #CCCCCC;
                    border-radius: 3px;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background-color: #0078D7;
                }
            """)
            
            # Update image label background
            self.image_label.setStyleSheet("border: 2px dashed #555555; background-color: #FFFFFF;")
        
        # If an image is loaded, reload it to apply the new theme to the display
        if hasattr(self, 'temp_preview_path') and os.path.exists(self.temp_preview_path):
            self.display_image(self.temp_preview_path)
        
        logger.info(f"Theme changed to {'dark' if self.is_dark_mode else 'light'} mode")
    
    def refresh_rembg_status(self):
        """Check if rembg is available again."""
        global REMBG_AVAILABLE
        
        self.statusBar().showMessage('Checking for rembg...')
        
        # Try to import and initialize rembg again
        was_available = REMBG_AVAILABLE
        initialize_rembg()
        
        # Update UI based on result
        self.remove_bg_check.setEnabled(REMBG_AVAILABLE)
        self.rembg_status_label.setText(f"Status: {'Available' if REMBG_AVAILABLE else 'Not Available'}")
        self.rembg_status_label.setStyleSheet(
            "color: #00AA00;" if REMBG_AVAILABLE else "color: #FF5500;"
        )
        
        if REMBG_AVAILABLE and 'rembg' in sys.modules:
            rembg_path = sys.modules['rembg'].__file__
            QMessageBox.information(self, "rembg Status", 
                                   f"Background removal is now available!\n\nPath: {os.path.dirname(rembg_path)}")
            self.statusBar().showMessage('rembg is available')
        elif was_available != REMBG_AVAILABLE:
            if REMBG_AVAILABLE:
                QMessageBox.information(self, "rembg Status", "Background removal is now available!")
                self.statusBar().showMessage('rembg is available')
            else:
                QMessageBox.warning(self, "rembg Status", "Background removal is not available.")
                self.statusBar().showMessage('rembg is not available')
        else:
            QMessageBox.warning(self, "rembg Status", 
                               f"rembg status unchanged: {'Available' if REMBG_AVAILABLE else 'Not Available'}")
            self.statusBar().showMessage('rembg status unchanged')
        
        return REMBG_AVAILABLE
    
    def install_rembg(self):
        """Install the rembg package using pip."""
        try:
            self.statusBar().showMessage('Installing rembg...')
            
            # Create a message box with progress information
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("Installing rembg")
            msg.setText("Installing background removal package...\n\nThis might take a few minutes.")
            msg.setDetailedText("This will install:\n- rembg\n- u2net model\n- required dependencies\n\nThe process may take several minutes, especially on the first install.")
            msg.setStandardButtons(QMessageBox.NoButton)
            msg.show()
            QApplication.processEvents()
            
            # Get Python executable path and pip paths
            python_exe = sys.executable
            scripts_dir = os.path.join(os.path.dirname(python_exe), 'Scripts')
            pip_path = os.path.join(scripts_dir, 'pip.exe') if os.name == 'nt' else os.path.join(scripts_dir, 'pip')
            if not os.path.exists(pip_path):
                pip_path = python_exe
                pip_args = ["-m", "pip"]
            else:
                pip_args = []
            
            # Log installation information
            logger.info(f"Using Python: {python_exe}")
            logger.info(f"Using pip: {pip_path}")
            
            # First try to uninstall to ensure clean installation
            try:
                logger.info("Attempting to uninstall existing rembg")
                uninstall_cmd = [pip_path] + pip_args + ["uninstall", "-y", "rembg"]
                subprocess.run(uninstall_cmd, capture_output=True, text=True)
            except Exception as e:
                logger.warning(f"Uninstall step error (non-fatal): {str(e)}")
            
            # Install rembg
            logger.info(f"Installing rembg {'with GPU support' if self.has_gpu() else 'without GPU'}")
            install_args = [pip_path] + pip_args + ["install", "--upgrade", "rembg[gpu]" if self.has_gpu() else "rembg"]
            logger.info(f"Install command: {' '.join(install_args)}")
            
            result = subprocess.run(install_args, capture_output=True, text=True)
            
            # Log installation result
            logger.info(f"Installation return code: {result.returncode}")
            logger.info(f"Installation stdout: {result.stdout}")
            if result.stderr:
                logger.warning(f"Installation stderr: {result.stderr}")
            
            if result.returncode == 0:
                # Try to initialize rembg again
                global REMBG_AVAILABLE
                was_available = REMBG_AVAILABLE
                initialize_rembg()
                
                msg.close()
                
                # Update UI based on installation result
                self.remove_bg_check.setEnabled(REMBG_AVAILABLE)
                self.rembg_status_label.setText(f"Status: {'Available' if REMBG_AVAILABLE else 'Not Available'}")
                self.rembg_status_label.setStyleSheet(
                    "color: #00AA00;" if REMBG_AVAILABLE else "color: #FF5500;"
                )
                
                if REMBG_AVAILABLE:
                    QMessageBox.information(
                        self, "Success", 
                        "rembg has been installed successfully and is now available for use."
                    )
                else:
                    QMessageBox.warning(
                        self, "Installation Issue", 
                        "rembg was installed but is still not detected.\n\n"
                        "You may need to restart the application."
                    )
                
                logger.info(f"Installation completed. REMBG_AVAILABLE: {REMBG_AVAILABLE}")
            else:
                msg.close()
                error_msg = f"Error installing rembg:\n\n{result.stderr}"
                QMessageBox.critical(self, "Installation Error", error_msg)
                logger.error(error_msg)
                
            self.statusBar().showMessage('Ready')
        except Exception as e:
            QMessageBox.critical(self, "Installation Error", 
                               f"Failed to install rembg: {str(e)}\n\nCheck the log file for details.")
            logger.error(f"Installation error: {str(e)}")
            logger.error(traceback.format_exc())
    
    def has_gpu(self):
        """Check if the system has a CUDA-capable GPU."""
        try:
            import torch
            return torch.cuda.is_available()
        except:
            return False
    
    def load_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 'Open Image', '', 'Image Files (*.png *.jpg *.jpeg *.bmp *.tiff *.gif *.webp)')
        
        if file_path:
            try:
                self.current_image_path = file_path
                self.current_image = Image.open(file_path)
                self.original_size = self.current_image.size
                
                # Update spinboxes with image dimensions
                self.width_spin.setValue(self.original_size[0])
                self.height_spin.setValue(self.original_size[1])
                
                # Display image
                self.display_image(file_path)
                self.info_label.setText(f"Size: {self.original_size[0]}x{self.original_size[1]}")
                self.statusBar().showMessage(f'Loaded: {os.path.basename(file_path)}')
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Could not load image: {str(e)}")
    
    def display_image(self, image_path):
        try:
            pixmap = QPixmap(image_path)
            
            # Scale pixmap to fit label while maintaining aspect ratio
            pixmap = pixmap.scaled(
                self.image_label.width(), 
                self.image_label.height(),
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            
            self.image_label.setPixmap(pixmap)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not display image: {str(e)}")
            logger.error(f"Display error: {str(e)}")
    
    def update_height_maintain_ratio(self):
        if self.maintain_ratio and self.original_size[0] > 0:
            ratio = self.original_size[1] / self.original_size[0]
            new_height = int(self.width_spin.value() * ratio)
            self.height_spin.blockSignals(True)
            self.height_spin.setValue(new_height)
            self.height_spin.blockSignals(False)
    
    def update_width_maintain_ratio(self):
        if self.maintain_ratio and self.original_size[1] > 0:
            ratio = self.original_size[0] / self.original_size[1]
            new_width = int(self.height_spin.value() * ratio)
            self.width_spin.blockSignals(True)
            self.width_spin.setValue(new_width)
            self.width_spin.blockSignals(False)
    
    def toggle_aspect_ratio(self):
        self.maintain_ratio = self.ratio_btn.isChecked()
        self.ratio_btn.setText(f"Maintain Ratio: {'ON' if self.maintain_ratio else 'OFF'}")
    
    def update_quality_label(self):
        self.quality_value.setText(f"{self.quality_slider.value()}%")
    
    def update_svg_quality_label(self):
        """Update the SVG quality slider value label."""
        self.svg_quality_value.setText(f"{self.svg_quality_slider.value()}%")
    
    def apply_background_removal(self, img):
        """Prepare for background removal using the background removal thread."""
        if not REMBG_AVAILABLE or not self.remove_bg_check.isChecked():
            return img
        
        try:
            # Import required functions here again to ensure they're available
            from rembg import remove
            from rembg.session_factory import new_session
            
            # Create and start the background removal thread
            self.bg_thread = BackgroundRemovalThread(img)
            self.bg_thread.finished.connect(self.on_bg_removal_finished)
            self.bg_thread.progress.connect(self.update_progress)
            self.bg_thread.error.connect(self.on_bg_removal_error)
            self.bg_thread.start()
            
            # Show a message that we're waiting
            self.statusBar().showMessage('Removing background, please wait...')
            
            # Create a modal processing dialog to prevent user interaction
            self.processing_dialog = QMessageBox(self)
            self.processing_dialog.setWindowTitle("Processing")
            self.processing_dialog.setText("Removing background...\nThis may take a few moments.")
            self.processing_dialog.setStandardButtons(QMessageBox.NoButton)
            self.processing_dialog.setModal(True)
            
            # Add a progress bar to the dialog
            layout = self.processing_dialog.layout()
            progress = QProgressBar(self.processing_dialog)
            progress.setRange(0, 0)  # Indeterminate progress
            layout.addWidget(progress, layout.rowCount(), 0, 1, layout.columnCount())
            
            # Show dialog and wait for thread to complete
            self.processing_dialog.exec_()
            
            # Wait for thread to finish and return the processed image
            if hasattr(self, 'processed_image'):
                img = self.processed_image
                delattr(self, 'processed_image')
            
            return img
        
        except Exception as e:
            logger.error(f"Error in apply_background_removal: {str(e)}")
            logger.error(traceback.format_exc())
            QMessageBox.critical(self, "Background Removal Error", 
                               f"Error preparing background removal: {str(e)}")
            return img
    
    def on_bg_removal_finished(self, result_image):
        """Handle the completion of background removal thread."""
        self.processed_image = result_image
        self.statusBar().showMessage('Background removed')
        if hasattr(self, 'processing_dialog') and self.processing_dialog:
            self.processing_dialog.accept()
    
    def on_bg_removal_error(self, error_message):
        """Handle errors from background removal thread."""
        self.statusBar().showMessage(f'Background removal failed: {error_message}')
        if hasattr(self, 'processing_dialog') and self.processing_dialog:
            self.processing_dialog.accept()
        QMessageBox.warning(self, "Background Removal Error", 
                           f"Failed to remove background:\n{error_message}")
        logger.error(f"Background removal error: {error_message}")
    
    def update_progress(self, value):
        """Update the progress bar based on thread progress."""
        self.progress_bar.setValue(value)
    
    def preview_changes(self):
        if self.current_image is None:
            QMessageBox.warning(self, "Warning", "No image loaded!")
            return
            
        try:
            # Start progress
            self.progress_bar.setValue(10)
            
            # Make a copy of the original image and resize it
            preview_image = self.current_image.copy()
            new_size = (self.width_spin.value(), self.height_spin.value())
            
            # Using correct resampling method
            preview_image = preview_image.resize(new_size, Image.Resampling.LANCZOS)
            self.progress_bar.setValue(40)
            
            # Apply background removal if selected
            if self.remove_bg_check.isChecked() and REMBG_AVAILABLE:
                self.statusBar().showMessage('Removing background...')
                preview_image = self.apply_background_removal(preview_image)
                self.statusBar().showMessage('Background removed')
            self.progress_bar.setValue(80)
            
            # Always save preview as PNG to support transparency
            preview_image.save(self.temp_preview_path, format="PNG")
            
            # Display preview
            self.display_image(self.temp_preview_path)
            self.statusBar().showMessage(f'Preview: {new_size[0]}x{new_size[1]}')
            self.progress_bar.setValue(100)
            
            # Reset progress bar after a delay
            QTimer.singleShot(1000, lambda: self.progress_bar.setValue(0))
        except Exception as e:
            self.progress_bar.setValue(0)
            QMessageBox.critical(self, "Error", f"Preview failed: {str(e)}")
            logger.error(f"Preview error: {str(e)}")
            import traceback
            traceback.print_exc()
            logger.error(traceback.format_exc())
    
    def save_image(self):
        if self.current_image is None:
            QMessageBox.warning(self, "Warning", "No image loaded!")
            return
        
        # Determine file extension based on selected format
        format_mapping = {
            "JPEG": ".jpg",
            "PNG": ".png",
            "BMP": ".bmp",
            "TIFF": ".tiff",
            "GIF": ".gif",
            "WEBP": ".webp",
            "ICO": ".ico",
            "SVG": ".svg"
        }
        
        selected_format = self.format_combo.currentText()
        file_ext = format_mapping[selected_format]
        
        # Warning for transparency with JPEG
        if selected_format == "JPEG" and self.remove_bg_check.isChecked():
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Warning)
            msg.setText("JPEG format doesn't support transparency!")
            msg.setInformativeText("The transparent background will be replaced with white. Do you want to continue?")
            msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            if msg.exec_() == QMessageBox.No:
                self.format_combo.setCurrentText("PNG")
                selected_format = "PNG"
                file_ext = ".png"
        
        # Open save dialog with selected format
        file_path, _ = QFileDialog.getSaveFileName(
            self, 'Save Image', '', f'{selected_format} Files (*{file_ext})')
        
        if not file_path:
            return
            
        # Add extension if not present
        if not file_path.lower().endswith(file_ext.lower()):
            file_path += file_ext
        
        try:
            # Prepare the image
            self.progress_bar.setValue(20)
            img_to_save = self.current_image.copy()
            
            # Resize the image
            new_size = (self.width_spin.value(), self.height_spin.value())
            img_to_save = img_to_save.resize(new_size, Image.Resampling.LANCZOS)
            self.progress_bar.setValue(40)
            
            # Apply background removal if selected and format supports it
            if self.remove_bg_check.isChecked() and REMBG_AVAILABLE and selected_format != "SVG":
                self.statusBar().showMessage('Removing background...')
                img_to_save = self.apply_background_removal(img_to_save)
                self.statusBar().showMessage('Background removed')
            self.progress_bar.setValue(80)
            
            # Save with appropriate format and options
            if selected_format == "JPEG":
                # JPEG doesn't support alpha, use white background
                if img_to_save.mode == 'RGBA':
                    white_bg = Image.new('RGBA', img_to_save.size, (255, 255, 255, 255))
                    img_to_save = Image.alpha_composite(white_bg, img_to_save).convert('RGB')
                img_to_save.save(file_path, quality=self.quality_slider.value())
                
            elif selected_format == "ICO":
                # Create a list of sizes for the icon
                sizes = []
                if self.size_16.isChecked(): sizes.append((16, 16))
                if self.size_32.isChecked(): sizes.append((32, 32))
                if self.size_48.isChecked(): sizes.append((48, 48))
                if self.size_64.isChecked(): sizes.append((64, 64))
                if self.size_128.isChecked(): sizes.append((128, 128))
                if self.size_256.isChecked(): sizes.append((256, 256))
                
                if not sizes:  # If no sizes selected, use default
                    sizes = [(32, 32)]
                
                # Create images for each size
                img_to_save.save(file_path, format="ICO", sizes=sizes)
                
            elif selected_format == "SVG":
                # Use direct conversion with the specified quality
                self.save_as_svg_direct(img_to_save, file_path, self.svg_quality_slider.value())
                
            else:
                img_to_save.save(file_path)
            
            self.progress_bar.setValue(100)
            QMessageBox.information(self, "Success", f"Image saved as {os.path.basename(file_path)}")
            
            # Reset progress bar after a delay
            QTimer.singleShot(1500, lambda: self.progress_bar.setValue(0))
        except Exception as e:
            self.progress_bar.setValue(0)
            QMessageBox.critical(self, "Error", f"Failed to save image: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def save_as_svg_direct(self, img, file_path, quality=85):
        """Convert image to SVG using direct embedding."""
        try:
            # Convert the image to PNG in memory with the specified quality
            png_buffer = io.BytesIO()
            img.save(png_buffer, format="PNG", quality=quality)
            png_data = png_buffer.getvalue()
            
            # Create the SVG with embedded PNG
            width, height = img.size
            svg = f'''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
            <svg xmlns="http://www.w3.org/2000/svg" 
                 xmlns:xlink="http://www.w3.org/1999/xlink" 
                 width="{width}" height="{height}" viewBox="0 0 {width} {height}">
                <image width="{width}" height="{height}" 
                       xlink:href="data:image/png;base64,{base64.b64encode(png_data).decode('ascii')}"/>
            </svg>'''
            
            # Write SVG to file
            with open(file_path, 'w') as f:
                f.write(svg)
        except Exception as e:
            logger.error(f"SVG conversion error: {str(e)}")
            logger.error(traceback.format_exc())
            raise e

    def format_changed(self, format_name):
        """Handle changes to the output format selection."""
        # Show/hide format-specific options
        self.ico_options_group.setVisible(format_name == "ICO")
        self.svg_options_group.setVisible(format_name == "SVG")
        
        # Disable background removal for SVG (not compatible)
        if format_name == "SVG":
            self.remove_bg_check.setEnabled(False)
            self.remove_bg_check.setChecked(False)
            self.remove_bg_check.setToolTip("Background removal is not compatible with SVG format")
        else:
            self.remove_bg_check.setEnabled(REMBG_AVAILABLE)
            self.remove_bg_check.setToolTip(f"Background removal: {'Available' if REMBG_AVAILABLE else 'Not Available'}")
    
    def closeEvent(self, event):
        """Clean up temporary files when closing the application."""
        try:
            if os.path.exists(self.temp_preview_path):
                os.remove(self.temp_preview_path)
            
            # Optional: remove temp directory if empty
            if os.path.exists(self.temp_dir) and not os.listdir(self.temp_dir):
                os.rmdir(self.temp_dir)
        except:
            pass
        logger.info("Application closed")
        super().closeEvent(event)

    def install_svg_dependencies(self):
        """Install the svglib package using pip."""
        try:
            self.statusBar().showMessage('Installing SVG dependencies...')
            
            # Create a message box with progress information
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Information)
            msg.setWindowTitle("Installing SVG Dependencies")
            msg.setText("Installing SVG conversion libraries...\n\nThis might take a few minutes.")
            msg.setDetailedText("This will install:\n- svglib (for SVG rendering)\n- reportlab (required by svglib)")
            msg.setStandardButtons(QMessageBox.NoButton)
            msg.show()
            QApplication.processEvents()
            
            # Get Python executable path and pip paths
            python_exe = sys.executable
            scripts_dir = os.path.join(os.path.dirname(python_exe), 'Scripts')
            pip_path = os.path.join(scripts_dir, 'pip.exe') if os.name == 'nt' else os.path.join(scripts_dir, 'pip')
            if not os.path.exists(pip_path):
                pip_path = python_exe
                pip_args = ["-m", "pip"]
            else:
                pip_args = []
            
            # Log installation information
            logger.info(f"Using Python: {python_exe}")
            logger.info(f"Using pip: {pip_path}")
            
            # Install packages
            packages = []
            
            # Check if svglib is already installed
            if importlib.util.find_spec('svglib') is None:
                packages.append("svglib")
                packages.append("reportlab")  # Required dependency for svglib
            
            # If nothing to install
            if not packages:
                msg.close()
                QMessageBox.information(self, "Already Installed", 
                                      "All SVG dependencies are already installed.")
                self.statusBar().showMessage('All dependencies already installed')
                return
                
            # Install the packages
            install_args = [pip_path] + pip_args + ["install", "--upgrade"] + packages
            logger.info(f"Install command: {' '.join(install_args)}")
            
            result = subprocess.run(install_args, capture_output=True, text=True)
            
            # Log installation result
            logger.info(f"Installation return code: {result.returncode}")
            logger.info(f"Installation stdout: {result.stdout}")
            if result.stderr:
                logger.warning(f"Installation stderr: {result.stderr}")
            
            msg.close()
            
            # Check if installation was successful
            if result.returncode == 0:
                # Check if svglib was installed
                global SVGLIB_AVAILABLE
                was_svglib_available = SVGLIB_AVAILABLE
                initialize_svglib()
                
                # Update the status label
                self.svglib_status_label.setText(f"SVG Library: {'Available' if SVGLIB_AVAILABLE else 'Not Available'}")
                self.svglib_status_label.setStyleSheet(
                    "color: #00AA00; font-weight: bold;" if SVGLIB_AVAILABLE else "color: #FF5500; font-weight: bold;"
                )
                
                # Show a success message
                if SVGLIB_AVAILABLE:
                    QMessageBox.information(
                        self, "Success", 
                        "SVG dependencies have been installed successfully and are now available for use."
                    )
                else:
                    QMessageBox.warning(
                        self, "Installation Issue", 
                        "SVG libraries were installed but are still not detected.\n\n"
                        "Please try installing them manually with 'pip install svglib reportlab'."
                    )
            else:
                error_msg = f"Error installing SVG dependencies:\n\n{result.stderr}"
                QMessageBox.critical(self, "Installation Error", error_msg)
                logger.error(error_msg)
                
            self.statusBar().showMessage('Ready')
        except Exception as e:
            QMessageBox.critical(self, "Installation Error", 
                               f"Failed to install SVG dependencies: {str(e)}\n\nCheck the log file for details.")
            logger.error(f"Installation error: {str(e)}")
            logger.error(traceback.format_exc())

def main():
    app = QApplication(sys.argv)
    window = ImageEditorApp()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
