import sys
import os
from PyQt5.QtWidgets import (QApplication, QMainWindow, QLabel, QPushButton, 
                           QVBoxLayout, QHBoxLayout, QWidget, QFileDialog,
                           QSpinBox, QComboBox, QSlider, QMessageBox, QGroupBox,
                           QSizePolicy, QProgressBar, QCheckBox, QToolBar, QAction)
from PyQt5.QtGui import QPixmap, QImage, QPalette, QColor, QIcon, QPainter, QBrush, QKeySequence
from PyQt5.QtCore import Qt, QSize, QTimer, QThread, pyqtSignal, QRect
from PIL import Image, ImageQt
import numpy as np
import subprocess
import importlib
import site
import traceback
import io
import base64  # For SVG encoding

# Dummy logger that does nothing
class DummyLogger:
    def __init__(self, *args, **kwargs):
        pass
    
    def info(self, *args, **kwargs):
        pass
    
    def warning(self, *args, **kwargs):
        pass
    
    def error(self, *args, **kwargs):
        pass

# Replace logger with dummy logger that does nothing
logger = DummyLogger()

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

class ZoomableImageLabel(TransparentBackgroundLabel):
    """Extended QLabel that supports zooming and panning."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_pixmap = None
        self.current_pixmap = None
        self.zoom_factor = 1.0
        self.zoom_step = 0.1  # 10% zoom per step
        self.min_zoom = 0.1   # Minimum zoom level (10%)
        self.max_zoom = 5.0   # Maximum zoom level (500%)
        
        # For panning support
        self.panning = False
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.pan_offset_x = 0
        self.pan_offset_y = 0
        
        # Enable mouse tracking
        self.setMouseTracking(True)
        
        # Allow focus to receive key events
        self.setFocusPolicy(Qt.StrongFocus)
        
    def setPixmap(self, pixmap):
        """Override setPixmap to store the original for zooming."""
        if pixmap and not pixmap.isNull():
            self.original_pixmap = pixmap
            self.current_pixmap = pixmap
            self.zoom_factor = 1.0
            self.pan_offset_x = 0
            self.pan_offset_y = 0
            self.update_display()
        else:
            super().setPixmap(pixmap)
    
    def update_display(self):
        """Update the displayed image with current zoom and pan settings."""
        if self.original_pixmap and not self.original_pixmap.isNull():
            # Calculate scaled size
            new_width = int(self.original_pixmap.width() * self.zoom_factor)
            new_height = int(self.original_pixmap.height() * self.zoom_factor)
            
            # Scale the pixmap
            if new_width > 0 and new_height > 0:
                scaled_pixmap = self.original_pixmap.scaled(
                    new_width, 
                    new_height,
                    Qt.KeepAspectRatio, 
                    Qt.SmoothTransformation
                )
                
                self.current_pixmap = scaled_pixmap
                super().setPixmap(scaled_pixmap)
    
    def update_cursor(self):
        """Update cursor based on current state."""
        if self.panning:
            self.setCursor(Qt.ClosedHandCursor)  # Grabbing hand
        else:
            self.setCursor(Qt.OpenHandCursor)    # Hand for panning
    
    def zoom_in(self):
        """Zoom in by one step."""
        if self.original_pixmap and not self.original_pixmap.isNull():
            old_zoom = self.zoom_factor
            self.zoom_factor = min(self.zoom_factor + self.zoom_step, self.max_zoom)
            if old_zoom != self.zoom_factor:
                self.update_display()
                self.update_cursor()
                return True
        return False
    
    def zoom_out(self):
        """Zoom out by one step."""
        if self.original_pixmap and not self.original_pixmap.isNull():
            old_zoom = self.zoom_factor
            self.zoom_factor = max(self.zoom_factor - self.zoom_step, self.min_zoom)
            if old_zoom != self.zoom_factor:
                self.update_display()
                self.update_cursor()
                return True
        return False
    
    def reset_zoom(self):
        """Reset zoom to 100%."""
        if self.original_pixmap and not self.original_pixmap.isNull():
            old_zoom = self.zoom_factor
            self.zoom_factor = 1.0
            self.pan_offset_x = 0
            self.pan_offset_y = 0
            if old_zoom != self.zoom_factor:
                self.update_display()
                self.update_cursor()
                return True
        return False
    
    # Mouse event handlers for zooming and panning
    def wheelEvent(self, event):
        """Handle mouse wheel events for zooming."""
        if self.original_pixmap and not self.original_pixmap.isNull():
            # Get the angle delta
            delta = event.angleDelta().y()
            
            # Zoom in or out based on wheel direction
            if delta > 0:
                self.zoom_in()
            else:
                self.zoom_out()
    
    def mousePressEvent(self, event):
        """Handle mouse press for panning."""
        if event.button() == Qt.LeftButton:
            # Allow panning at any zoom level (not just when zoomed in)
            self.panning = True
            self.pan_start_x = event.x()
            self.pan_start_y = event.y()
            self.update_cursor()
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for panning."""
        if self.panning:
            # Calculate movement delta
            delta_x = event.x() - self.pan_start_x
            delta_y = event.y() - self.pan_start_y
            
            # Update panning offset
            self.pan_offset_x += delta_x
            self.pan_offset_y += delta_y
            
            # Reset start position
            self.pan_start_x = event.x()
            self.pan_start_y = event.y()
            
            # Update the display with new offset
            self.update()
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release to end panning."""
        if event.button() == Qt.LeftButton and self.panning:
            self.panning = False
            self.update_cursor()
    
    def paintEvent(self, event):
        """Custom paint event to handle panning."""
        if self.current_pixmap and not self.current_pixmap.isNull():
            painter = QPainter(self)
            
            # Draw the checkered background first (for transparent images)
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
            
            # Calculate position to center the image in the view
            x = (self.width() - self.current_pixmap.width()) / 2 + self.pan_offset_x
            y = (self.height() - self.current_pixmap.height()) / 2 + self.pan_offset_y
            
            # Draw the pixmap with panning offset
            painter.drawPixmap(int(x), int(y), self.current_pixmap)
        else:
            # Fall back to default paint behavior for normal display
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
        
        # Initialize history for undo/redo
        self.history = []
        self.history_position = -1
        self.max_history = 20  # Maximum number of states to store
        
        # Enable drag and drop
        self.setAcceptDrops(True)
        
        self.initUI()
        
        # Initialize variables
        self.current_image = None
        self.current_image_path = None
        self.original_image = None
        self.original_size = (0, 0)
        self.temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp")
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
        self.temp_preview_path = os.path.join(self.temp_dir, "temp_preview.png")
        
        # Show welcome dialog with new features information
        self.show_welcome_dialog()
        
        # Log initialization
        logger.info(f"Application started. Dark mode: {self.is_dark_mode}")
        logger.info(f"rembg available: {REMBG_AVAILABLE}")
        
    def initUI(self):
        # Set window properties
        self.setWindowTitle("Image Editor with Background Removal")
        self.setMinimumSize(1000, 600)
        
        # Create toolbar
        self.toolbar = QToolBar("Main Toolbar")
        self.addToolBar(self.toolbar)
        
        # Add dark mode toggle action
        icon_name = "moon.png" if not self.is_dark_mode else "sun.png"
        self.theme_action = QAction(f"{'Dark' if not self.is_dark_mode else 'Light'} Mode", self)
        self.theme_action.triggered.connect(self.toggle_theme)
        self.toolbar.addAction(self.theme_action)
        
        # Add undo/redo actions with keyboard shortcuts
        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcut(QKeySequence.Undo)  # Ctrl+Z
        self.undo_action.triggered.connect(self.undo)
        self.undo_action.setEnabled(False)
        self.toolbar.addAction(self.undo_action)
        
        self.redo_action = QAction("Redo", self)
        self.redo_action.setShortcut(QKeySequence.Redo)  # Ctrl+Y or Ctrl+Shift+Z
        self.redo_action.triggered.connect(self.redo)
        self.redo_action.setEnabled(False)
        self.toolbar.addAction(self.redo_action)
        
        # Add more common actions with keyboard shortcuts
        self.open_action = QAction("Open", self)
        self.open_action.setShortcut(QKeySequence.Open)  # Ctrl+O
        self.open_action.triggered.connect(self.load_image)
        self.toolbar.addAction(self.open_action)
        
        self.save_action = QAction("Save", self)
        self.save_action.setShortcut(QKeySequence.Save)  # Ctrl+S
        self.save_action.triggered.connect(self.save_image)
        self.toolbar.addAction(self.save_action)
        
        # Add separator in toolbar
        self.toolbar.addSeparator()
        
        # Add zoom controls to toolbar
        self.zoom_in_action = QAction("Zoom In", self)
        self.zoom_in_action.setShortcut(QKeySequence("Ctrl++"))  # Ctrl+Plus
        self.zoom_in_action.triggered.connect(self.zoom_in_action_triggered)
        self.toolbar.addAction(self.zoom_in_action)
        
        self.zoom_out_action = QAction("Zoom Out", self)
        self.zoom_out_action.setShortcut(QKeySequence("Ctrl+-"))  # Ctrl+Minus
        self.zoom_out_action.triggered.connect(self.zoom_out_action_triggered)
        self.toolbar.addAction(self.zoom_out_action)
        
        self.zoom_reset_action = QAction("Reset Zoom", self)
        self.zoom_reset_action.setShortcut(QKeySequence("Ctrl+0"))  # Ctrl+0
        self.zoom_reset_action.triggered.connect(self.zoom_reset_action_triggered)
        self.toolbar.addAction(self.zoom_reset_action)
        
        # Add separator in toolbar
        self.toolbar.addSeparator()
        
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
        
        # Image display area - Use custom label for transparent images
        self.image_label = ZoomableImageLabel("No image loaded")
        self.image_label.set_dark_mode(self.is_dark_mode)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(400, 300)
        bg_color = "#1E1E1E" if self.is_dark_mode else "#FFFFFF"
        self.image_label.setStyleSheet(f"border: 2px dashed #555555; background-color: {bg_color};")
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout.addWidget(self.image_label)
        
        # Add zoom info label below the image
        self.zoom_info_label = QLabel("Zoom: 100%")
        self.zoom_info_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.zoom_info_label)
        
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
        
        # Add zoom controls to the load panel
        zoom_layout = QHBoxLayout()
        self.zoom_in_btn = QPushButton("Zoom In")
        self.zoom_in_btn.clicked.connect(self.zoom_in_action_triggered)
        self.zoom_in_btn.setToolTip("Zoom in (Ctrl++)")
        
        self.zoom_out_btn = QPushButton("Zoom Out")
        self.zoom_out_btn.clicked.connect(self.zoom_out_action_triggered)
        self.zoom_out_btn.setToolTip("Zoom out (Ctrl+-)")
        
        self.zoom_reset_btn = QPushButton("Reset Zoom")
        self.zoom_reset_btn.clicked.connect(self.zoom_reset_action_triggered)
        self.zoom_reset_btn.setToolTip("Reset zoom to 100% (Ctrl+0)")
        
        zoom_layout.addWidget(self.zoom_in_btn)
        zoom_layout.addWidget(self.zoom_out_btn)
        load_layout.addLayout(zoom_layout)
        load_layout.addWidget(self.zoom_reset_btn)
        
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
        self.maintain_ratio = False
        self.ratio_btn = QPushButton("Maintain Ratio: OFF")
        self.ratio_btn.setCheckable(True)
        self.ratio_btn.setChecked(False)
        self.ratio_btn.clicked.connect(self.toggle_aspect_ratio)
        resize_layout.addWidget(self.ratio_btn)
        
        # Preview button
        self.preview_btn = QPushButton("Apply Changes")
        self.preview_btn.clicked.connect(self.preview_changes)
        self.preview_btn.setToolTip("Apply resize and other changes (Ctrl+P)")
        # Add keyboard shortcut for preview
        preview_shortcut = QKeySequence("Ctrl+P")
        self.preview_action = QAction("Preview", self)
        self.preview_action.setShortcut(preview_shortcut)
        self.preview_action.triggered.connect(self.preview_changes)
        self.toolbar.addAction(self.preview_action)
        resize_layout.addWidget(self.preview_btn)
        
        controls_layout.addWidget(resize_group)
        
        # Add Transform panel for rotation and flipping
        transform_group = QGroupBox("Transform")
        transform_layout = QVBoxLayout(transform_group)
        
        # Rotation buttons
        rotation_layout = QHBoxLayout()
        self.rotate_90_btn = QPushButton("Rotate 90°")
        self.rotate_90_btn.clicked.connect(lambda: self.rotate_image(90))
        self.rotate_90_btn.setToolTip("Rotate image 90 degrees clockwise")
        
        self.rotate_180_btn = QPushButton("Rotate 180°")
        self.rotate_180_btn.clicked.connect(lambda: self.rotate_image(180))
        self.rotate_180_btn.setToolTip("Rotate image 180 degrees")
        
        self.rotate_270_btn = QPushButton("Rotate 270°")
        self.rotate_270_btn.clicked.connect(lambda: self.rotate_image(270))
        self.rotate_270_btn.setToolTip("Rotate image 270 degrees clockwise (90 degrees counterclockwise)")
        
        rotation_layout.addWidget(self.rotate_90_btn)
        rotation_layout.addWidget(self.rotate_180_btn)
        rotation_layout.addWidget(self.rotate_270_btn)
        transform_layout.addLayout(rotation_layout)
        
        # Fine rotation arrows
        fine_rotation_layout = QHBoxLayout()
        fine_rotation_layout.addWidget(QLabel("Fine Rotation:"))
        
        self.rotate_left_btn = QPushButton("↺")  # Counter-clockwise arrow
        self.rotate_left_btn.clicked.connect(lambda: self.rotate_image_fine(-5))
        self.rotate_left_btn.setToolTip("Rotate 5° counter-clockwise")
        self.rotate_left_btn.setMaximumWidth(40)
        
        self.rotate_right_btn = QPushButton("↻")  # Clockwise arrow
        self.rotate_right_btn.clicked.connect(lambda: self.rotate_image_fine(5))
        self.rotate_right_btn.setToolTip("Rotate 5° clockwise")
        self.rotate_right_btn.setMaximumWidth(40)
        
        fine_rotation_layout.addWidget(self.rotate_left_btn)
        fine_rotation_layout.addWidget(self.rotate_right_btn)
        transform_layout.addLayout(fine_rotation_layout)
        
        # Flip buttons
        flip_layout = QHBoxLayout()
        self.flip_h_btn = QPushButton("Flip Horizontal")
        self.flip_h_btn.clicked.connect(lambda: self.flip_image("horizontal"))
        self.flip_h_btn.setToolTip("Flip image horizontally (mirror)")
        
        self.flip_v_btn = QPushButton("Flip Vertical")
        self.flip_v_btn.clicked.connect(lambda: self.flip_image("vertical"))
        self.flip_v_btn.setToolTip("Flip image vertically (upside down)")
        
        flip_layout.addWidget(self.flip_h_btn)
        flip_layout.addWidget(self.flip_v_btn)
        transform_layout.addLayout(flip_layout)
        
        controls_layout.addWidget(transform_group)
        
        # Background removal
        bg_group = QGroupBox("Background Removal")
        bg_layout = QVBoxLayout(bg_group)
        
        self.remove_bg_check = QCheckBox("Remove Background")
        self.remove_bg_btn = QPushButton("Remove Background")
        self.remove_bg_btn.clicked.connect(lambda: self.apply_background_removal(self.current_image))
        self.remove_bg_btn.setToolTip("Remove the background from the image (Ctrl+B)")
        # Add keyboard shortcut for background removal
        bg_shortcut = QKeySequence("Ctrl+B")
        self.bg_action = QAction("Remove Background", self)
        self.bg_action.setShortcut(bg_shortcut)
        self.bg_action.triggered.connect(lambda: self.apply_background_removal(self.current_image))
        self.toolbar.addAction(self.bg_action)
        
        bg_layout.addWidget(self.remove_bg_btn)
        controls_layout.addWidget(bg_group)
        
        # Format panel
        format_group = QGroupBox("Format Options")
        format_layout = QVBoxLayout(format_group)
        
        format_layout.addWidget(QLabel("Output Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["JPEG", "PNG", "BMP", "TIFF", "GIF", "WEBP", "ICO", "SVG"])
        self.format_combo.currentTextChanged.connect(self.format_changed)
        format_layout.addWidget(self.format_combo)
        
        # Background removal option
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
        
        # Update theme action text
        self.theme_action.setText(f"{'Dark' if not self.is_dark_mode else 'Light'} Mode")
        
        # Apply appropriate stylesheet based on theme
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
        """Open file dialog to select and load an image."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, 'Open Image', '', 'Image Files (*.png *.jpg *.jpeg *.bmp *.tiff *.gif *.webp)')
        
        if file_path:
            self.load_image_from_path(file_path)
    
    def display_image(self, image_path):
        """Display an image in the UI from a file path."""
        if not os.path.exists(image_path):
            logger.error(f"Image file not found: {image_path}")
            return
            
        try:
            # Load the image with PIL, preserving transparency
            img = Image.open(image_path)
            
            # Ensure we keep transparency information
            if img.format == 'PNG' and img.mode != 'RGBA':
                img = img.convert('RGBA')
                
            self.original_image = img.copy()  # Store the original image
            self.current_image = img.copy()   # Store a copy as the current working image
            self.current_image_path = image_path
            self.original_size = img.size
            
            # Update width and height spinners
            self.width_spin.setValue(self.original_size[0])
            self.height_spin.setValue(self.original_size[1])
            
            # Display the image
            self.display_pil_image(self.current_image)
            
            # Clear the history and save initial state
            self.history = []
            self.history_position = -1
            self.save_state()
            
            # Update status
            self.statusBar().showMessage(f"Loaded: {os.path.basename(image_path)} - {self.original_size[0]}x{self.original_size[1]} - Mode: {img.mode}")
            logger.info(f"Displayed image: {image_path} with mode {img.mode}")
        except Exception as e:
            logger.error(f"Error displaying image: {str(e)}")
            QMessageBox.critical(self, "Error", f"Could not display image: {str(e)}")
    
    def update_height_maintain_ratio(self):
        if self.maintain_ratio and self.original_size[0] > 0:
            ratio = self.original_size[1] / self.original_size[0]
            new_height = int(self.width_spin.value() * ratio)
            self.height_spin.blockSignals(True)
            self.height_spin.setValue(new_height)
            self.height_spin.blockSignals(False)
        # If maintain_ratio is false, do nothing - let the user set any value
    
    def update_width_maintain_ratio(self):
        if self.maintain_ratio and self.original_size[1] > 0:
            ratio = self.original_size[0] / self.original_size[1]
            new_width = int(self.height_spin.value() * ratio)
            self.width_spin.blockSignals(True)
            self.width_spin.setValue(new_width)
            self.width_spin.blockSignals(False)
        # If maintain_ratio is false, do nothing - let the user set any value
    
    def toggle_aspect_ratio(self):
        self.maintain_ratio = self.ratio_btn.isChecked()
        self.ratio_btn.setText(f"Maintain Ratio: {'ON' if self.maintain_ratio else 'OFF'}")
    
    def update_quality_label(self):
        self.quality_value.setText(f"{self.quality_slider.value()}%")
    
    def update_svg_quality_label(self):
        """Update the SVG quality slider value label."""
        self.svg_quality_value.setText(f"{self.svg_quality_slider.value()}%")
    
    def apply_background_removal(self, img):
        """Remove background from image using rembg."""
        if not REMBG_AVAILABLE:
            QMessageBox.warning(self, "Feature Not Available", 
                               "Background removal is not available because the 'rembg' package is not installed.\n\n"
                               "Click the 'Install rembg' button in the status panel to install it.")
            return
            
        # Save current state before background removal
        self.save_state()
            
        # Show progress bar
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        
        # Create and start background thread
        self.bg_thread = BackgroundRemovalThread(img)
        self.bg_thread.progress.connect(self.update_progress)
        self.bg_thread.finished.connect(self.on_bg_removal_finished)
        self.bg_thread.error.connect(self.on_bg_removal_error)
        self.bg_thread.start()
        
        logger.info("Background removal started")
    
    def on_bg_removal_finished(self, result_image):
        """Handle the completion of background removal thread."""
        # Ensure the result maintains RGBA mode for transparency
        if result_image.mode != 'RGBA':
            result_image = result_image.convert('RGBA')
            
        self.current_image = result_image
        
        # Display the image with transparency
        self.display_pil_image(self.current_image)
        
        self.statusBar().showMessage('Background removed')
        logger.info(f"Background removal completed. Image mode: {self.current_image.mode}")
    
    def on_bg_removal_error(self, error_message):
        """Handle errors from background removal thread."""
        self.statusBar().showMessage(f'Background removal failed: {error_message}')
        QMessageBox.warning(self, "Background Removal Error", 
                           f"Failed to remove background:\n{error_message}")
        logger.error(f"Background removal error: {error_message}")
    
    def update_progress(self, value):
        """Update the progress bar based on thread progress."""
        self.progress_bar.setValue(value)
    
    def preview_changes(self):
        """Preview the changes based on current settings."""
        if self.current_image is None:
            return
            
        # Save current state for undo/redo
        self.save_state()
            
        # Make a copy of the original image and resize it
        if self.original_image:
            preview_image = self.original_image.copy()
            new_size = (self.width_spin.value(), self.height_spin.value())
            
            # Preserve original image mode to maintain transparency
            original_mode = preview_image.mode
            
            # Perform resize operation while preserving transparency
            preview_image = preview_image.resize(new_size, Image.Resampling.LANCZOS)
            
            # Make sure we keep the original mode (RGBA for transparent images)
            if original_mode == 'RGBA' and preview_image.mode != 'RGBA':
                preview_image = preview_image.convert('RGBA')
            
            # Update the current image with the preview
            self.current_image = preview_image
            
            # Display the preview image
            self.display_pil_image(self.current_image)
            logger.info(f"Image preview updated. New size: {new_size}, Mode: {self.current_image.mode}")
        else:
            logger.error("No original image to preview changes on")
    
    def save_image(self):
        """Save the current image to a file."""
        if self.current_image is None:
            QMessageBox.warning(self, "Warning", "No image to save!")
            return
            
        try:
            # Get the desired format
            selected_format = self.format_combo.currentText()
            default_extension = ".png" if selected_format == "PNG" else ".jpg"
            
            # Get save location from user
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save Image", 
                os.path.splitext(os.path.basename(self.current_image_path))[0] + default_extension,
                "Images (*.png *.jpg *.jpeg *.svg)"
            )
            
            if not file_path:  # User canceled
                return
                
            # Prepare a copy of the image for saving
            img_to_save = self.current_image.copy()
                
            # Get file extension
            _, ext = os.path.splitext(file_path)
            ext = ext.lower()
            
            # Quality value
            quality = self.quality_slider.value()
            
            # Check if we need to save as SVG
            if ext == '.svg':
                if SVGLIB_AVAILABLE:
                    self.save_as_svg_direct(img_to_save, file_path, quality)
                else:
                    QMessageBox.warning(self, "SVG Support Not Available", 
                                      "SVG export is not available because the required packages are not installed.\n\n"
                                      "Click 'Install SVG Support' in the status panel.")
                    return
            else:
                # Check if trying to save transparent image as JPEG
                if (ext == '.jpg' or ext == '.jpeg') and img_to_save.mode == 'RGBA':
                    # Warn the user that transparency will be lost
                    msg = QMessageBox()
                    msg.setIcon(QMessageBox.Warning)
                    msg.setWindowTitle("Transparency Warning")
                    msg.setText("JPEG format doesn't support transparency!")
                    msg.setInformativeText("The transparent background will be replaced with white. Continue with JPEG or save as PNG instead?")
                    
                    # Add custom buttons
                    continue_button = msg.addButton("Continue with JPEG", QMessageBox.YesRole)
                    png_button = msg.addButton("Save as PNG instead", QMessageBox.NoRole)
                    cancel_button = msg.addButton(QMessageBox.Cancel)
                    
                    msg.exec_()
                    
                    clicked_button = msg.clickedButton()
                    
                    if clicked_button == cancel_button:
                        return
                    elif clicked_button == png_button:
                        # Change to PNG format
                        ext = '.png'
                        file_path = os.path.splitext(file_path)[0] + '.png'
                        self.statusBar().showMessage(f"Changed format to PNG to preserve transparency")
                
                # Regular image save
                if ext == '.jpg' or ext == '.jpeg':
                    # Convert RGBA to RGB with white background for JPEG
                    if img_to_save.mode == 'RGBA':
                        # Create a white background
                        background = Image.new('RGB', img_to_save.size, (255, 255, 255))
                        # Paste the image using alpha as mask
                        background.paste(img_to_save, mask=img_to_save.split()[3])
                        img_to_save = background
                    # Make sure the image is in RGB mode
                    elif img_to_save.mode != 'RGB':
                        img_to_save = img_to_save.convert('RGB')
                        
                    img_to_save.save(file_path, format="JPEG", quality=quality)
                    
                elif ext == '.png':
                    # Ensure mode is RGBA if it has transparency
                    if 'A' in img_to_save.mode or img_to_save.mode == 'RGBA':
                        img_to_save = img_to_save.convert('RGBA')
                    img_to_save.save(file_path, format="PNG")
                else:
                    # Default to PNG for unknown formats
                    img_to_save.save(file_path, format="PNG")
                    
            self.statusBar().showMessage(f"Image saved to {file_path}")
            logger.info(f"Image saved to: {file_path} in mode {img_to_save.mode}")
            
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save image: {str(e)}")
            logger.error(f"Save error: {str(e)}")
            logger.error(traceback.format_exc())
    
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

    # Add new methods for undo/redo functionality
    def save_state(self):
        """Save current state to history"""
        if self.current_image is None:
            return
            
        # If we're not at the end of the history, truncate it
        if self.history_position < len(self.history) - 1:
            self.history = self.history[:self.history_position + 1]
            
        # Create a copy of the current image
        state = {
            'image': self.current_image.copy(),
            'width': self.width_spin.value(),
            'height': self.height_spin.value()
        }
        
        # Add to history
        self.history.append(state)
        
        # Enforce history limit
        if len(self.history) > self.max_history:
            self.history.pop(0)
        else:
            self.history_position = len(self.history) - 1
            
        # Enable/disable undo/redo buttons
        self.update_undo_redo_buttons()
        
    def update_undo_redo_buttons(self):
        """Update the enabled state of undo/redo buttons"""
        self.undo_action.setEnabled(self.history_position >= 0)
        self.redo_action.setEnabled(self.history_position < len(self.history) - 1)
        
    def undo(self):
        """Undo the last operation"""
        if self.history_position > 0:
            self.history_position -= 1
            self.restore_state(self.history[self.history_position])
            self.update_undo_redo_buttons()
            
    def redo(self):
        """Redo the last undone operation"""
        if self.history_position < len(self.history) - 1:
            self.history_position += 1
            self.restore_state(self.history[self.history_position])
            self.update_undo_redo_buttons()
            
    def restore_state(self, state):
        """Restore a saved state"""
        self.current_image = state['image'].copy()
        
        # Block signals to prevent recursive updates
        self.width_spin.blockSignals(True)
        self.height_spin.blockSignals(True)
        
        # Restore width and height
        self.width_spin.setValue(state['width'])
        self.height_spin.setValue(state['height'])
        
        # Unblock signals
        self.width_spin.blockSignals(False)
        self.height_spin.blockSignals(False)
        
        # Display the restored image
        self.display_pil_image(self.current_image)

    def display_pil_image(self, pil_image):
        """Display a PIL image in the UI"""
        if pil_image is None:
            return
            
        # Convert PIL image to QPixmap and display
        # Need to handle conversion differently to avoid type errors
        if pil_image.mode == "RGBA":
            # For RGBA images, we need to preserve transparency
            data = pil_image.tobytes("raw", "RGBA")
            qimage = QImage(data, pil_image.width, pil_image.height, QImage.Format_RGBA8888)
        else:
            # For other formats, convert to RGB first
            rgb_img = pil_image.convert("RGB")
            data = rgb_img.tobytes("raw", "RGB")
            qimage = QImage(data, rgb_img.width, rgb_img.height, QImage.Format_RGB888)
            
        pixmap = QPixmap.fromImage(qimage)
        
        # Scale pixmap to fit label while maintaining aspect ratio
        scaled_pixmap = pixmap.scaled(
            self.image_label.width(),
            self.image_label.height(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled_pixmap)

    def show_welcome_dialog(self):
        """Show a welcome dialog with information about new features."""
        welcome_msg = QMessageBox(self)
        welcome_msg.setWindowTitle("Welcome to Image Editor")
        welcome_msg.setIcon(QMessageBox.Information)
        welcome_msg.setText("Welcome to the improved Image Editor!")
        
        # Add information about new features
        features_text = """
<b>Features:</b>
<ul>
<li><b>NEW!</b> Image Rotation and Flipping - Rotate or flip your images with one click</li>
<li><b>NEW!</b> Zoom and Pan - Zoom with mouse wheel or Ctrl+/- and pan by dragging</li>
<li><b>NEW!</b> Drag and Drop Support - Drag image files directly into the editor</li>
<li>Independent width/height control - aspect ratio is now OFF by default</li>
<li>Dark/Light mode toggle in the toolbar</li>
<li>Undo/Redo support for all editing operations</li>
<li>Keyboard shortcuts:</li>
    <ul>
    <li>Ctrl+O: Open image</li>
    <li>Ctrl+S: Save image</li>
    <li>Ctrl+Z: Undo</li>
    <li>Ctrl+Y: Redo</li>
    <li>Ctrl+P: Apply Changes</li>
    <li>Ctrl+B: Remove Background</li>
    <li>Ctrl++: Zoom in</li>
    <li>Ctrl+-: Zoom out</li>
    <li>Ctrl+0: Reset zoom</li>
    </ul>
</ul>
"""
        welcome_msg.setInformativeText(features_text)
        welcome_msg.setStandardButtons(QMessageBox.Ok)
        welcome_msg.exec_()

    # Add drag and drop event handlers
    def dragEnterEvent(self, event):
        """Accept drag events if they contain image files."""
        # Check if the drag contains URLs (files)
        if event.mimeData().hasUrls():
            # Get the first URL
            url = event.mimeData().urls()[0]
            # Check if it's a local file
            if url.isLocalFile():
                file_path = url.toLocalFile()
                # Check if it's an image file by extension
                if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.gif', '.webp')):
                    # Add visual feedback
                    self.image_label.setStyleSheet(
                        "border: 3px dashed #007ACC; background-color: rgba(0, 122, 204, 0.1);"
                    )
                    event.acceptProposedAction()
                    return
        # If not an image file, don't accept
        event.ignore()
    
    def dragMoveEvent(self, event):
        """Allow the drag to move over the window."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dragLeaveEvent(self, event):
        """Reset the visual feedback when drag leaves."""
        # Reset the image label style
        bg_color = "#1E1E1E" if self.is_dark_mode else "#FFFFFF"
        self.image_label.setStyleSheet(f"border: 2px dashed #555555; background-color: {bg_color};")
        event.accept()
    
    def dropEvent(self, event):
        """Handle the dropped file."""
        # Reset the visual style first
        bg_color = "#1E1E1E" if self.is_dark_mode else "#FFFFFF"
        self.image_label.setStyleSheet(f"border: 2px dashed #555555; background-color: {bg_color};")
        
        if event.mimeData().hasUrls():
            # Get the first URL
            url = event.mimeData().urls()[0]
            # If it's a local file
            if url.isLocalFile():
                file_path = url.toLocalFile()
                # Check if it's an image file
                if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.gif', '.webp')):
                    # Load the image
                    self.load_image_from_path(file_path)
                    event.acceptProposedAction()
                    
                    # Show a status message
                    self.statusBar().showMessage(f"Image loaded from drag and drop: {os.path.basename(file_path)}")
                    return
        # If not an image file, don't accept
        event.ignore()
    
    # Add method to load image from path 
    def load_image_from_path(self, file_path):
        """Load an image from a file path."""
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
            logger.error(f"Error loading image: {str(e)}")
            logger.error(traceback.format_exc())

    def rotate_image(self, degrees):
        """Rotate the image by the specified degrees."""
        if self.current_image is None:
            QMessageBox.warning(self, "Warning", "No image to rotate!")
            return
            
        # Save current state for undo/redo
        self.save_state()
        
        try:
            # Rotate the image
            rotated_image = self.current_image.rotate(degrees, expand=True, resample=Image.Resampling.BICUBIC)
            
            # Update current image
            self.current_image = rotated_image
            
            # Update the display
            self.display_pil_image(self.current_image)
            
            # Update size info since rotation might change dimensions
            self.width_spin.setValue(self.current_image.width)
            self.height_spin.setValue(self.current_image.height)
            self.info_label.setText(f"Size: {self.current_image.width}x{self.current_image.height}")
            
            # Update status
            self.statusBar().showMessage(f"Image rotated {degrees} degrees")
            logger.info(f"Image rotated {degrees} degrees")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to rotate image: {str(e)}")
            logger.error(f"Rotation error: {str(e)}")
            logger.error(traceback.format_exc())
    
    def flip_image(self, direction):
        """Flip the image horizontally or vertically."""
        if self.current_image is None:
            QMessageBox.warning(self, "Warning", "No image to flip!")
            return
            
        # Save current state for undo/redo
        self.save_state()
        
        try:
            if direction == "horizontal":
                # Flip the image horizontally (left to right)
                flipped_image = self.current_image.transpose(Image.FLIP_LEFT_RIGHT)
                flip_desc = "horizontally"
            else:  # vertical
                # Flip the image vertically (top to bottom)
                flipped_image = self.current_image.transpose(Image.FLIP_TOP_BOTTOM)
                flip_desc = "vertically"
            
            # Update current image
            self.current_image = flipped_image
            
            # Update the display
            self.display_pil_image(self.current_image)
            
            # Update status
            self.statusBar().showMessage(f"Image flipped {flip_desc}")
            logger.info(f"Image flipped {flip_desc}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to flip image: {str(e)}")
            logger.error(f"Flip error: {str(e)}")
            logger.error(traceback.format_exc())

    def zoom_in_action_triggered(self):
        """Handler for zoom in button and shortcut."""
        if self.image_label.zoom_in():
            # Update the zoom info label
            zoom_percent = int(self.image_label.zoom_factor * 100)
            self.zoom_info_label.setText(f"Zoom: {zoom_percent}%")
            self.statusBar().showMessage(f"Zoomed in to {zoom_percent}%")
    
    def zoom_out_action_triggered(self):
        """Handler for zoom out button and shortcut."""
        if self.image_label.zoom_out():
            # Update the zoom info label
            zoom_percent = int(self.image_label.zoom_factor * 100)
            self.zoom_info_label.setText(f"Zoom: {zoom_percent}%")
            self.statusBar().showMessage(f"Zoomed out to {zoom_percent}%")
    
    def zoom_reset_action_triggered(self):
        """Handler for zoom reset button and shortcut."""
        if self.image_label.reset_zoom():
            # Update the zoom info label
            self.zoom_info_label.setText("Zoom: 100%")
            self.statusBar().showMessage("Zoom reset to 100%")

    def rotate_image_fine(self, degrees):
        """Rotate the image by a small angle without changing its size."""
        if self.current_image is None:
            QMessageBox.warning(self, "Warning", "No image to rotate!")
            return
            
        # Save current state for undo/redo
        self.save_state()
        
        try:
            # Get original dimensions
            original_width, original_height = self.current_image.size
            
            # For fine rotations, don't expand the canvas to keep the original dimensions
            rotated_image = self.current_image.rotate(degrees, expand=False, resample=Image.Resampling.BICUBIC)
            
            # Ensure we maintain original dimensions (may crop some edges for non-rectangular images)
            if rotated_image.size != (original_width, original_height):
                # Create a new image with original dimensions
                new_image = Image.new(rotated_image.mode, (original_width, original_height), (0, 0, 0, 0))
                
                # Calculate paste position to center the rotated image
                paste_x = (original_width - rotated_image.width) // 2
                paste_y = (original_height - rotated_image.height) // 2
                
                # Paste the rotated image
                new_image.paste(rotated_image, (paste_x, paste_y))
                rotated_image = new_image
            
            # Update current image
            self.current_image = rotated_image
            
            # Update the display
            self.display_pil_image(self.current_image)
            
            # Use appropriate sign for status message
            sign = "+" if degrees > 0 else ""
            self.statusBar().showMessage(f"Fine rotation: {sign}{degrees}°")
            logger.info(f"Fine rotation: {sign}{degrees} degrees")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to rotate image: {str(e)}")
            logger.error(f"Fine rotation error: {str(e)}")
            logger.error(traceback.format_exc())

def main():
    app = QApplication(sys.argv)
    window = ImageEditorApp()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
