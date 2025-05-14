# img-to-drawing

A Python script that I cooked up convert a drawing to mouse input on your device. Easy to use & based on Pillow, Potrace & PyAutoGUI

## Motivation

Initially, this resulted out of me wanting to automatically let a drawing be drawn in the Revolut Card Design screen - yeah, random af. After multiple tries on this, I found out about potrace and finally, I was able to get it done!

[TODO: Add picture of card when it arrived]

## Performance

In /test_assets, there are some images that I experimented and worked with - and then there is test.png, the picture for which the current settings in the script are adjusted for (for having less gaps, more fidelity and "smoothness")

## Parameters & Configuration

The script provides several configuration parameters that can be adjusted to fine-tune the image conversion and drawing process:

### Image Processing & Potrace Settings

- `DEFAULT_THRESHOLD_VALUE` (128): Value (0-255) to distinguish black (to be traced) from white (background).
- `POTRACE_TURDSIZE` (2): Suppresses speckles (small paths) smaller than this size in pixels. Lower values trace more details.
- `POTRACE_OPTTOLERANCE` (0.3): Curve optimization tolerance. Lower values result in more detailed curves.
- `POTRACE_ALPHAMAX` (1.0): Corner detection threshold. Range from 0.0 (polygons only) to 1.3333 (no corners, very smooth).

### Tessellation Settings

- `TESSELATE_METHOD` ('adaptive'): Controls how Potrace curves are broken into straight lines.
  - 'adaptive': Intelligently adds more points where curves are sharper.
  - 'regular': Divides curves into a fixed number of segments.
- `TESSELATE_RES` (15): Resolution for 'regular' tessellation. Higher values create smoother curves but more points.

### Drawing Control

- `PYAUTOGUI_ACTION_PAUSE` (0.005): Pause (seconds) between individual PyAutoGUI actions.
- `START_DRAW_DELAY` (5): Seconds to wait before drawing starts, allowing time to switch windows.
- `SCALE_FACTOR` (1.1): Scale of the final drawing (1.0 = original size, 0.5 = half, 2.0 = double).

### Border Skipping Heuristic

- `ATTEMPT_TO_SKIP_IMAGE_BORDER` (True): If enabled, tries to detect and skip drawing paths that form a full-image border.
- `BORDER_DETECTION_PIXEL_TOLERANCE` (5): Maximum distance (pixels) from image edge for a path to be considered part of a border.
- `BORDER_DETECTION_DIMENSION_MATCH_RATIO` (0.95): Path width/height must be at least this ratio of image width/height to be considered a border.
