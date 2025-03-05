# Image Editor with Background Removal

## About Rembg

Rembg is a Python package that's used in this application to remove backgrounds from images. It uses deep learning models (specifically U2Net) to automatically detect and remove image backgrounds.

### How Rembg Works:

1. It analyzes the image to distinguish between foreground objects and background
2. It creates an alpha mask that identifies the areas to keep and remove
3. It applies this mask to the original image, making the background transparent (for PNG output)

### Installation:

Rembg is installed automatically from PyPI when you install this application's requirements:

```bash
pip install -r requirements.txt
```

If the automatic installation fails, you can manually install it using:

```bash
pip install rembg
```

For GPU acceleration (recommended for faster processing):

```bash
pip install rembg[gpu]
```

Note: The GPU version requires a CUDA-compatible graphics card and properly installed CUDA drivers.

## Troubleshooting Rembg Issues

If you encounter issues with background removal:

1. Check that rembg is properly installed (`pip list | grep rembg`)
2. Use the "Refresh Status" button in the application to check if rembg is detected
3. If not detected, use the "Install/Reinstall rembg" button
4. You may need to restart the application after installation
5. First time use may download model files which requires an internet connection (~130MB)
6. Check that your Python environment has access to the internet to download the models
7. Ensure you have at least 2GB of free disk space for models

### Common Issues:

- **ImportError**: Could mean the package is not installed or in the wrong Python environment
- **Session creation error**: Could mean the model files are missing or corrupted
- **Memory errors**: Large images may require more RAM than available
- **CUDA errors**: GPU acceleration requires proper NVIDIA drivers

For detailed logs, check the `image_editor.log` file in the application directory.

