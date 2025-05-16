import os
import sys
import time
import traceback

import numpy
import potrace as potracelib  # pypotrace library
import pyautogui
from PIL import Image, UnidentifiedImageError

# This script converts an image into a series of mouse drawing
# actions using PyAutoGUI. It leverages the Potrace library 
# to vectorize the image by tracing outlines. The resulting vector paths are then
# tessellated into line segments that PyAutoGUI can draw.

# --- Configuration ---
# Image Processing & Potrace Settings
DEFAULT_THRESHOLD_VALUE = 128 # Value (0-255) to distinguish black (to be traced) from white (background).
POTRACE_TURDSIZE = 2      # Suppress speckles (small paths) smaller than this size (pixels). Potrace default: 2.
                          # Lower values (e.g., 0 or 1) trace more, including very small details.
POTRACE_OPTTOLERANCE = 0.3 # Potrace curve optimization tolerance. Lower values (e.g., 0.2, pypotrace default)
                           # result in more detailed curves (less simplification).
POTRACE_ALPHAMAX = 1.0     # Potrace corner detection threshold. Default: 1.0.
                           # Range: 0.0 (polygons only) to 1.3333 (no corners, very smooth).

# Tessellation Settings (how Potrace curves are broken into straight lines for PyAutoGUI)
TESSELATE_METHOD = 'adaptive' # Options: 'adaptive' or 'regular'.
                            # 'adaptive' intelligently adds more points where curves are sharper.
                            # 'regular' divides curves into a fixed number of segments.
TESSELATE_RES = 15          # Resolution for 'regular' tessellation. Higher = smoother curves but more points/slower.
                            # This setting is generally ignored by the 'adaptive' method.

# Drawing Control
PYAUTOGUI_ACTION_PAUSE = 0.005 # Pause (seconds) between individual PyAutoGUI actions.
START_DRAW_DELAY = 5         # Seconds to wait before drawing starts, allowing time to switch windows.
SCALE_FACTOR = 1.1           # Scale of the final drawing. 1.0 = original image size, 0.5 = half, 2.0 = double.

# Border Skipping Heuristic
ATTEMPT_TO_SKIP_IMAGE_BORDER = True # If True, tries to detect and skip drawing paths that form a full-image border.
BORDER_DETECTION_PIXEL_TOLERANCE = 5 # Max distance (pixels) from image edge for a path to be considered part of a border.
BORDER_DETECTION_DIMENSION_MATCH_RATIO = 0.95 # Path width/height must be at least this ratio of image width/height
                                             # to be considered part of a border.
# --- End Configuration ---

def image_to_pyautogui_actions(
    image_path, threshold, turd_size, opt_tolerance, alphamax, scale_factor,
    skip_border_setting, border_pixel_tol, border_dim_ratio,
    tesselate_method_config, tesselate_res_config
):
    """
    Converts an image file to a list of PyAutoGUI drawing actions.

    Args:
        image_path (str): Path to the input image file.
        threshold (int): Value (0-255) for image binarization.
        turd_size (int): Potrace parameter to suppress small speckles.
        opt_tolerance (float): Potrace parameter for curve optimization.
        alphamax (float): Potrace parameter for corner detection.
        scale_factor (float): Factor by which to scale the drawing.
        skip_border_setting (bool): Whether to attempt skipping image borders.
        border_pixel_tol (int): Pixel tolerance for border detection.
        border_dim_ratio (float): Dimension ratio for border detection.
        tesselate_method_config (str): Tessellation method ('adaptive' or 'regular').
        tesselate_res_config (int): Resolution for 'regular' tessellation.

    Returns:
        list: A list of drawing actions for PyAutoGUI, or an empty list on error.
    """
    try:
        pil_img = Image.open(image_path)
    except FileNotFoundError:
        print(f"Error: Image file not found at '{image_path}'")
        return []
    except UnidentifiedImageError:
        print(f"Error: Cannot identify image file. Is it a valid image format (PNG, JPEG, etc.)? Path: '{image_path}'")
        return []
    except Exception as e:
        print(f"Error opening image: {e}")
        traceback.print_exc()
        return []

    img_width, img_height = pil_img.width, pil_img.height
    gray_img = pil_img.convert('L')
    # Create a binary image: 0 for parts darker than threshold (to be traced), 255 for lighter parts.
    bw_img = gray_img.point(lambda x: 0 if x < threshold else 255, '1')
    
    # For debugging the thresholding step, uncomment the next line:
    # bw_img.save("debug_thresholded_image.png")
    
    np_image_data = numpy.array(bw_img) # Potrace (pypotrace) expects a NumPy array.

    raw_actions_original_coords = []
    all_points_for_bbox_calculation = [] # Used for overall centering calculation.

    try:
        bitmap = potracelib.Bitmap(np_image_data)
        path_object = bitmap.trace(
            turdsize=turd_size,
            opttolerance=opt_tolerance,
            alphamax=alphamax
        )

        if not path_object or not path_object.curves:
            print("Warning: Potrace did not return any curves for the image.")
            return []

        for curve_idx, curve in enumerate(path_object.curves):
            if not curve.segments: # Skip curves that have no actual line/curve segments.
                continue

            current_curve_vertices_list = []
            if tesselate_method_config == 'regular':
                tesselated_vertices_np = curve.tesselate(method=potracelib.Curve.regular, res=TESSELATE_RES)
            else:
                tesselated_vertices_np = curve.tesselate(method=potracelib.Curve.adaptive)


            if tesselated_vertices_np.size == 0:
                continue
            
            for i in range(tesselated_vertices_np.shape[0]):
                current_curve_vertices_list.append((tesselated_vertices_np[i, 0], tesselated_vertices_np[i, 1]))
            
            # Need at least 2 points to draw a line.
            if not current_curve_vertices_list or len(current_curve_vertices_list) < 2:
                continue

            # Border Detection Logic
            if skip_border_setting:
                curve_min_x = min(p[0] for p in current_curve_vertices_list)
                curve_max_x = max(p[0] for p in current_curve_vertices_list)
                curve_min_y = min(p[1] for p in current_curve_vertices_list)
                curve_max_y = max(p[1] for p in current_curve_vertices_list)

                curve_width = curve_max_x - curve_min_x
                curve_height = curve_max_y - curve_min_y

                spans_almost_full_width = curve_width >= img_width * border_dim_ratio
                spans_almost_full_height = curve_height >= img_height * border_dim_ratio
                is_near_left_edge = curve_min_x <= border_pixel_tol
                is_near_right_edge = curve_max_x >= img_width - border_pixel_tol
                is_near_top_edge = curve_min_y <= border_pixel_tol
                is_near_bottom_edge = curve_max_y >= img_height - border_pixel_tol
                
                if (spans_almost_full_width and spans_almost_full_height and
                    is_near_left_edge and is_near_right_edge and
                    is_near_top_edge and is_near_bottom_edge):
                    print(f"INFO: Curve {curve_idx} appears to be an image border. Skipping.")
                    continue # Skip this curve

            # If not a skipped border, add its drawing actions (outline only for this version).
            curve_actions_buffer = []
            start_x, start_y = curve.start_point # Potrace provides a start_point for each curve.
            curve_actions_buffer.append(('moveto', start_x, start_y))
            
            current_pen_x, current_pen_y = start_x, start_y
            # Use the pre-tessellated vertices for drawing this curve's outline.
            for vx, vy in current_curve_vertices_list:
                # Avoid tiny redundant moves if tessellation produces very close points.
                if abs(vx - current_pen_x) > 1e-4 or abs(vy - current_pen_y) > 1e-4 : 
                    curve_actions_buffer.append(('dragto', vx, vy))
                    current_pen_x, current_pen_y = vx, vy
            
            if curve_actions_buffer: # Only add if actions were actually generated.
                raw_actions_original_coords.extend(curve_actions_buffer)
                # Add all points from this valid curve to the bbox calculation.
                all_points_for_bbox_calculation.extend(p[1:] for p in curve_actions_buffer if len(p) > 1)

    except AttributeError as e:
        print(f"AttributeError during Potrace processing: {e}\\n"
              "This might be a linter warning if pypotrace is installed but its C components confuse the linter.\\n"
              "Ensure 'pypotrace' (often installed via pip as 'potrace') is correctly in your Python environment.")
        traceback.print_exc()
        return []
    except Exception as e:
        print(f"An unexpected error occurred during Potrace processing: {e}")
        traceback.print_exc()
        return []

    if not all_points_for_bbox_calculation:
        print("No points for drawing were generated (or all were skipped as borders/empty).")
        return []

    # --- Calculate Bounding Box of all points to be drawn for centering and scaling ---
    min_x_orig = min(p[0] for p in all_points_for_bbox_calculation)
    max_x_orig = max(p[0] for p in all_points_for_bbox_calculation)
    min_y_orig = min(p[1] for p in all_points_for_bbox_calculation)
    max_y_orig = max(p[1] for p in all_points_for_bbox_calculation)

    original_drawing_width = max_x_orig - min_x_orig
    original_drawing_height = max_y_orig - min_y_orig
    
    # Check for negligible size to prevent division by zero or distorted scaling.
    if original_drawing_width <= 1e-3 or original_drawing_height <= 1e-3: # Using a small epsilon.
        print("Warning: Bounding box of drawable elements has zero or negligible size. Cannot draw.")
        return []

    # --- Apply scaling ---
    scaled_drawing_width = original_drawing_width * scale_factor
    scaled_drawing_height = original_drawing_height * scale_factor

    screen_width, screen_height = pyautogui.size()

    # --- Calculate offset for centering the SCALED drawing on the screen ---
    screen_offset_x = (screen_width - scaled_drawing_width) / 2.0
    screen_offset_y = (screen_height - scaled_drawing_height) / 2.0
    
    final_actions = []
    for action_type, x_orig, y_orig in raw_actions_original_coords:
        # 1. Normalize original point relative to its own drawing's bounding box (so 0,0 is top-left of drawing).
        norm_x = x_orig - min_x_orig if original_drawing_width > 1e-3 else 0
        norm_y = y_orig - min_y_orig if original_drawing_height > 1e-3 else 0
        
        # 2. Scale the normalized point.
        scaled_x = norm_x * scale_factor
        scaled_y = norm_y * scale_factor

        # 3. Add the screen offset to position the scaled drawing correctly on the screen.
        final_x = int(round(scaled_x + screen_offset_x))
        final_y = int(round(scaled_y + screen_offset_y))
        
        final_actions.append((action_type, final_x, final_y))
        
    return final_actions

def draw_with_pyautogui(actions, start_delay, action_pause):
    """Executes the generated drawing actions using PyAutoGUI."""
    if not actions:
        print("No actions to draw.")
        return

    print(f"\nDrawing will start in {start_delay} seconds.")
    print("Please switch to your drawing application window NOW!")
    print(f"Drawing scaled by {SCALE_FACTOR}, centered.")
    if ATTEMPT_TO_SKIP_IMAGE_BORDER: 
        print("Border skipping: ON.")
    
    tess_res_info = TESSELATE_RES if TESSELATE_METHOD == 'regular' else 'N/A (adaptive method)'
    print(f"Potrace settings: turdsize={POTRACE_TURDSIZE}, opttolerance={POTRACE_OPTTOLERANCE}, alphamax={POTRACE_ALPHAMAX}")
    print(f"Tessellation: method='{TESSELATE_METHOD}', resolution (if regular)='{tess_res_info}'")
    print("To cancel countdown in terminal: Ctrl+C.")
    print("To cancel drawing once started: quickly move mouse to any screen corner.")
    
    try:
        for i in range(start_delay, 0, -1):
            print(f"{i}... ", end="", flush=True)
            time.sleep(1)
        print("Starting drawing!")
    except KeyboardInterrupt:
        print("\nDrawing cancelled by user during countdown.")
        return

    original_pause_setting = pyautogui.PAUSE # Save current PyAutoGUI pause.
    pyautogui.PAUSE = action_pause          # Set our desired pause for drawing actions.
    pyautogui.FAILSAFE = True               # Enable PyAutoGUI's built-in failsafe.

    try:
        for action_type, x, y in actions:
            if action_type == 'moveto':
                pyautogui.moveTo(x, y)
            elif action_type == 'dragto':
                pyautogui.dragTo(x, y, button='left')
    except pyautogui.FailSafeException:
        print("\nDrawing cancelled by user (mouse moved to screen corner).")
    except Exception as e:
        print(f"\nAn error occurred during PyAutoGUI drawing: {e}")
        traceback.print_exc()
    finally:
        pyautogui.PAUSE = original_pause_setting # Restore original PyAutoGUI pause.
        print("\nDrawing attempt finished or cancelled.")

if __name__ == "__main__":
    print("Image to PyAutoGUI Drawing Script (using pypotrace)")
    print("-" * 50) # Print a separator line.
    
    if len(sys.argv) > 1:
        image_file_path = sys.argv[1]
        print(f"Using image from command line argument: {image_file_path}")
    else:
        image_file_path = input("Enter the path to your image file: ").strip()

    if not os.path.exists(image_file_path):
        print(f"Error: The file '{image_file_path}' does not exist.")
    elif not os.path.isfile(image_file_path):
        print(f"Error: The path '{image_file_path}' is not a file.")
    else:
        generated_actions = image_to_pyautogui_actions(
            image_path=image_file_path,
            threshold=DEFAULT_THRESHOLD_VALUE,
            turd_size=POTRACE_TURDSIZE,
            opt_tolerance=POTRACE_OPTTOLERANCE,
            alphamax=POTRACE_ALPHAMAX,
            scale_factor=SCALE_FACTOR,
            skip_border_setting=ATTEMPT_TO_SKIP_IMAGE_BORDER,
            border_pixel_tol=BORDER_DETECTION_PIXEL_TOLERANCE,
            border_dim_ratio=BORDER_DETECTION_DIMENSION_MATCH_RATIO,
            tesselate_method_config=TESSELATE_METHOD, # Pass configured method
            tesselate_res_config=TESSELATE_RES        # Pass configured resolution
        )

        if generated_actions:
            draw_with_pyautogui(generated_actions, START_DRAW_DELAY, PYAUTOGUI_ACTION_PAUSE)
        else:
            print("Could not generate drawing actions. Review settings, image, or check console for errors.")
