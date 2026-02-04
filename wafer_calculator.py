#!/usr/bin/env python3
"""
Wafer Die Calculator - Web-based GUI
Run: python3 wafer_calculator.py
Then open http://localhost:5000 in your browser

Algorithm: Centered grid placement with symmetry
"""

import math
import os
import struct
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.parse
import urllib.request


# SEMI standard wafer specifications
SEMI_STANDARDS = {
    '300mm': {'diameter': 300, 'flat_length': 0, 'notch_depth': 1.0, 'edge_exclusion': 3},
    '200mm': {'diameter': 200, 'flat_length': 0, 'notch_depth': 1.0, 'edge_exclusion': 3},
    '150mm': {'diameter': 150, 'flat_length': 47.5, 'edge_exclusion': 3},
    '125mm': {'diameter': 125, 'flat_length': 42.5, 'edge_exclusion': 3},
    '100mm': {'diameter': 100, 'flat_length': 32.5, 'edge_exclusion': 3},
    '76mm': {'diameter': 76.2, 'flat_length': 22.2, 'edge_exclusion': 2.5},
    '50mm': {'diameter': 50.8, 'flat_length': 15.9, 'edge_exclusion': 2.5},
}

MIN_WAFER_DIAMETER = 20.0
MAX_WAFER_DIAMETER = 450.0
MIN_DIE_SIZE = 0.1
MAX_DIE_SIZE = 200.0
MAX_SCRIBE = 5.0
MAX_EDGE_EXCLUSION = 20.0


def calculate_sagitta(radius, flat_length):
    """Calculate the sagitta (height of flat cut) from flat length.

    The flat cuts into the wafer. The sagitta is how deep the flat cuts.
    Formula: sagitta = radius - sqrt(radius^2 - (flat_length/2)^2)

    Args:
        radius: Wafer radius in mm
        flat_length: Length of the flat in mm

    Returns:
        Sagitta (depth of flat cut) in mm
    """
    if flat_length <= 0 or flat_length > 2 * radius:
        return 0
    half_flat = flat_length / 2
    return radius - math.sqrt(radius**2 - half_flat**2)


def calculate_dies(
    wafer_diameter,
    die_width,
    die_height,
    scribe,
    edge_exclusion,
    flat_length=0.0,
    notch_depth=0.0,
    max_positions=1200,
    include_partial=True,
    align_x=False,
    align_y=False,
):
    """Calculate the number of dies that fit on a wafer with symmetrical placement.

    Algorithm:
    1. Calculate usable radius (wafer radius minus edge exclusion)
    2. Calculate sagitta from flat length (how deep the flat cuts)
    3. Create a SYMMETRICAL centered grid:
       - Start with a die centered at (0,0)
       - Expand outward in all directions
       - This ensures perfect symmetry about the wafer center
    4. For each die position, check if all 4 corners fit within the usable circle
    5. Classify as full die (all corners inside) or partial (some corners inside)

    Args:
        wafer_diameter: Total wafer diameter in mm
        die_width: Width of each die in mm
        die_height: Height of each die in mm
        scribe: Scribe line width (kerf) in mm
        edge_exclusion: Unusable edge width in mm
        flat_length: Length of wafer flat (for older wafers) in mm
        notch_depth: Depth of notch (for 200mm+ wafers) in mm

    Returns:
        Dictionary with die counts, positions, and statistics
    """
    wafer_radius = wafer_diameter / 2
    usable_radius = wafer_radius - edge_exclusion
    effective_width = die_width + scribe
    effective_height = die_height + scribe

    # Calculate flat/notch constraint
    sagitta = calculate_sagitta(wafer_radius, flat_length)
    if notch_depth > 0:
        sagitta = notch_depth

    # The flat/notch is at the bottom, cutting into the wafer
    # Coordinate system: +Y is down in the internal grid
    # y must be <= flat_y to remain above the flat line
    if sagitta > 0:
        flat_y = wafer_radius - sagitta
        usable_flat_y = flat_y
    else:
        flat_y = wafer_radius * 2
        usable_flat_y = usable_radius * 2

    dies = 0
    partial = 0
    die_positions = []
    total_positions = 0
    limit_enabled = max_positions > 0

    # SYMMETRICAL PLACEMENT ALGORITHM
    # Start from center and expand outward in both directions
    # Calculate how many dies fit in each direction from center

    max_cols = int((usable_radius / effective_width)) + 2
    max_rows = int((usable_radius / effective_height)) + 2

    # Iterate over row and column indices
    x_offset = 0.5 if align_x else 0.0
    y_offset = 0.5 if align_y else 0.0

    for row in range(-max_rows, max_rows + 1):
        for col in range(-max_cols, max_cols + 1):
            # Calculate die position - centered on the die
            x = (col + x_offset) * effective_width
            y = (row + y_offset) * effective_height

            # Check if die fits within usable area
            if die_intersects(x, y, effective_width, effective_height, usable_radius, usable_flat_y):
                total_positions += 1
                center_x = x
                center_y = y
                is_full = is_fully_inside(center_x, center_y, effective_width, effective_height, usable_radius, usable_flat_y)

                if is_full:
                    dies += 1
                else:
                    if not include_partial:
                        continue
                    partial += 1

                if not limit_enabled or len(die_positions) < max_positions:
                    die_positions.append({
                        'x': x - effective_width / 2,  # Convert to top-left corner for drawing
                        'y': y - effective_height / 2,
                        'w': effective_width,
                        'h': effective_height,
                        'full': is_full,
                        'center_x': x,
                        'center_y': y
                    })

    # Enforce symmetry about center when a flat/notch is present
    if sagitta > 0:
        center_lookup = {}
        for die in die_positions:
            key = (round(die['center_x'], 6), round(die['center_y'], 6))
            center_lookup[key] = die

        filtered_positions = []
        for die in die_positions:
            key = (round(die['center_x'], 6), round(die['center_y'], 6))
            mirror = (-key[0], -key[1])
            if key == (0.0, 0.0) or mirror in center_lookup:
                filtered_positions.append(die)

        die_positions = filtered_positions
        total_positions = len(die_positions)
        dies = sum(1 for die in die_positions if die['full'])
        partial = total_positions - dies

    # Calculate statistics
    die_area = die_width * die_height
    usable_area = math.pi * usable_radius ** 2
    die_utilization = (dies * die_area) / usable_area * 100 if usable_area > 0 else 0

    # Theoretical maximum (square packing area / wafer area)
    theoretical_max = math.floor(usable_area / (effective_width * effective_height))

    # Limit die positions in API response to prevent browser freezing
    # Full statistics are kept, just limit the array for visualization
    die_positions_limited = limit_enabled and total_positions > max_positions

    return {
        'full_dies': dies,
        'partial_dies': partial,
        'total_sites': dies + partial,
        'die_utilization': round(die_utilization, 1),
        'usable_area': round(usable_area, 1),
        'die_positions': die_positions,
        'die_positions_limited': die_positions_limited,
        'total_die_positions': total_positions,
        'usable_radius': usable_radius,
        'wafer_radius': wafer_radius,
        'wafer_diameter': wafer_diameter,
        'sagitta': round(sagitta, 2),
        'flat_length': flat_length,
        'notch_depth': notch_depth,
        'effective_width': effective_width,
        'effective_height': effective_height
    }


def die_intersects(cx, cy, w, h, radius, flat_y):
    """Check if any part of the die intersects the usable wafer area.

    Args:
        cx, cy: Die center coordinates
        w, h: Die width and height
        radius: Usable wafer radius
        flat_y: Maximum y-coordinate (bottom of usable area due to flat/notch)

    Returns:
        True if any corner is within the usable circle and above the flat
    """
    half_w = w / 2
    half_h = h / 2
    corners = [
        (cx - half_w, cy - half_h),
        (cx + half_w, cy - half_h),
        (cx - half_w, cy + half_h),
        (cx + half_h, cy + half_h)
    ]
    return any(
        math.sqrt(x**2 + y**2) <= radius and y <= flat_y
        for x, y in corners
    )


def is_fully_inside(cx, cy, w, h, radius, flat_y):
    """Check if die is completely within the usable area.

    A die is "full" if all 4 corners are within the usable radius AND
    the die has sufficient clearance from the edge (no corner touches boundary).
    """
    half_w = w / 2
    half_h = h / 2
    corners = [
        (cx - half_w, cy - half_h),
        (cx + half_w, cy - half_h),
        (cx - half_w, cy + half_h),
        (cx + half_h, cy + half_h)
    ]
    # All corners must be strictly inside (not touching the boundary)
    # and above the flat line
    for x, y in corners:
        dist = math.sqrt(x**2 + y**2)
        if dist >= radius or y >= flat_y:
            return False
    return True


def generate_gdsii(data, layer_config):
    """Generate a GDSII binary file from wafer calculation data.

    GDSII format:
    - Records have header: 2-byte length, 1-byte record type, 1-byte data type
    - Common record types: HEADER(0x0002), BGNLIB(0x0102), LIBNAME(0x0206),
      UNITS(0x0305), BGNSTR(0x0502), STRNAME(0x0606), BOUNDARY(0x0800),
      XY(0x1003), ENDEL(0x1100), ENDSTR(0x0700), ENDLIB(0x0400)
    - Data types: 2-byte integer (0x02), 4-byte integer (0x03),
      8-byte real (0x05), ASCII string (0x06)
    - Coordinates are 4-byte signed integers (in database units)
    - Units: typically 1 database unit = 1 nanometer

    Args:
        data: Dictionary with wafer calculation results

    Returns:
        Bytes containing the GDSII file
    """
    # Use 1 database unit = 1 nanometer (0.001 mm)
    # Scale factor: mm to database units
    DB_UNIT_NM = 1000000  # 1 mm = 1,000,000 nm

    def write_record(record_type, data_type, data):
        """Write a GDSII record with proper header."""
        length = 4 + len(data)  # 4 bytes for header
        header = struct.pack('>HBB', length, record_type, data_type)
        return header + data

    def write_string(s):
        """Write an ASCII string padded to even length."""
        if len(s) % 2 == 1:
            s += '\x00'
        return s.encode('ascii')

    def write_2byte_int(n):
        """Write a 2-byte signed integer."""
        return struct.pack('>h', n)

    def write_4byte_int(n):
        """Write a 4-byte signed integer."""
        return struct.pack('>i', n)

    def write_8byte_real(n):
        """Write an 8-byte real (GDSII floating point format)."""
        # GDSII uses a custom floating point format
        # For simplicity, we'll use a fixed user unit = 1 micrometer
        # and database unit = 1 nanometer
        # 8-byte real: exponent in upper bits, mantissa in lower
        # Simplified: encode as IEEE double with conversion
        # Actually, GDSII uses: mantissa * 16^(exponent-64)
        # For user units (1 um = 1000 nm), database units (1 nm)
        # We'll encode 1.0e-9 for database unit in meters
        if n == 0:
            return b'\x00' * 8

        # Find exponent such that mantissa is in [0.0625, 1.0)
        abs_n = abs(n)
        exponent = 0
        while abs_n >= 1.0:
            abs_n /= 16.0
            exponent += 1
        while abs_n < 0.0625:
            abs_n *= 16.0
            exponent -= 1

        # Adjust for GDSII bias of 64
        exp_byte = exponent + 64
        # Mantissa is 7 bytes
        mantissa = int(abs_n * (2 ** 56))

        # Pack: sign bit (1), exponent (7), mantissa (56)
        sign_bit = 0x80 if n < 0 else 0x00
        result = struct.pack('>B', sign_bit | exp_byte)
        result += struct.pack('>Q', mantissa)[1:]  # 7 bytes

        return result

    def write_xy(points):
        """Write XY record with list of (x, y) tuples."""
        data = b''
        for x, y in points:
            data += write_4byte_int(int(x * DB_UNIT_NM))
            data += write_4byte_int(int(y * DB_UNIT_NM))
        return write_record(0x10, 0x03, data)  # XY, 4-byte integer

    def flip_y(points):
        """Flip Y coordinates to match viewer orientation (+Y up)."""
        return [(x, -y) for x, y in points]

    gdsii = b''

    # HEADER record (version 5)
    gdsii += write_record(0x00, 0x02, write_2byte_int(5))

    # BGNLIB - begin library (dates)
    now = [2024, 1, 1, 0, 0, 0]  # Simplified date
    gdsii += write_record(0x01, 0x02, b''.join(write_2byte_int(x) for x in now * 2))

    # LIBNAME
    gdsii += write_record(0x02, 0x06, write_string('WAFER_LIB'))

    # UNITS - user units and database units in meters
    # User unit = 1 micrometer = 1e-6 meters, DB unit = 1 nanometer = 1e-9 meters
    units_data = write_8byte_real(1e-6) + write_8byte_real(1e-9)
    gdsii += write_record(0x03, 0x05, units_data)

    # BGNSTR - begin structure
    gdsii += write_record(0x05, 0x02, b''.join(write_2byte_int(x) for x in now * 2))

    # STRNAME
    gdsii += write_record(0x06, 0x06, write_string('WAFER_DIE_LAYOUT'))

    def add_boundary(layer, points, datatype=0):
        """Add a GDSII BOUNDARY element with layer/datatype and XY points."""
        nonlocal gdsii
        gdsii += write_record(0x08, 0x00, b'')
        gdsii += write_record(0x0D, 0x02, write_2byte_int(layer))
        gdsii += write_record(0x0E, 0x02, write_2byte_int(datatype))
        gdsii += write_xy(points)
        gdsii += write_record(0x11, 0x00, b'')

    # Create wafer edge polygon (circle approximated with 64 points)
    wafer_radius = data['wafer_radius']
    wafer_points = []
    num_segments = 64
    for i in range(num_segments):
        angle = 2 * math.pi * i / num_segments
        x = wafer_radius * math.cos(angle)
        y = wafer_radius * math.sin(angle)
        wafer_points.append((x, y))
    wafer_points.append(wafer_points[0])  # Close the polygon

    add_boundary(layer_config['wafer_layer'], flip_y(wafer_points), layer_config['wafer_datatype'])

    # Create usable edge polygon
    usable_radius = data['usable_radius']
    usable_points = []
    for i in range(num_segments):
        angle = 2 * math.pi * i / num_segments
        x = usable_radius * math.cos(angle)
        y = usable_radius * math.sin(angle)
        usable_points.append((x, y))
    usable_points.append(usable_points[0])  # Close the polygon

    add_boundary(layer_config['usable_layer'], flip_y(usable_points), layer_config['usable_datatype'])

    # Add all dies as BOUNDARY elements
    for die in data['die_positions']:
        # Create 5-point polygon (4 corners + closing point)
        x1 = die['x']
        y1 = die['y']
        x2 = die['x'] + die['w']
        y2 = die['y'] + die['h']

        die_points = [
            (x1, -y1),  # top-left
            (x2, -y1),  # top-right
            (x2, -y2),  # bottom-right
            (x1, -y2),  # bottom-left
            (x1, -y1)   # close
        ]

        add_boundary(layer_config['die_layer'], die_points, layer_config['die_datatype'])

    # ENDSTR - end structure
    gdsii += write_record(0x07, 0x00, b'')

    # ENDLIB - end library
    gdsii += write_record(0x04, 0x00, b'')

    return gdsii


HTML_TEMPLATE = '''<!DOCTYPE html>
<html data-theme="dark">
<head>
    <title>Wafer Die Calculator</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        :root {
            --bg-primary: #0a0a0a;
            --bg-secondary: #111111;
            --bg-tertiary: #1a1a1a;
            --bg-hover: #2a2a2a;
            --text-primary: #e0e0e0;
            --text-secondary: #a0a0a0;
            --text-muted: #6b7280;
            --accent-blue: #a855f7;
            --accent-green: #84cc16;
            --accent-orange: #f97316;
            --accent-red: #ef4444;
            --accent-yellow: #eab308;
            --border-color: #2a2a2a;
            --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3), 0 2px 4px -1px rgba(0, 0, 0, 0.2);
            --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.4), 0 4px 6px -2px rgba(0, 0, 0, 0.3);
            --radius: 8px;
            --radius-sm: 4px;
            --font-mono: 'JetBrains Mono', 'Fira Code', 'Consolas', monospace;
            --font-sans: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            --grid-color: rgba(168, 85, 247, 0.1);
            --grid-color-major: rgba(168, 85, 247, 0.2);
        }

        [data-theme="light"] {
            --bg-primary: #f8fafc;
            --bg-secondary: #ffffff;
            --bg-tertiary: #f1f5f9;
            --bg-hover: #e2e8f0;
            --text-primary: #1e293b;
            --text-secondary: #64748b;
            --text-muted: #94a3b8;
            --accent-blue: #9333ea;
            --accent-green: #65a30d;
            --accent-orange: #ea580c;
            --accent-red: #dc2626;
            --accent-yellow: #ca8a04;
            --border-color: #e2e8f0;
            --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
            --grid-color: rgba(168, 85, 247, 0.08);
            --grid-color-major: rgba(168, 85, 247, 0.15);
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: var(--font-sans);
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        /* Header */
        .header {
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            padding: 0 16px;
            height: 48px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: var(--shadow);
            z-index: 100;
        }

        .header-left {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .header-title {
            font-size: 18px;
            font-weight: 600;
            color: var(--text-primary);
            letter-spacing: -0.5px;
        }

        .header-title span {
            color: var(--accent-blue);
        }

        .header-right {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        /* Toolbar Buttons */
        .toolbar-btn {
            background: transparent;
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            padding: 8px 14px;
            border-radius: var(--radius-sm);
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.15s ease;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .toolbar-btn span {
            font-size: 15px;
        }

        .toolbar-btn:hover {
            background: var(--bg-hover);
            color: var(--text-primary);
            border-color: var(--accent-blue);
        }

        .toolbar-btn:active {
            transform: translateY(1px);
        }

        .toolbar-btn.primary {
            background: var(--accent-blue);
            color: white;
            border-color: var(--accent-blue);
        }

        .toolbar-btn.primary:hover {
            background: #2563eb;
        }

        .toolbar-btn.success {
            background: var(--accent-green);
            color: white;
            border-color: var(--accent-green);
        }

        .toolbar-btn.success:hover {
            background: #16a34a;
        }

        .toolbar-btn.warning {
            background: var(--accent-orange);
            color: white;
            border-color: var(--accent-orange);
        }

        .toolbar-btn.warning:hover {
            background: #ea580c;
        }

        .toolbar-btn.feedback {
            background: transparent;
            border: 1px solid var(--accent-blue);
            color: var(--accent-blue);
        }

        .toolbar-btn.feedback:hover {
            background: rgba(168, 85, 247, 0.12);
            border-color: var(--accent-blue);
            color: var(--text-primary);
        }

        /* Main Layout */
        .main-container {
            display: flex;
            flex: 1;
            overflow: hidden;
        }

        /* Left Sidebar */
        .sidebar {
            width: 380px;
            background: var(--bg-secondary);
            border-right: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            overflow-y: auto;
        }

        .sidebar-section {
            border-bottom: 1px solid var(--border-color);
        }

        .sidebar-header {
            padding: 12px 16px;
            background: var(--bg-tertiary);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-weight: 600;
            font-size: 14px;
            color: var(--text-primary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            transition: background 0.15s ease;
        }

        .sidebar-header:hover {
            background: var(--bg-hover);
        }

        .sidebar-header .chevron {
            transition: transform 0.2s ease;
            font-size: 13px;
        }

        .sidebar-section.collapsed .chevron {
            transform: rotate(-90deg);
        }

        .sidebar-content {
            padding: 12px 12px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .sidebar-section.collapsed .sidebar-content {
            display: none;
        }

        /* Form Elements */
        .input-group {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .sidebar .input-group {
            background: var(--bg-primary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-sm);
            padding: 10px;
        }

        .input-group label {
            font-size: 13px;
            font-weight: 500;
            color: var(--text-secondary);
        }

        .input-group input,
        .input-group select {
            background: transparent;
            border: 1px solid var(--bg-hover);
            color: var(--text-primary);
            padding: 8px 12px;
            border-radius: var(--radius-sm);
            font-size: 13px;
            font-family: var(--font-mono);
            transition: all 0.15s ease;
            width: 100%;
            box-sizing: border-box;
        }

        .input-group input:focus,
        .input-group select:focus {
            outline: none;
            border-color: var(--accent-blue);
            box-shadow: 0 0 0 2px rgba(168, 85, 247, 0.2);
        }

        .input-group .hint {
            font-size: 11px;
            color: var(--text-muted);
        }

        .input-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
        }

        /* Canvas Area */
        .canvas-area {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: var(--bg-primary);
            position: relative;
        }

        .canvas-toolbar {
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            padding: 8px 16px;
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .canvas-toolbar-group {
            display: flex;
            align-items: center;
            gap: 6px;
            padding-right: 12px;
            border-right: 1px solid var(--border-color);
        }

        .icon-btn {
            font-size: 18px;
            padding: 8px 10px;
        }

        .export-filename {
            background: var(--bg-primary);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 6px 10px;
            border-radius: var(--radius-sm);
            font-size: 12px;
            width: 180px;
        }

            .canvas-toolbar-group:last-child {
                border-right: none;
                margin-left: auto;
            }

        .canvas-wrapper {
            flex: 1;
            position: relative;
            overflow: hidden;
            cursor: crosshair;
        }

        .canvas-wrapper:active {
            cursor: grab;
        }

        canvas {
            display: block;
        }

        /* Right Panel */
        .right-panel {
            width: 320px;
            background: var(--bg-secondary);
            border-left: 1px solid var(--border-color);
            display: flex;
            flex-direction: column;
            overflow-y: auto;
        }

        /* Statistics Cards */
        .stat-card {
            background: var(--bg-primary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            padding: 16px;
            margin-bottom: 12px;
        }

        .stat-card-header {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
            margin-bottom: 8px;
        }

        .stat-card-value {
            font-family: var(--font-mono);
            font-size: 24px;
            font-weight: 700;
            color: var(--text-primary);
        }

        .stat-card-value.success {
            color: var(--accent-green);
        }

        .stat-card-value.warning {
            color: var(--accent-yellow);
        }

        .stat-card-value.info {
            color: var(--accent-blue);
        }

        .progress-bar {
            height: 4px;
            background: var(--bg-tertiary);
            border-radius: 2px;
            margin-top: 8px;
            overflow: hidden;
        }

        .progress-bar-fill {
            height: 100%;
            background: var(--accent-green);
            border-radius: 2px;
            transition: width 0.3s ease;
        }

        /* Status Bar */
        .status-bar {
            background: var(--bg-tertiary);
            border-top: 1px solid var(--border-color);
            padding: 0 16px;
            height: 28px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 12px;
            color: var(--text-secondary);
        }

        .status-left {
            display: flex;
            align-items: center;
            gap: 16px;
        }

        .status-right {
            display: flex;
            align-items: center;
            gap: 16px;
        }

        .status-item {
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .status-item .value {
            font-family: var(--font-mono);
            color: var(--text-primary);
            font-weight: 500;
        }

        /* Layer Toggles */
        .layer-toggles {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .layer-toggle {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 12px;
            background: var(--bg-primary);
            border-radius: var(--radius-sm);
            cursor: pointer;
            transition: background 0.15s ease;
        }

        .layer-meta {
            margin-left: auto;
            font-size: 11px;
            color: var(--text-muted);
            border: 1px solid var(--border-color);
            padding: 2px 6px;
            border-radius: 999px;
            background: var(--bg-secondary);
        }

        .layer-actions {
            margin-top: 10px;
            display: flex;
            gap: 8px;
        }

        .layer-toggle:hover {
            background: var(--bg-hover);
        }

        .layer-toggle input[type="checkbox"] {
            width: 16px;
            height: 16px;
            accent-color: var(--accent-blue);
        }

        .layer-color {
            width: 12px;
            height: 12px;
            border-radius: 2px;
        }

        .layer-color.wafer { background: var(--text-secondary); }
        .layer-color.usable { background: var(--accent-blue); }
        .layer-color.die-full { background: var(--accent-green); }
        .layer-color.die-partial { background: var(--accent-yellow); }
        .layer-color.flat { background: var(--accent-red); }

        .layer-label {
            font-size: 12px;
            color: var(--text-secondary);
            flex: 1;
        }

        /* Toast Notifications */
        .toast-container {
            position: fixed;
            bottom: 48px;
            right: 344px;
            z-index: 1000;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .toast {
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-left: 3px solid var(--accent-blue);
            border-radius: var(--radius);
            padding: 12px 16px;
            box-shadow: var(--shadow-lg);
            min-width: 280px;
            animation: slideIn 0.3s ease;
        }

        .toast.success { border-left-color: var(--accent-green); }
        .toast.error { border-left-color: var(--accent-red); }
        .toast.warning { border-left-color: var(--accent-orange); }

        .modal-backdrop {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.55);
            display: none;
            align-items: center;
            justify-content: center;
            z-index: 1000;
        }

        .modal-backdrop.show {
            display: flex;
        }

        .modal {
            width: 520px;
            max-width: 92vw;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            box-shadow: var(--shadow-lg);
            padding: 18px;
        }

        .modal-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 12px;
        }

        .modal-title {
            font-size: 15px;
            font-weight: 600;
            color: var(--text-primary);
        }

        .modal-body {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .modal textarea {
            min-height: 120px;
            resize: vertical;
            background: var(--bg-primary);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 10px 12px;
            border-radius: var(--radius-sm);
            font-size: 13px;
            font-family: var(--font-sans);
        }

        .modal-actions {
            display: flex;
            justify-content: flex-end;
            gap: 8px;
            margin-top: 12px;
        }

        @keyframes slideIn {
            from {
                transform: translateX(100%);
                opacity: 0;
            }
            to {
                transform: translateX(0);
                opacity: 1;
            }
        }

        @keyframes slideOut {
            from {
                transform: translateX(0);
                opacity: 1;
            }
            to {
                transform: translateX(100%);
                opacity: 0;
            }
        }

        .toast.hiding {
            animation: slideOut 0.3s ease forwards;
        }

        .toast-title {
            font-weight: 600;
            font-size: 13px;
            color: var(--text-primary);
            margin-bottom: 4px;
        }

        .toast-message {
            font-size: 12px;
            color: var(--text-secondary);
        }

        /* Error message */
        .error-message {
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid var(--accent-red);
            border-radius: var(--radius);
            padding: 12px 16px;
            color: var(--accent-red);
            font-size: 13px;
            margin: 12px 16px;
            display: none;
        }

        .error-message.show {
            display: block;
            animation: shake 0.5s ease;
        }

        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            25% { transform: translateX(-5px); }
            75% { transform: translateX(5px); }
        }

        /* Export buttons */
        .export-buttons {
            display: flex;
            flex-direction: column;
            gap: 8px;
            padding: 12px 16px;
        }

        /* Section dividers */
        .section-divider {
            height: 1px;
            background: var(--border-color);
            margin: 8px 0;
        }

        /* Tooltip */
        .tooltip {
            position: absolute;
            background: var(--bg-tertiary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-sm);
            padding: 8px 12px;
            font-size: 12px;
            color: var(--text-primary);
            pointer-events: none;
            z-index: 1000;
            box-shadow: var(--shadow);
            display: none;
        }

        .tooltip.show {
            display: block;
        }

        /* Coordinate overlay */
        .coord-overlay {
            position: absolute;
            top: 16px;
            left: 16px;
            background: rgba(26, 26, 46, 0.9);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-sm);
            padding: 8px 12px;
            font-family: var(--font-mono);
            font-size: 12px;
            color: var(--text-secondary);
            pointer-events: none;
            backdrop-filter: blur(4px);
        }

        .coord-overlay [data-theme="light"] & {
            background: rgba(255, 255, 255, 0.9);
        }

        /* Empty state */
        .empty-state {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100%;
            color: var(--text-muted);
            text-align: center;
            padding: 32px;
        }

        .empty-state-icon {
            font-size: 48px;
            margin-bottom: 16px;
            opacity: 0.5;
        }

        .empty-state h3 {
            font-size: 16px;
            font-weight: 600;
            color: var(--text-secondary);
            margin-bottom: 8px;
        }

        .empty-state p {
            font-size: 13px;
        }

        /* Scrollbar styling */
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }

        ::-webkit-scrollbar-track {
            background: var(--bg-primary);
        }

        ::-webkit-scrollbar-thumb {
            background: var(--border-color);
            border-radius: 4px;
        }

        ::-webkit-scrollbar-thumb:hover {
            background: var(--text-muted);
        }
    </style>
</head>
<body>
    <!-- Toast Container -->
    <div class="toast-container" id="toastContainer"></div>

    <!-- Header -->
    <header class="header">
        <div class="header-left">
            <div class="header-title">Wafer<span>Calc</span> Pro</div>
        </div>
        <div class="header-right">
            <button class="toolbar-btn" id="themeToggle" title="Toggle Theme">
                <span id="themeIcon">🌙</span>
            </button>
            <button class="toolbar-btn feedback" id="feedbackBtn" title="Send Feedback">
                <span>💬</span>
                Feedback
            </button>
            <button class="toolbar-btn" id="helpBtn" title="Help">
                <span>?</span>
            </button>
        </div>
    </header>

    <!-- Main Container -->
    <div class="main-container">
        <!-- Left Sidebar -->
        <aside class="sidebar">
            <div class="sidebar-section" id="sectionWafer">
                <div class="sidebar-header" onclick="toggleSection('sectionWafer')">
                    <span>Wafer Parameters</span>
                    <span class="chevron">▼</span>
                </div>
                    <div class="sidebar-content">
                    <div class="input-group">
                        <label for="standard_size">Standard Wafer Size (SEMI)</label>
                        <select id="standard_size" name="standard_size">
                            <option value="300mm">300mm (12") - Notch</option>
                            <option value="200mm">200mm (8") - Notch</option>
                            <option value="150mm">150mm (6") - 47.5mm flat</option>
                            <option value="125mm">125mm (5") - 42.5mm flat</option>
                            <option value="100mm" selected>100mm (4") - 32.5mm flat</option>
                            <option value="76mm">76mm (3") - 22.2mm flat</option>
                            <option value="50mm">50mm (2") - 15.9mm flat</option>
                            <option value="">Custom</option>
                        </select>
                    </div>
                    <div class="input-row">
                        <div class="input-group">
                            <label for="wafer">Diameter (mm)</label>
                            <input type="number" id="wafer" name="wafer" value="100" step="0.1" min="20" max="450">
                        </div>
                        <div class="input-group">
                            <label for="edge">Edge Excl. (mm)</label>
                            <input type="number" id="edge" name="edge" value="3" step="0.1" min="0" max="20">
                        </div>
                    </div>
                    <div class="input-row">
                        <div class="input-group">
                            <label for="flat_length">Flat Length (mm)</label>
                            <input type="number" id="flat_length" name="flat_length" value="32.5" step="0.1" min="0" max="450">
                        </div>
                        <div class="input-group">
                            <label for="notch_depth">Notch Depth (mm)</label>
                            <input type="number" id="notch_depth" name="notch_depth" value="0" step="0.1" min="0" max="5">
                        </div>
                    </div>
                </div>
            </div>

            <div class="sidebar-section" id="sectionDie">
                <div class="sidebar-header" onclick="toggleSection('sectionDie')">
                    <span>Die Parameters</span>
                    <span class="chevron">▼</span>
                </div>
                <div class="sidebar-content">
                    <div class="input-row">
                        <div class="input-group">
                            <label for="die_width">Width (mm)</label>
                            <input type="number" id="die_width" name="die_width" value="10" step="0.1" min="0.1" max="200">
                        </div>
                        <div class="input-group">
                            <label for="die_height">Height (mm)</label>
                            <input type="number" id="die_height" name="die_height" value="10" step="0.1" min="0.1" max="200">
                        </div>
                    </div>
                    <div class="input-group">
                        <label for="scribe">Scribe Line / Kerf (mm)</label>
                            <input type="number" id="scribe" name="scribe" value="0.1" step="0.01" min="0" max="5">
                    </div>
                    <button type="button" class="toolbar-btn primary" id="calculateBtn" style="width: 100%; padding: 12px; margin-top: 8px;">
                        <span>▶</span> Calculate
                    </button>
                    <label class="layer-toggle" style="margin-top: 8px;">
                        <input type="checkbox" id="includePartial" checked>
                        <span class="layer-label">Include partial dies</span>
                    </label>
                    <label class="layer-toggle" style="margin-top: 6px;">
                        <input type="checkbox" id="alignX">
                        <span class="layer-label">Align dicing lanes to X=0</span>
                    </label>
                    <label class="layer-toggle" style="margin-top: 6px;">
                        <input type="checkbox" id="alignY">
                        <span class="layer-label">Align dicing lanes to Y=0</span>
                    </label>
                    <div class="error-message" id="errorMessage"></div>
                </div>
            </div>

            <div class="sidebar-section" id="sectionLayers">
                <div class="sidebar-header" onclick="toggleSection('sectionLayers')">
                    <span>Layer Visibility</span>
                    <span class="chevron">▼</span>
                </div>
                <div class="sidebar-content">
                    <div class="layer-toggles">
                        <label class="layer-toggle">
                            <input type="checkbox" id="layerWafer" checked>
                            <span class="layer-color wafer"></span>
                            <span class="layer-label">Wafer Edge</span>
                            <span class="layer-meta" data-layer-key="wafer">L0 / D0</span>
                        </label>
                        <label class="layer-toggle">
                            <input type="checkbox" id="layerUsable" checked>
                            <span class="layer-color usable"></span>
                            <span class="layer-label">Usable Area</span>
                            <span class="layer-meta" data-layer-key="usable">L1 / D0</span>
                        </label>
                        <label class="layer-toggle">
                            <input type="checkbox" id="layerDieFull" checked>
                            <span class="layer-color die-full"></span>
                            <span class="layer-label">Full Dies</span>
                            <span class="layer-meta" data-layer-key="die">L2 / D0</span>
                        </label>
                        <label class="layer-toggle">
                            <input type="checkbox" id="layerDiePartial" checked>
                            <span class="layer-color die-partial"></span>
                            <span class="layer-label">Partial Dies</span>
                            <span class="layer-meta" data-layer-key="die">L2 / D0</span>
                        </label>
                    </div>
                    <div class="layer-actions">
                        <button class="toolbar-btn" id="importLypBtn" type="button">
                            <span>⬆</span> Import .lyp
                        </button>
                        <input type="file" id="importLypInput" accept=".lyp,.xml" style="display: none;">
                    </div>
                </div>
            </div>

        </aside>

        <!-- Canvas Area -->
        <main class="canvas-area">
            <div class="canvas-toolbar">
                <div class="canvas-toolbar-group">
                    <button class="toolbar-btn icon-btn" id="zoomOutBtn" title="Zoom Out">−</button>
                    <button class="toolbar-btn icon-btn" id="fitScreenBtn" title="Fit to Screen">⊡</button>
                    <button class="toolbar-btn icon-btn" id="zoomInBtn" title="Zoom In">+</button>
                </div>
                <div class="canvas-toolbar-group">
                    <button class="toolbar-btn icon-btn" id="resetViewBtn" title="Reset View">⌂</button>
                </div>
                <div class="canvas-toolbar-group">
                    <input class="export-filename" id="exportFilename" type="text" placeholder="filename (optional)">
                    <button class="toolbar-btn warning" id="exportGdsiiBtn" title="Export GDSII">
                        <span>⬇</span> GDSII
                    </button>
                    <button class="toolbar-btn" id="exportPngBtn" title="Export PNG">
                        <span>🖼</span> PNG
                    </button>
                </div>
            </div>

            <div class="canvas-wrapper" id="canvasWrapper">
                <canvas id="waferCanvas"></canvas>
                <div class="coord-overlay" id="coordOverlay" style="display: none;">
                    X: <span id="mouseX" class="value">0.00</span> mm | 
                    Y: <span id="mouseY" class="value">0.00</span> mm
                </div>
                <div class="empty-state" id="emptyState">
                    <div class="empty-state-icon">◎</div>
                    <h3>No Calculation Yet</h3>
                    <p>Enter parameters and click Calculate to view wafer layout</p>
                </div>
            </div>
        </main>

        <!-- Right Panel -->
        <aside class="right-panel">
            <div class="sidebar-section" id="sectionResults">
                <div class="sidebar-header" onclick="toggleSection('sectionResults')">
                    <span>Results</span>
                    <span class="chevron">▼</span>
                </div>
                <div class="sidebar-content" id="resultsContent">
                    <div class="stat-card" id="statFullDies" style="display: none;">
                        <div class="stat-card-header">Full Dies</div>
                        <div class="stat-card-value success" id="fullDiesValue">0</div>
                    </div>
                    <div class="stat-card" id="statPartialDies" style="display: none;">
                        <div class="stat-card-header">Partial Dies</div>
                        <div class="stat-card-value warning" id="partialDiesValue">0</div>
                    </div>
                    <div class="stat-card" id="statTotalSites" style="display: none;">
                        <div class="stat-card-header">Total Die Sites</div>
                        <div class="stat-card-value info" id="totalSitesValue">0</div>
                    </div>
                    <div class="stat-card" id="statUtilization" style="display: none;">
                        <div class="stat-card-header">Die Utilization</div>
                        <div class="stat-card-value success" id="utilizationValue">0%</div>
                        <div class="progress-bar">
                            <div class="progress-bar-fill" id="utilizationBar" style="width: 0%"></div>
                        </div>
                    </div>
                    <div class="stat-card" id="statArea" style="display: none;">
                        <div class="stat-card-header">Usable Area</div>
                        <div class="stat-card-value" id="usableAreaValue">0 mm²</div>
                    </div>
                    <div class="stat-card" id="statSagitta" style="display: none;">
                        <div class="stat-card-header">Flat/Notch Depth (Sagitta)</div>
                        <div class="stat-card-value" id="sagittaValue">0 mm</div>
                    </div>
                    <div id="noResults" style="text-align: center; color: var(--text-muted); padding: 32px 16px; font-size: 13px;">
                        No results yet. Click Calculate to see statistics.
                    </div>
                </div>
            </div>

            <div class="sidebar-section" id="sectionInfo">
                <div class="sidebar-header" onclick="toggleSection('sectionInfo')">
                    <span>Algorithm Info</span>
                    <span class="chevron">▼</span>
                </div>
                <div class="sidebar-content" style="font-size: 12px; color: var(--text-secondary); line-height: 1.6;">
                    <p style="margin-bottom: 8px;"><strong style="color: var(--text-primary);">Centered Symmetrical Grid</strong></p>
                    <p style="margin-bottom: 12px;">Uses centered grid placement with perfect symmetry about the wafer center for optimal die utilization.</p>
                    <p style="font-size: 11px; color: var(--text-muted);">
                        <strong style="color: var(--text-secondary);">Sagitta:</strong> sagitta = radius - √(radius² - (flat_length/2)²)
                    </p>
                </div>
            </div>
        </aside>
    </div>

    <!-- Status Bar -->
    <footer class="status-bar">
        <div class="status-left">
            <div class="status-item">
                <span>Zoom:</span>
                <span class="value" id="zoomLevel">100%</span>
            </div>
            <div class="status-item">
                <span>Dies:</span>
                <span class="value" id="statusDieCount">-</span>
            </div>
        </div>
        <div class="status-right">
            <div class="status-item" id="mouseCoords" style="display: none;">
                <span>Cursor:</span>
                <span class="value" id="statusMouseCoords">0.00, 0.00</span>
            </div>
            <div class="status-item">
                <span id="statusMessage">Ready</span>
            </div>
        </div>
    </footer>

    <!-- Feedback Modal -->
    <div class="modal-backdrop" id="feedbackModal">
        <div class="modal" role="dialog" aria-modal="true" aria-labelledby="feedbackTitle">
            <div class="modal-header">
                <div class="modal-title" id="feedbackTitle">Submit Feedback</div>
                <button class="toolbar-btn" id="feedbackClose" title="Close">✕</button>
            </div>
            <div class="modal-body">
                <div class="input-group">
                    <label for="feedbackType">Type</label>
                    <select id="feedbackType">
                        <option value="issue">Bug / Error</option>
                        <option value="improvement">Design Improvement</option>
                        <option value="other">Other</option>
                    </select>
                </div>
                <div class="input-group">
                    <label for="feedbackMessage">Message</label>
                    <textarea id="feedbackMessage" placeholder="Describe the issue or improvement..."></textarea>
                </div>
                <div class="input-group" style="display: none;">
                    <label for="feedbackWebsite">Website</label>
                    <input type="text" id="feedbackWebsite" autocomplete="off">
                </div>
                <div class="input-group">
                    <label for="feedbackEmail">Email (optional)</label>
                    <input type="email" id="feedbackEmail" placeholder="you@example.com">
                </div>
                <div class="modal-actions">
                    <button class="toolbar-btn" id="feedbackCancel">Cancel</button>
                    <button class="toolbar-btn primary" id="feedbackSubmit">Send Feedback</button>
                </div>
            </div>
        </div>
    </div>

    <!-- Layer Config Modal -->
    <div class="modal-backdrop" id="layerModal">
        <div class="modal" role="dialog" aria-modal="true" aria-labelledby="layerTitle">
            <div class="modal-header">
                <div class="modal-title" id="layerTitle">Edit GDS Layer</div>
                <button class="toolbar-btn" id="layerClose" title="Close">✕</button>
            </div>
            <div class="modal-body">
                <div class="input-group">
                    <label for="layerNumberInput">Layer Number</label>
                    <input type="number" id="layerNumberInput" min="0" step="1">
                </div>
                <div class="input-group">
                    <label for="datatypeNumberInput">Datatype</label>
                    <input type="number" id="datatypeNumberInput" min="0" step="1">
                </div>
                <div class="modal-actions">
                    <button class="toolbar-btn" id="layerCancel">Cancel</button>
                    <button class="toolbar-btn primary" id="layerSave">Save</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        // SEMI standard specifications
        const semiStandards = {
            '300mm': {diameter: 300, flat_length: 0, notch_depth: 1.0, edge_exclusion: 3},
            '200mm': {diameter: 200, flat_length: 0, notch_depth: 1.0, edge_exclusion: 3},
            '150mm': {diameter: 150, flat_length: 47.5, notch_depth: 0, edge_exclusion: 3},
            '125mm': {diameter: 125, flat_length: 42.5, notch_depth: 0, edge_exclusion: 3},
            '100mm': {diameter: 100, flat_length: 32.5, notch_depth: 0, edge_exclusion: 3},
            '76mm': {diameter: 76.2, flat_length: 22.2, notch_depth: 0, edge_exclusion: 2.5},
            '50mm': {diameter: 50.8, flat_length: 15.9, notch_depth: 0, edge_exclusion: 2.5}
        };

        // Canvas state variables
        let zoomScale = 1.0;
        let offsetX = 0;
        let offsetY = 0;
        let isDragging = false;
        let lastMouseX = 0;
        let lastMouseY = 0;
        let currentData = null;
        let baseScale = 1.0;

        // Layer visibility
        let layerVisibility = {
            wafer: true,
            usable: true,
            dieFull: true,
            diePartial: true,
            flat: true
        };

        const layerConfig = {
            wafer: { layer: 0, datatype: 0, color: '#6b7280' },
            usable: { layer: 1, datatype: 0, color: '#a855f7' },
            die: { layer: 2, datatype: 0, color: '#84cc16' },
            diePartial: { color: '#eab308' },
        };

        // Theme toggle
        const themeToggle = document.getElementById('themeToggle');
        const themeIcon = document.getElementById('themeIcon');
        
        themeToggle.addEventListener('click', () => {
            const html = document.documentElement;
            const currentTheme = html.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            html.setAttribute('data-theme', newTheme);
            themeIcon.textContent = newTheme === 'dark' ? '🌙' : '☀️';
            if (currentData) drawWafer(currentData);
        });

        // Feedback modal
        const feedbackModal = document.getElementById('feedbackModal');
        document.getElementById('feedbackBtn').addEventListener('click', () => {
            feedbackModal.classList.add('show');
        });
        document.getElementById('feedbackClose').addEventListener('click', () => {
            feedbackModal.classList.remove('show');
        });
        document.getElementById('feedbackCancel').addEventListener('click', () => {
            feedbackModal.classList.remove('show');
        });
        feedbackModal.addEventListener('click', (e) => {
            if (e.target === feedbackModal) {
                feedbackModal.classList.remove('show');
            }
        });
        document.getElementById('feedbackSubmit').addEventListener('click', async () => {
            const feedbackType = document.getElementById('feedbackType').value;
            const feedbackMessage = document.getElementById('feedbackMessage').value.trim();
            const feedbackEmail = document.getElementById('feedbackEmail').value.trim();
            const feedbackWebsite = document.getElementById('feedbackWebsite').value.trim();

            if (!feedbackMessage) {
                showToast('Feedback Required', 'Please enter a message.', 'warning');
                return;
            }

            try {
                const payload = {
                    type: feedbackType,
                    message: feedbackMessage,
                    email: feedbackEmail,
                    website: feedbackWebsite,
                    timestamp: new Date().toISOString(),
                    context: {
                        wafer: document.getElementById('wafer').value,
                        die_width: document.getElementById('die_width').value,
                        die_height: document.getElementById('die_height').value,
                        scribe: document.getElementById('scribe').value,
                        edge: document.getElementById('edge').value,
                        flat_length: document.getElementById('flat_length').value,
                        notch_depth: document.getElementById('notch_depth').value,
                    }
                };

                const response = await fetch('/feedback', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });

                const data = await response.json();
                if (data.error) {
                    throw new Error(data.error);
                }

                document.getElementById('feedbackMessage').value = '';
                document.getElementById('feedbackEmail').value = '';
                feedbackModal.classList.remove('show');
                showToast('Thanks!', 'Your feedback was sent.', 'success');
            } catch (err) {
                showToast('Feedback Failed', err.message, 'error');
            }
        });

        // Layer config modal
        const layerModal = document.getElementById('layerModal');
        let activeLayerKey = 'wafer';

        function updateLayerMeta() {
            document.querySelectorAll('.layer-meta').forEach((meta) => {
                const key = meta.dataset.layerKey;
                const config = layerConfig[key];
                meta.textContent = `${config.layer}/${config.datatype}`;
            });

            document.querySelectorAll('.layer-color.wafer').forEach((el) => {
                el.style.background = layerConfig.wafer.color;
            });
            document.querySelectorAll('.layer-color.usable').forEach((el) => {
                el.style.background = layerConfig.usable.color;
            });
            document.querySelectorAll('.layer-color.die-full').forEach((el) => {
                el.style.background = layerConfig.die.color;
            });
        }

        function openLayerModal(layerKey) {
            activeLayerKey = layerKey;
            document.getElementById('layerNumberInput').value = layerConfig[layerKey].layer;
            document.getElementById('datatypeNumberInput').value = layerConfig[layerKey].datatype;
            layerModal.classList.add('show');
        }

        document.querySelectorAll('.layer-meta').forEach((meta) => {
            meta.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                openLayerModal(meta.dataset.layerKey);
            });
            meta.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                openLayerModal(meta.dataset.layerKey);
            });
        });

        document.getElementById('layerClose').addEventListener('click', () => {
            layerModal.classList.remove('show');
        });
        document.getElementById('layerCancel').addEventListener('click', () => {
            layerModal.classList.remove('show');
        });
        layerModal.addEventListener('click', (e) => {
            if (e.target === layerModal) {
                layerModal.classList.remove('show');
            }
        });

        document.getElementById('layerSave').addEventListener('click', () => {
            const layerValue = parseInt(document.getElementById('layerNumberInput').value || '0', 10);
            const datatypeValue = parseInt(document.getElementById('datatypeNumberInput').value || '0', 10);
            layerConfig[activeLayerKey].layer = Math.max(0, layerValue);
            layerConfig[activeLayerKey].datatype = Math.max(0, datatypeValue);
            updateLayerMeta();
            layerModal.classList.remove('show');
            showToast('Layer Updated', `Set ${activeLayerKey} to ${layerConfig[activeLayerKey].layer}/${layerConfig[activeLayerKey].datatype}`, 'success');
        });

        // Import KLayout .lyp
        const importLypBtn = document.getElementById('importLypBtn');
        const importLypInput = document.getElementById('importLypInput');

        importLypBtn.addEventListener('click', () => {
            importLypInput.click();
        });

        importLypInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (!file) return;

            const reader = new FileReader();
            reader.onload = () => {
                try {
                    const xml = reader.result;
                    const parser = new DOMParser();
                    const doc = parser.parseFromString(xml, 'text/xml');
                    const props = Array.from(doc.getElementsByTagName('properties'));

                    const layers = props.map((node) => {
                        const name = node.getElementsByTagName('name')[0]?.textContent?.toLowerCase() || '';
                        const layer = parseInt(node.getElementsByTagName('layer')[0]?.textContent || '0', 10);
                        const datatype = parseInt(node.getElementsByTagName('datatype')[0]?.textContent || '0', 10);
                        const colorText = node.getElementsByTagName('color')[0]?.textContent || '';
                        const color = colorText.startsWith('#') ? colorText : `#${colorText}`;

                        return { name, layer, datatype, color };
                    });

                    const findLayer = (key, fallbackIndex) => {
                        const match = layers.find((l) => l.name.includes(key));
                        return match || layers[fallbackIndex] || null;
                    };

                    const waferLayer = findLayer('wafer', 0);
                    const usableLayer = findLayer('usable', 1) || findLayer('edge', 1);
                    const dieLayer = findLayer('die', 2) || findLayer('chip', 2);

                    if (waferLayer) {
                        layerConfig.wafer.layer = waferLayer.layer;
                        layerConfig.wafer.datatype = waferLayer.datatype;
                        if (waferLayer.color) layerConfig.wafer.color = waferLayer.color;
                    }
                    if (usableLayer) {
                        layerConfig.usable.layer = usableLayer.layer;
                        layerConfig.usable.datatype = usableLayer.datatype;
                        if (usableLayer.color) layerConfig.usable.color = usableLayer.color;
                    }
                    if (dieLayer) {
                        layerConfig.die.layer = dieLayer.layer;
                        layerConfig.die.datatype = dieLayer.datatype;
                        if (dieLayer.color) layerConfig.die.color = dieLayer.color;
                    }

                    updateLayerMeta();
                    showToast('Layer Import', 'Loaded layer numbers and colors from .lyp', 'success');
                } catch (err) {
                    showToast('Layer Import Failed', err.message, 'error');
                } finally {
                    importLypInput.value = '';
                }
            };
            reader.readAsText(file);
        });

        function applyStandardSize(value, showToastMessage = false) {
            const std = semiStandards[value];
            if (std) {
                document.getElementById('wafer').value = std.diameter;
                document.getElementById('flat_length').value = std.flat_length;
                document.getElementById('notch_depth').value = std.notch_depth;
                document.getElementById('edge').value = std.edge_exclusion;
                if (showToastMessage) {
                    showToast('SEMI Standard Applied', `${value} parameters loaded`, 'success');
                }
            }
            drawWaferOutline();
        }

        // Auto-fill when standard size is selected
        document.getElementById('standard_size').addEventListener('change', function() {
            applyStandardSize(this.value, true);
        });

        // Auto-draw wafer outline when wafer parameters change
        const waferParams = ['wafer', 'edge', 'flat_length', 'notch_depth'];
        waferParams.forEach(id => {
            document.getElementById(id).addEventListener('input', debounce(drawWaferOutline, 100));
        });

        function debounce(func, wait) {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        }

        function drawWaferOutline() {
            const canvas = document.getElementById('waferCanvas');
            const ctx = canvas.getContext('2d');
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            const emptyState = document.getElementById('emptyState');

            // Get wafer parameters
            const waferDiameter = parseFloat(document.getElementById('wafer').value) || 100;
            const edgeExclusion = parseFloat(document.getElementById('edge').value) || 3;
            const flatLength = parseFloat(document.getElementById('flat_length').value) || 0;
            const notchDepth = parseFloat(document.getElementById('notch_depth').value) || 0;

            const waferRadius = waferDiameter / 2;
            const usableRadius = waferRadius - edgeExclusion;

            // Calculate sagitta
            let sagitta = 0;
            if (flatLength > 0 && flatLength <= 2 * waferRadius) {
                const halfFlat = flatLength / 2;
                sagitta = waferRadius - Math.sqrt(waferRadius**2 - halfFlat**2);
            } else if (notchDepth > 0) {
                sagitta = notchDepth;
            }

            // Hide empty state and show coordinate overlay
            emptyState.style.display = 'none';
            document.getElementById('coordOverlay').style.display = 'block';

            // Clear canvas
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            const centerX = canvas.width / 2;
            const centerY = canvas.height / 2;
            baseScale = 200 / waferRadius;
            const scale = baseScale * zoomScale;
            // Draw grid background
            drawGrid(ctx, canvas.width, canvas.height, centerX, centerY, scale);

            // Draw wafer outline
            ctx.beginPath();
            ctx.arc(centerX + offsetX, centerY + offsetY, waferRadius * scale, 0, 2 * Math.PI);
            ctx.fillStyle = isDark ? 'rgba(100, 100, 100, 0.2)' : 'rgba(200, 200, 200, 0.3)';
            ctx.fill();
            ctx.strokeStyle = isDark ? '#666' : '#999';
            ctx.lineWidth = 2;
            ctx.stroke();

            // Draw usable area
            ctx.beginPath();
            ctx.arc(centerX + offsetX, centerY + offsetY, usableRadius * scale, 0, 2 * Math.PI);
            ctx.strokeStyle = layerConfig.usable.color;
            ctx.setLineDash([5, 5]);
            ctx.lineWidth = 2;
            ctx.stroke();
            ctx.setLineDash([]);

            // Draw flat/notch
            if (sagitta > 0) {
                if (flatLength > 0) {
                    const halfFlat = flatLength / 2;
                    const flatY_canvas = waferRadius - sagitta;
                    const intersectX = Math.sqrt(2 * waferRadius * sagitta - sagitta * sagitta);

                    // Draw the flat chord
                    ctx.beginPath();
                    ctx.moveTo(centerX + offsetX - intersectX * scale, centerY + offsetY + flatY_canvas * scale);
                    ctx.lineTo(centerX + offsetX + intersectX * scale, centerY + offsetY + flatY_canvas * scale);
                    ctx.strokeStyle = isDark ? '#666' : '#999';
                    ctx.lineWidth = 3;
                    ctx.stroke();

                    const angleToLeft = Math.atan2(flatY_canvas, -intersectX);
                    const angleToRight = Math.atan2(flatY_canvas, intersectX);

                    ctx.beginPath();
                    ctx.arc(centerX + offsetX, centerY + offsetY, waferRadius * scale, angleToLeft, angleToRight);
                    ctx.strokeStyle = isDark ? '#666' : '#999';
                    ctx.lineWidth = 2;
                    ctx.setLineDash([3, 3]);
                    ctx.stroke();
                    ctx.setLineDash([]);

                    ctx.save();
                    ctx.beginPath();
                    ctx.moveTo(centerX + offsetX - intersectX * scale, centerY + offsetY + flatY_canvas * scale);
                    ctx.lineTo(centerX + offsetX + intersectX * scale, centerY + offsetY + flatY_canvas * scale);
                    ctx.arc(centerX + offsetX, centerY + offsetY, waferRadius * scale, angleToRight, angleToLeft, true);
                    ctx.closePath();
                    ctx.fillStyle = isDark ? 'rgba(100, 100, 100, 0.2)' : 'rgba(200, 200, 200, 0.3)';
                    ctx.fill();
                    ctx.restore();
                } else if (notchDepth > 0) {
                    const flatY = waferRadius - sagitta;
                    const notchWidth = 2;

                    ctx.beginPath();
                    ctx.moveTo(centerX + offsetX - notchWidth * scale, centerY + offsetY + (flatY + sagitta) * scale);
                    ctx.lineTo(centerX + offsetX, centerY + offsetY + flatY * scale);
                    ctx.lineTo(centerX + offsetX + notchWidth * scale, centerY + offsetY + (flatY + sagitta) * scale);
                    ctx.strokeStyle = isDark ? '#666' : '#999';
                    ctx.lineWidth = 2;
                    ctx.stroke();
                }
            }

            // Draw center crosshair
            ctx.beginPath();
            ctx.moveTo(centerX + offsetX - 15, centerY + offsetY);
            ctx.lineTo(centerX + offsetX + 15, centerY + offsetY);
            ctx.moveTo(centerX + offsetX, centerY + offsetY - 15);
            ctx.lineTo(centerX + offsetX, centerY + offsetY + 15);
            ctx.strokeStyle = isDark ? 'rgba(168, 85, 247, 0.8)' : 'rgba(168, 85, 247, 0.6)';
            ctx.lineWidth = 1;
            ctx.stroke();
        }

        // Calculate button
        document.getElementById('calculateBtn').addEventListener('click', calculate);

        async function calculate() {
            const errorMessage = document.getElementById('errorMessage');
            const emptyState = document.getElementById('emptyState');
            const coordOverlay = document.getElementById('coordOverlay');

            errorMessage.classList.remove('show');

            const params = new URLSearchParams({
                wafer: document.getElementById('wafer').value,
                die_width: document.getElementById('die_width').value,
                die_height: document.getElementById('die_height').value,
                scribe: document.getElementById('scribe').value,
                edge: document.getElementById('edge').value,
                flat_length: document.getElementById('flat_length').value,
                notch_depth: document.getElementById('notch_depth').value,
                include_partial: document.getElementById('includePartial').checked ? '1' : '0',
                align_x: document.getElementById('alignX').checked ? '1' : '0',
                align_y: document.getElementById('alignY').checked ? '1' : '0'
            });

            try {
                const response = await fetch('/calculate?' + params.toString());
                const data = await response.json();

                if (data.error) {
                    errorMessage.textContent = data.error;
                    errorMessage.classList.add('show');
                    showToast('Calculation Failed', data.error, 'error');
                    return;
                }

                // Update results
                updateResults(data);

                // Show canvas, hide empty state
                emptyState.style.display = 'none';
                coordOverlay.style.display = 'block';

                // Update scale, fit to screen, and draw
                currentData = data;
                baseScale = 200 / data.wafer_radius;
                fitToScreen();
                drawWafer(data);

                showToast('Calculation Complete', `${data.full_dies} full dies, ${data.partial_dies} partial`, 'success');

            } catch (err) {
                errorMessage.textContent = 'Error: ' + err.message;
                errorMessage.classList.add('show');
                showToast('Error', err.message, 'error');
            }
        }

        function updateResults(data) {
            document.getElementById('noResults').style.display = 'none';
            
            document.getElementById('statFullDies').style.display = 'block';
            document.getElementById('fullDiesValue').textContent = data.full_dies;
            
            if (document.getElementById('includePartial').checked) {
                document.getElementById('statPartialDies').style.display = 'block';
                document.getElementById('partialDiesValue').textContent = data.partial_dies;
            } else {
                document.getElementById('statPartialDies').style.display = 'none';
            }
            
            document.getElementById('statTotalSites').style.display = 'block';
            document.getElementById('totalSitesValue').textContent = data.total_sites;
            
            document.getElementById('statUtilization').style.display = 'block';
            document.getElementById('utilizationValue').textContent = data.die_utilization + '%';
            document.getElementById('utilizationBar').style.width = data.die_utilization + '%';
            
            document.getElementById('statArea').style.display = 'block';
            document.getElementById('usableAreaValue').textContent = data.usable_area + ' mm²';
            
            document.getElementById('statusDieCount').textContent = data.full_dies;
            const statusMessage = document.getElementById('statusMessage');
            if (data.die_positions_limited) {
                statusMessage.textContent = `Showing ${data.die_positions.length} of ${data.total_die_positions} dies`;
                showToast('Visualization Limited', `Rendering ${data.die_positions.length} of ${data.total_die_positions} dies for performance.`, 'warning');
            } else {
                statusMessage.textContent = 'Ready';
            }

            if (data.sagitta > 0.001) {
                document.getElementById('statSagitta').style.display = 'block';
                document.getElementById('sagittaValue').textContent = data.sagitta + ' mm';
            } else {
                document.getElementById('statSagitta').style.display = 'none';
            }
        }

        function resetView() {
            zoomScale = 1.0;
            offsetX = 0;
            offsetY = 0;
            updateZoomDisplay();
            if (currentData) {
                drawWafer(currentData);
            }
        }

        function fitToScreen() {
            if (!currentData) return;
            const canvas = document.getElementById('waferCanvas');
            const wrapper = document.getElementById('canvasWrapper');
            const waferRadius = currentData.wafer_radius;
            const padding = 40;
            
            const availableWidth = wrapper.clientWidth - padding * 2;
            const availableHeight = wrapper.clientHeight - padding * 2;
            const scaleX = availableWidth / (waferRadius * 2);
            const scaleY = availableHeight / (waferRadius * 2);
            
            zoomScale = Math.min(scaleX, scaleY) / baseScale;
            offsetX = 0;
            offsetY = 0;
            
            updateZoomDisplay();
            drawWafer(currentData);
        }

        function updateZoomDisplay() {
            document.getElementById('zoomLevel').textContent = Math.round(zoomScale * 100) + '%';
        }

        const MIN_ZOOM = 0.5;  // Minimum 50% zoom
        const MAX_ZOOM = 10.0;  // Max 10x zoom

        function zoomIn() {
            zoomScale = Math.min(zoomScale * 1.2, MAX_ZOOM);
            updateZoomDisplay();
            if (currentData) {
                drawWafer(currentData);
            }
        }

        function zoomOut() {
            zoomScale = Math.max(zoomScale / 1.2, MIN_ZOOM);
            updateZoomDisplay();
            if (currentData) {
                drawWafer(currentData);
            }
        }

        // Layer toggles
        document.getElementById('layerWafer').addEventListener('change', (e) => {
            layerVisibility.wafer = e.target.checked;
            if (currentData) drawWafer(currentData);
        });
        document.getElementById('layerUsable').addEventListener('change', (e) => {
            layerVisibility.usable = e.target.checked;
            if (currentData) drawWafer(currentData);
        });
        document.getElementById('layerDieFull').addEventListener('change', (e) => {
                layerVisibility.dieFull = e.target.checked;
                if (currentData) drawWafer(currentData);
            });
        document.getElementById('layerDiePartial').addEventListener('change', (e) => {
            layerVisibility.diePartial = e.target.checked;
            if (currentData) drawWafer(currentData);
        });

        document.getElementById('includePartial').addEventListener('change', (e) => {
            layerVisibility.diePartial = e.target.checked;
            document.getElementById('layerDiePartial').checked = e.target.checked;
            document.getElementById('layerDiePartial').disabled = !e.target.checked;
            if (currentData) drawWafer(currentData);
        });
        // Canvas event listeners
        const canvas = document.getElementById('waferCanvas');
        const wrapper = document.getElementById('canvasWrapper');

        function resizeCanvas() {
            canvas.width = wrapper.clientWidth;
            canvas.height = wrapper.clientHeight;
            if (currentData) {
                drawWafer(currentData);
            }
        }

        window.addEventListener('resize', resizeCanvas);
        resizeCanvas();

        canvas.addEventListener('mousedown', (e) => {
            isDragging = true;
            lastMouseX = e.clientX;
            lastMouseY = e.clientY;
            canvas.style.cursor = 'grabbing';
        });

        canvas.addEventListener('mousemove', (e) => {
            const rect = canvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            // Update coordinate display
            const centerX = canvas.width / 2;
            const centerY = canvas.height / 2;
            const scale = baseScale * zoomScale;
            const toCanvasX = (x) => centerX + offsetX + (x * scale);
            const toCanvasY = (y) => centerY + offsetY - (y * scale);
            const mmX = ((x - centerX - offsetX) / scale).toFixed(2);
            const mmY = ((centerY + offsetY - y) / scale).toFixed(2);
            
            document.getElementById('mouseX').textContent = mmX;
            document.getElementById('mouseY').textContent = mmY;
            document.getElementById('statusMouseCoords').textContent = `${mmX}, ${mmY}`;
            document.getElementById('mouseCoords').style.display = 'flex';

            if (isDragging && currentData) {
                const deltaX = e.clientX - lastMouseX;
                const deltaY = e.clientY - lastMouseY;
                offsetX += deltaX;
                offsetY += deltaY;
                lastMouseX = e.clientX;
                lastMouseY = e.clientY;
                drawWafer(currentData);
            }
        });

        canvas.addEventListener('mouseup', () => {
            isDragging = false;
            canvas.style.cursor = 'crosshair';
        });

        canvas.addEventListener('mouseleave', () => {
            isDragging = false;
            canvas.style.cursor = 'crosshair';
        });

        canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            if (e.deltaY < 0) {
                zoomIn();
            } else {
                zoomOut();
            }
        }, { passive: false });

        // Toolbar button event listeners
        document.getElementById('zoomInBtn').addEventListener('click', zoomIn);
        document.getElementById('zoomOutBtn').addEventListener('click', zoomOut);
        document.getElementById('resetViewBtn').addEventListener('click', resetView);
        document.getElementById('fitScreenBtn').addEventListener('click', fitToScreen);
        document.getElementById('exportGdsiiBtn').addEventListener('click', exportGdsii);
        document.getElementById('exportPngBtn').addEventListener('click', exportPng);

        function transformX(x, canvasCenter, scale, zoom, offset) {
            return canvasCenter + (x * scale * zoom) + offset;
        }

        function transformY(y, canvasCenter, scale, zoom, offset) {
            return canvasCenter + (y * scale * zoom) + offset;
        }

        function drawGrid(ctx, width, height, centerX, centerY, scale) {
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            const gridColor = isDark ? 'rgba(168, 85, 247, 0.08)' : 'rgba(168, 85, 247, 0.05)';
            const majorGridColor = isDark ? 'rgba(168, 85, 247, 0.15)' : 'rgba(168, 85, 247, 0.1)';
            
            // Calculate grid spacing based on zoom level - use adaptive spacing
            let baseGridSize = 10; // mm
            if (scale < 0.5) baseGridSize = 50;
            else if (scale < 1) baseGridSize = 20;
            else if (scale > 5) baseGridSize = 5;
            
            const gridSize = baseGridSize * scale;
            
            ctx.save();
            
            // Draw major grid lines only - skip minor dots for performance
            ctx.strokeStyle = majorGridColor;
            ctx.lineWidth = 1;
            
            // Batch line drawing for better performance
            ctx.beginPath();
            
            // Vertical lines
            for (let x = centerX % gridSize; x < width; x += gridSize) {
                ctx.moveTo(x, 0);
                ctx.lineTo(x, height);
            }
            for (let x = centerX % gridSize; x > 0; x -= gridSize) {
                ctx.moveTo(x, 0);
                ctx.lineTo(x, height);
            }
            
            // Horizontal lines
            for (let y = centerY % gridSize; y < height; y += gridSize) {
                ctx.moveTo(0, y);
                ctx.lineTo(width, y);
            }
            for (let y = centerY % gridSize; y > 0; y -= gridSize) {
                ctx.moveTo(0, y);
                ctx.lineTo(width, y);
            }
            
            ctx.stroke();
            
            // Draw axes
            ctx.strokeStyle = isDark ? 'rgba(168, 85, 247, 0.4)' : 'rgba(168, 85, 247, 0.3)';
            ctx.lineWidth = 2;
            
            // X axis
            ctx.beginPath();
            ctx.moveTo(0, centerY + offsetY);
            ctx.lineTo(width, centerY + offsetY);
            ctx.stroke();
            
            // Y axis
            ctx.beginPath();
            ctx.moveTo(centerX + offsetX, 0);
            ctx.lineTo(centerX + offsetX, height);
            ctx.stroke();

            // Axis labels
            ctx.fillStyle = isDark ? 'rgba(168, 85, 247, 0.8)' : 'rgba(168, 85, 247, 0.7)';
            ctx.font = '12px var(--font-mono)';
            ctx.textAlign = 'left';
            ctx.textBaseline = 'middle';
            ctx.fillText('+X', width - 28, centerY + offsetY - 10);
            ctx.fillText('-X', 8, centerY + offsetY - 10);
            ctx.textAlign = 'center';
            ctx.textBaseline = 'top';
            ctx.fillText('+Y', centerX + offsetX + 12, 8);
            ctx.textBaseline = 'bottom';
            ctx.fillText('-Y', centerX + offsetX + 12, height - 8);
            
            ctx.restore();
        }

        function drawWafer(data) {
            const canvas = document.getElementById('waferCanvas');
            const ctx = canvas.getContext('2d');
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';

            ctx.clearRect(0, 0, canvas.width, canvas.height);

            const centerX = canvas.width / 2;
            const centerY = canvas.height / 2;
            const scale = baseScale * zoomScale;

            // Draw grid background
            drawGrid(ctx, canvas.width, canvas.height, centerX, centerY, scale);

            // Draw wafer outline (including flat/notch area)
            if (layerVisibility.wafer) {
                ctx.beginPath();
                ctx.arc(centerX + offsetX, centerY + offsetY, data.wafer_radius * scale, 0, 2 * Math.PI);
                ctx.fillStyle = isDark ? 'rgba(100, 100, 100, 0.2)' : 'rgba(200, 200, 200, 0.3)';
                ctx.fill();
                ctx.strokeStyle = isDark ? '#666' : '#999';
                ctx.lineWidth = 2;
                ctx.stroke();

                // Draw flat/notch area as part of wafer layer
                if (data.sagitta > 0) {
                    if (data.flat_length > 0) {
                        const halfFlat = data.flat_length / 2;
                        const flatY_canvas = data.wafer_radius - data.sagitta;
                        const intersectX = Math.sqrt(2 * data.wafer_radius * data.sagitta - data.sagitta * data.sagitta);

                        // Draw the flat chord
                        ctx.beginPath();
                        ctx.moveTo(centerX + offsetX - intersectX * scale, centerY + offsetY + flatY_canvas * scale);
                        ctx.lineTo(centerX + offsetX + intersectX * scale, centerY + offsetY + flatY_canvas * scale);
                        ctx.strokeStyle = isDark ? '#666' : '#999';
                        ctx.lineWidth = 3;
                        ctx.stroke();

                        const angleToLeft = Math.atan2(flatY_canvas, -intersectX);
                        const angleToRight = Math.atan2(flatY_canvas, intersectX);

                        ctx.beginPath();
                        ctx.arc(centerX + offsetX, centerY + offsetY, data.wafer_radius * scale, angleToLeft, angleToRight);
                        ctx.strokeStyle = isDark ? '#666' : '#999';
                        ctx.lineWidth = 2;
                        ctx.setLineDash([3, 3]);
                        ctx.stroke();
                        ctx.setLineDash([]);

                        ctx.save();
                        ctx.beginPath();
                        ctx.moveTo(centerX + offsetX - intersectX * scale, centerY + offsetY + flatY_canvas * scale);
                        ctx.lineTo(centerX + offsetX + intersectX * scale, centerY + offsetY + flatY_canvas * scale);
                        ctx.arc(centerX + offsetX, centerY + offsetY, data.wafer_radius * scale, angleToRight, angleToLeft, true);
                        ctx.closePath();
                        ctx.fillStyle = isDark ? 'rgba(100, 100, 100, 0.2)' : 'rgba(200, 200, 200, 0.3)';
                        ctx.fill();
                        ctx.restore();
                    } else if (data.notch_depth > 0) {
                        const flatY = data.wafer_radius - data.sagitta;
                        const notchWidth = 2;

                        ctx.beginPath();
                        ctx.moveTo(centerX + offsetX - notchWidth * scale, centerY + offsetY + (flatY + data.sagitta) * scale);
                        ctx.lineTo(centerX + offsetX, centerY + offsetY + flatY * scale);
                        ctx.lineTo(centerX + offsetX + notchWidth * scale, centerY + offsetY + (flatY + data.sagitta) * scale);
                        ctx.strokeStyle = isDark ? '#666' : '#999';
                        ctx.lineWidth = 2;
                        ctx.stroke();
                    }
                }
            }

            // Draw usable area
            if (layerVisibility.usable) {
                ctx.beginPath();
                ctx.arc(centerX + offsetX, centerY + offsetY, data.usable_radius * scale, 0, 2 * Math.PI);
                ctx.strokeStyle = layerConfig.usable.color;
                ctx.setLineDash([5, 5]);
                ctx.lineWidth = 2;
                ctx.stroke();
                ctx.setLineDash([]);
            }

            // Draw flat/notch area
            if (layerVisibility.flat && data.sagitta > 0) {
                if (data.flat_length > 0) {
                    const halfFlat = data.flat_length / 2;
                    const flatY_canvas = data.wafer_radius - data.sagitta;
                    const intersectX = Math.sqrt(2 * data.wafer_radius * data.sagitta - data.sagitta * data.sagitta);

                    // Draw the flat chord
                    ctx.beginPath();
                    ctx.moveTo(centerX + offsetX - intersectX * scale, centerY + offsetY + flatY_canvas * scale);
                    ctx.lineTo(centerX + offsetX + intersectX * scale, centerY + offsetY + flatY_canvas * scale);
                    ctx.strokeStyle = '#ef4444';
                    ctx.lineWidth = 3;
                    ctx.stroke();

                    const angleToLeft = Math.atan2(flatY_canvas, -intersectX);
                    const angleToRight = Math.atan2(flatY_canvas, intersectX);

                    ctx.beginPath();
                    ctx.arc(centerX + offsetX, centerY + offsetY, data.wafer_radius * scale, angleToLeft, angleToRight);
                    ctx.strokeStyle = '#ef4444';
                    ctx.lineWidth = 2;
                    ctx.setLineDash([3, 3]);
                    ctx.stroke();
                    ctx.setLineDash([]);

                    ctx.save();
                    ctx.beginPath();
                    ctx.moveTo(centerX + offsetX - intersectX * scale, centerY + offsetY + flatY_canvas * scale);
                    ctx.lineTo(centerX + offsetX + intersectX * scale, centerY + offsetY + flatY_canvas * scale);
                    ctx.arc(centerX + offsetX, centerY + offsetY, data.wafer_radius * scale, angleToRight, angleToLeft, true);
                    ctx.closePath();
                    ctx.fillStyle = isDark ? 'rgba(239, 68, 68, 0.2)' : 'rgba(239, 68, 68, 0.15)';
                    ctx.fill();
                    ctx.restore();
                } else if (data.notch_depth > 0) {
                    const flatY = data.wafer_radius - data.sagitta;
                    const notchWidth = 2;

                    ctx.beginPath();
                    ctx.moveTo(centerX + offsetX - notchWidth * scale, centerY + offsetY + (flatY + data.sagitta) * scale);
                    ctx.lineTo(centerX + offsetX, centerY + offsetY + flatY * scale);
                    ctx.lineTo(centerX + offsetX + notchWidth * scale, centerY + offsetY + (flatY + data.sagitta) * scale);
                    ctx.strokeStyle = '#ef4444';
                    ctx.lineWidth = 2;
                    ctx.stroke();
                }
            }

            // Draw dies - batch by type for better performance
            const fullDies = [];
            const partialDies = [];
            
            data.die_positions.forEach(die => {
                if (die.full && layerVisibility.dieFull) {
                    fullDies.push(die);
                } else if (!die.full && layerVisibility.diePartial) {
                    partialDies.push(die);
                }
            });
            
            // Draw full dies
            if (fullDies.length > 0) {
                ctx.save();
                ctx.globalAlpha = 0.7;
                ctx.fillStyle = layerConfig.die.color;
                ctx.strokeStyle = isDark ? 'rgba(255, 255, 255, 0.55)' : 'rgba(0, 0, 0, 0.5)';
                ctx.lineWidth = 0.9;
                fullDies.forEach(die => {
                    const px = centerX + offsetX + die.x * scale;
                    const py = centerY + offsetY + die.y * scale;
                    const w = die.w * scale;
                    const h = die.h * scale;
                    ctx.fillRect(px, py, w, h);
                    ctx.strokeRect(px, py, w, h);
                });
                ctx.restore();
            }
            
            // Draw partial dies
            if (partialDies.length > 0) {
                ctx.save();
                ctx.globalAlpha = 0.35;
                ctx.fillStyle = layerConfig.diePartial.color;
                ctx.strokeStyle = isDark ? 'rgba(255, 255, 255, 0.55)' : 'rgba(0, 0, 0, 0.5)';
                ctx.lineWidth = 0.9;
                partialDies.forEach(die => {
                    const px = centerX + offsetX + die.x * scale;
                    const py = centerY + offsetY + die.y * scale;
                    const w = die.w * scale;
                    const h = die.h * scale;
                    ctx.fillRect(px, py, w, h);
                    ctx.strokeRect(px, py, w, h);
                });
                ctx.restore();
            }

            // Draw center crosshair
            ctx.beginPath();
            ctx.moveTo(centerX + offsetX - 15, centerY + offsetY);
            ctx.lineTo(centerX + offsetX + 15, centerY + offsetY);
            ctx.moveTo(centerX + offsetX, centerY + offsetY - 15);
            ctx.lineTo(centerX + offsetX, centerY + offsetY + 15);
            ctx.strokeStyle = isDark ? 'rgba(168, 85, 247, 0.8)' : 'rgba(168, 85, 247, 0.6)';
            ctx.lineWidth = 1;
            ctx.stroke();
        }

        function showToast(title, message, type = 'info') {
            const container = document.getElementById('toastContainer');
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            toast.innerHTML = `
                <div class="toast-title">${title}</div>
                <div class="toast-message">${message}</div>
            `;
            container.appendChild(toast);

            setTimeout(() => {
                toast.classList.add('hiding');
                setTimeout(() => {
                    container.removeChild(toast);
                }, 300);
            }, 3000);
        }

        // Sidebar section toggle
        function toggleSection(sectionId) {
            const section = document.getElementById(sectionId);
            section.classList.toggle('collapsed');
        }

        async function exportGdsii() {
            const btn = document.getElementById('exportGdsiiBtn');
            const originalText = btn.innerHTML;
            btn.innerHTML = '<span>⏳</span> Exporting...';

            try {
                const params = new URLSearchParams();
                const wafer = document.getElementById('wafer').value || '100';
                const dieWidth = document.getElementById('die_width').value || '10';
                const dieHeight = document.getElementById('die_height').value || '10';
                const scribe = document.getElementById('scribe').value || '0.1';
                const edge = document.getElementById('edge').value || '3';
                const flatLength = document.getElementById('flat_length').value || '0';
                const notchDepth = document.getElementById('notch_depth').value || '0';

                params.append('wafer', wafer);
                params.append('die_width', dieWidth);
                params.append('die_height', dieHeight);
                params.append('scribe', scribe);
                params.append('edge', edge);
                params.append('flat_length', flatLength);
                params.append('notch_depth', notchDepth);

                params.append('layer_wafer', layerConfig.wafer.layer);
                params.append('datatype_wafer', layerConfig.wafer.datatype);
                params.append('layer_usable', layerConfig.usable.layer);
                params.append('datatype_usable', layerConfig.usable.datatype);
                params.append('layer_die', layerConfig.die.layer);
                params.append('datatype_die', layerConfig.die.datatype);

                params.append('include_partial', document.getElementById('includePartial').checked ? '1' : '0');
                params.append('align_x', document.getElementById('alignX').checked ? '1' : '0');
                params.append('align_y', document.getElementById('alignY').checked ? '1' : '0');

                const response = await fetch('/export_gdsii?' + params.toString());
                if (!response.ok) {
                    throw new Error('Export failed: ' + response.statusText);
                }

                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                const customName = document.getElementById('exportFilename').value.trim();
                const fileTag = customName
                    ? customName
                    : (currentData
                        ? `${Math.round(currentData.wafer_diameter)}mm_${currentData.full_dies}dies`
                        : `${Math.round(parseFloat(wafer))}mm_layout`);
                const fileName = fileTag.endsWith('.gds') ? fileTag : `wafer_${fileTag}.gds`;
                a.download = fileName;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);

                showToast('Export Complete', 'GDSII file downloaded successfully', 'success');
            } catch (err) {
                showToast('Export Failed', err.message, 'error');
            } finally {
                btn.innerHTML = originalText;
            }
        }

        function exportPng() {
            if (!currentData) {
                showToast('Export Failed', 'Please calculate first before exporting', 'error');
                return;
            }

            const canvas = document.getElementById('waferCanvas');
            const link = document.createElement('a');
            const customName = document.getElementById('exportFilename').value.trim();
            const fileTag = customName
                ? customName
                : `${Math.round(currentData.wafer_diameter)}mm_${currentData.full_dies}dies`;
            const fileName = fileTag.endsWith('.png') ? fileTag : `wafer_${fileTag}.png`;
            link.download = fileName;
            link.href = canvas.toDataURL();
            link.click();

            showToast('Export Complete', 'PNG image downloaded successfully', 'success');
        }

        function exportSvg() {
            showToast('Export Disabled', 'SVG export has been removed from the sidebar.', 'warning');
        }

        // Initialize first section as collapsed for better layout
        toggleSection('sectionInfo');
        updateLayerMeta();
        applyStandardSize(document.getElementById('standard_size').value, false);
        
        // Initialize baseScale and draw initial wafer outline
        baseScale = 200 / 50; // Default for 100mm wafer (50mm radius)
        drawWaferOutline();
    </script>
</body>
</html>'''


class RequestHandler(BaseHTTPRequestHandler):
    rate_limit = {}

    def _rate_limited(self):
        ip = self.client_address[0]
        now = int(time.time())
        window = 60
        limit = 10
        record = self.rate_limit.get(ip, {'start': now, 'count': 0})
        if now - record['start'] >= window:
            record = {'start': now, 'count': 0}
        record['count'] += 1
        self.rate_limit[ip] = record
        return record['count'] > limit
    def _read_json_body(self):
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length <= 0:
            return None
        raw = self.rfile.read(content_length)
        return json.loads(raw.decode('utf-8'))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode())

        elif parsed.path == '/calculate':
            params = urllib.parse.parse_qs(parsed.query)

            try:
                wafer_diameter = float(params.get('wafer', ['100'])[0])
                die_width = float(params.get('die_width', ['10'])[0])
                die_height = float(params.get('die_height', ['10'])[0])
                scribe = float(params.get('scribe', ['0.1'])[0])
                edge_exclusion = float(params.get('edge', ['3'])[0])
                flat_length = float(params.get('flat_length', ['0'])[0])
                notch_depth = float(params.get('notch_depth', ['0'])[0])

                if wafer_diameter <= 0 or die_width <= 0 or die_height <= 0:
                    raise ValueError("Dimensions must be positive")
                if wafer_diameter < MIN_WAFER_DIAMETER or wafer_diameter > MAX_WAFER_DIAMETER:
                    raise ValueError("Wafer diameter out of range")
                if die_width < MIN_DIE_SIZE or die_width > MAX_DIE_SIZE:
                    raise ValueError("Die width out of range")
                if die_height < MIN_DIE_SIZE or die_height > MAX_DIE_SIZE:
                    raise ValueError("Die height out of range")
                if scribe < 0 or scribe > MAX_SCRIBE:
                    raise ValueError("Scribe out of range")
                if edge_exclusion < 0 or edge_exclusion > MAX_EDGE_EXCLUSION:
                    raise ValueError("Edge exclusion out of range")

                include_partial = params.get('include_partial', ['1'])[0] == '1'
                align_x = params.get('align_x', ['0'])[0] == '1'
                align_y = params.get('align_y', ['0'])[0] == '1'

                result = calculate_dies(
                    wafer_diameter,
                    die_width,
                    die_height,
                    scribe,
                    edge_exclusion,
                    flat_length,
                    notch_depth,
                    max_positions=1200,
                    include_partial=include_partial,
                    align_x=align_x,
                    align_y=align_y,
                )

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())

            except Exception as e:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())

        elif parsed.path == '/export_gdsii':
            params = urllib.parse.parse_qs(parsed.query)

            try:
                wafer_diameter = float(params.get('wafer', ['100'])[0])
                die_width = float(params.get('die_width', ['10'])[0])
                die_height = float(params.get('die_height', ['10'])[0])
                scribe = float(params.get('scribe', ['0.1'])[0])
                edge_exclusion = float(params.get('edge', ['3'])[0])
                flat_length = float(params.get('flat_length', ['0'])[0])
                notch_depth = float(params.get('notch_depth', ['0'])[0])

                if wafer_diameter <= 0 or die_width <= 0 or die_height <= 0:
                    raise ValueError("Dimensions must be positive")
                if wafer_diameter < MIN_WAFER_DIAMETER or wafer_diameter > MAX_WAFER_DIAMETER:
                    raise ValueError("Wafer diameter out of range")
                if die_width < MIN_DIE_SIZE or die_width > MAX_DIE_SIZE:
                    raise ValueError("Die width out of range")
                if die_height < MIN_DIE_SIZE or die_height > MAX_DIE_SIZE:
                    raise ValueError("Die height out of range")
                if scribe < 0 or scribe > MAX_SCRIBE:
                    raise ValueError("Scribe out of range")
                if edge_exclusion < 0 or edge_exclusion > MAX_EDGE_EXCLUSION:
                    raise ValueError("Edge exclusion out of range")

                include_partial = params.get('include_partial', ['1'])[0] == '1'
                align_x = params.get('align_x', ['0'])[0] == '1'
                align_y = params.get('align_y', ['0'])[0] == '1'

                result = calculate_dies(
                    wafer_diameter,
                    die_width,
                    die_height,
                    scribe,
                    edge_exclusion,
                    flat_length,
                    notch_depth,
                    max_positions=0,
                    include_partial=include_partial,
                    align_x=align_x,
                    align_y=align_y,
                )
                layer_config = {
                    'wafer_layer': int(params.get('layer_wafer', ['0'])[0]),
                    'wafer_datatype': int(params.get('datatype_wafer', ['0'])[0]),
                    'usable_layer': int(params.get('layer_usable', ['1'])[0]),
                    'usable_datatype': int(params.get('datatype_usable', ['0'])[0]),
                    'die_layer': int(params.get('layer_die', ['2'])[0]),
                    'die_datatype': int(params.get('datatype_die', ['0'])[0]),
                }

                gdsii_data = generate_gdsii(result, layer_config)

                self.send_response(200)
                self.send_header('Content-type', 'application/octet-stream')
                self.send_header('Content-Disposition', 'attachment; filename="wafer_layout.gds"')
                self.send_header('Content-Length', str(len(gdsii_data)))
                self.end_headers()
                self.wfile.write(gdsii_data)

            except Exception as e:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == '/feedback':
            try:
                payload = self._read_json_body()
                if not payload or not payload.get('message'):
                    raise ValueError('Feedback message is required')

                if payload.get('website'):
                    raise ValueError('Invalid submission')

                if self._rate_limited():
                    raise ValueError('Rate limit exceeded')

                entry = {
                    'type': payload.get('type', 'other'),
                    'message': payload.get('message', '').strip(),
                    'email': payload.get('email', '').strip(),
                    'timestamp': payload.get('timestamp', ''),
                    'context': payload.get('context', {}),
                }

                webhook_url = os.environ.get('FEEDBACK_WEBHOOK_URL', '').strip()
                if webhook_url:
                    text = (
                        f"Feedback ({entry['type']}):\n"
                        f"{entry['message']}\n\n"
                        f"Email: {entry['email'] or 'n/a'}\n"
                        f"Context: {json.dumps(entry['context'])}"
                    )
                    data = json.dumps({'text': text}).encode('utf-8')
                    req = urllib.request.Request(
                        webhook_url,
                        data=data,
                        headers={'Content-Type': 'application/json'},
                        method='POST',
                    )
                    with urllib.request.urlopen(req, timeout=10):
                        pass
                else:
                    feedback_path = os.environ.get('FEEDBACK_PATH', '/tmp/feedback.jsonl')
                    feedback_dir = os.path.dirname(feedback_path)
                    if feedback_dir:
                        os.makedirs(feedback_dir, exist_ok=True)
                    with open(feedback_path, 'a', encoding='utf-8') as handle:
                        handle.write(json.dumps(entry) + '\n')

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'ok': True}).encode())
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress request logging


def main():
    port = int(os.environ.get('PORT', '5000'))
    server = HTTPServer(('0.0.0.0', port), RequestHandler)
    print("Wafer Die Calculator running at:")
    print(f"  http://localhost:{port}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == '__main__':
    main()
