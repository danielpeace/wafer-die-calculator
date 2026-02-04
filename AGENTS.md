# Agent Guidelines for Wafer Die Calculator

## Project Overview
A Python web-based GUI application for calculating semiconductor dies per wafer.
Uses only Python standard library (http.server, json) for a lightweight web interface.

## Build/Test Commands

### Run the application
```bash
python3 wafer_calculator.py
```

Then open http://localhost:5000 in your browser.

### Check for syntax errors
```bash
python3 -m py_compile wafer_calculator.py
```

## Code Style Guidelines

### Python Style
- Follow PEP 8 conventions
- Use 4 spaces for indentation (no tabs)
- Maximum line length: 100 characters
- Use snake_case for variables and functions
- Use PascalCase for class names

### Import Style
- Group imports: standard library first, then third-party, then local
- Use absolute imports only
- Example:
  ```python
  import math
  from http.server import HTTPServer, BaseHTTPRequestHandler
  import json
  ```

### Error Handling
- Use try/except with specific exceptions
- Return errors as JSON with 'error' key for web display
- Validate numeric inputs immediately
- Example:
  ```python
  try:
      value = float(params.get('wafer', ['300'])[0])
      if value <= 0:
          raise ValueError("Must be positive")
  except ValueError as e:
      return json.dumps({'error': str(e)})
  ```

### Naming Conventions
- Functions: `calculate_dies()`, `die_fits()`
- Variables: `wafer_diameter`, `die_count`, `usable_radius`
- Constants: HTML_TEMPLATE (all caps for module-level constants)
- Request handler class: `RequestHandler(BaseHTTPRequestHandler)`

### Web Interface Guidelines
- Use built-in http.server for simplicity (no external dependencies)
- Serve HTML/CSS/JS from embedded template (no external files)
- REST-style endpoints: GET /calculate?param=value
- Return JSON responses for API calls
- Use browser canvas for visualization (HTML5 Canvas API)

### Type Safety
- Document parameter types in docstrings
- Validate numeric inputs immediately
- Convert string inputs to appropriate types at entry point
- Use descriptive variable names to indicate types

### Code Organization
- Pure calculation functions at top (no dependencies)
- HTML template as module-level constant
- RequestHandler class for HTTP routing
- Main function at bottom to start server
- Canvas drawing logic in JavaScript (browser-side)

## Architecture

### Main Components
1. **calculation functions** - Pure Python die counting algorithms
2. **RequestHandler** - HTTP server routing requests
3. **HTML_TEMPLATE** - Embedded HTML/CSS/JS for web UI
4. **Browser canvas** - Real-time wafer visualization

### Calculation Method: Centered Symmetrical Grid Placement

**Algorithm Overview:**
1. Calculate usable wafer radius: (diameter/2) - edge_exclusion
2. Calculate sagitta (flat depth) from flat length: `radius - sqrt(radius^2 - (flat_length/2)^2)`
3. Create a **SYMMETRICAL** centered grid:
   - First die is centered at (0,0) - the wafer center
   - Expand outward in both + and - directions equally
   - Iterate using row/col indices from -N to +N
   - This ensures perfect symmetry about the wafer center
4. For each die position, check if all 4 corners fit within the usable circle
5. Classify as full die (all corners strictly inside) or partial (some on boundary)

**Why Symmetry Matters:**
- Previous brute-force algorithm started at (-radius, -radius) causing asymmetric placement
- Centered algorithm ensures dies are optimally placed around the wafer center
- Better die utilization and more realistic manufacturing simulation

### SEMI Standard Wafer Specifications

The calculator includes predefined SEMI specifications:

| Size  | Diameter | Flat/Notch | Edge Exclusion |
|-------|----------|------------|----------------|
| 300mm | 300mm    | 1mm notch  | 3mm            |
| 200mm | 200mm    | 1mm notch  | 3mm            |
| 150mm | 150mm    | 47.5mm flat| 3mm            |
| 125mm | 125mm    | 42.5mm flat| 3mm            |
| 100mm | 100mm    | 32.5mm flat| 3mm            |
| 76mm  | 76.2mm   | 22.2mm flat| 2.5mm          |
| 50mm  | 50.8mm   | 15.9mm flat| 2.5mm          |

**Sagitta Calculation:**
Formula: `sagitta = radius - sqrt(radius^2 - (flat_length/2)^2)`

This represents the depth of the flat cut into the wafer. For 200mm+ wafers with notches, notch_depth is used directly.

### Key Formulas
- Usable radius = (wafer_diameter / 2) - edge_exclusion
- Die utilization = (dies * die_area) / usable_wafer_area * 100
- Effective die size = die_size + scribe_line
- Sagitta = radius - sqrt(radius^2 - (flat_length/2)^2)

### Web Server
- Single-file application with embedded HTML
- No external dependencies (uses only stdlib)
- Runs on 0.0.0.0:5000 (accessible from any interface)
- Serves static HTML and handles API requests

## Visualization Features

### Zoomable Canvas (800x600)
- **Mouse wheel**: Zoom in/out at cursor position
- **Drag**: Pan/move the view
- **Zoom buttons**: +/- buttons with percentage display
- **Reset View**: Return to default zoom/pan

### GDSII Export
- **Export button**: Downloads layout as .gds file
- **Format**: Standard GDSII binary format
- **Contents**:
  - Layer 0: Wafer edge (64-point circle polygon)
  - Layer 1: Usable edge area
  - Layer 2: All dies as BOUNDARY elements (5-point rectangles)
- **Scaling**: 1 database unit = 1 nanometer

## Testing Approach

### Manual Testing Checklist
- [ ] Valid inputs produce correct die count
- [ ] Invalid inputs show error message in UI
- [ ] Canvas visualization shows symmetrical die placement
- [ ] Flat/notch area properly visualized in red
- [ ] SEMI standards dropdown auto-fills correct values
- [ ] Edge cases (very large/small dies)
- [ ] Standard wafer sizes (300mm, 200mm, 150mm)
- [ ] Canvas zoom in/out works with mouse wheel
- [ ] Canvas pan/drag works
- [ ] Reset View button restores default view
- [ ] GDSII export downloads valid .gds file
- [ ] Browser compatibility (Chrome, Firefox, Safari)

### Edge Cases to Handle
- Die larger than wafer
- Zero or negative dimensions
- Very small dies (grid iteration limit)
- Flat length > wafer diameter
- Missing or malformed URL parameters
- Sagitta calculation with invalid flat length
- GDSII export with zero dies
