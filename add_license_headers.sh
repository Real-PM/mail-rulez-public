#!/bin/bash
#
# Mail-Rulez - Add License Headers Script
# Copyright (c) 2024 Real Project Management Solutions
#
# This script adds license headers to all source files

set -e

# License header for Python files
PYTHON_HEADER='"""
Mail-Rulez - Intelligent Email Management System
Copyright (c) 2024 Real Project Management Solutions

This software is dual-licensed:
1. AGPL v3 for open source/self-hosted use
2. Commercial license for hosted services and enterprise use

For commercial licensing, contact: license@mail-rulez.com
See LICENSE-DUAL for complete licensing information.
"""

'

# License header for shell scripts
SHELL_HEADER='#!/bin/bash
#
# Mail-Rulez - Intelligent Email Management System
# Copyright (c) 2024 Real Project Management Solutions
#
# This software is dual-licensed. See LICENSE-DUAL for details.
# Commercial licensing: license@mail-rulez.com
#

'

# License header for HTML files
HTML_HEADER='<!--
Mail-Rulez - Intelligent Email Management System
Copyright (c) 2024 Real Project Management Solutions
Dual-licensed software. See LICENSE-DUAL for details.
-->
'

# License header for CSS/JS files
CSS_JS_HEADER='/*
 * Mail-Rulez - Intelligent Email Management System
 * Copyright (c) 2024 Real Project Management Solutions
 * Dual-licensed software. See LICENSE-DUAL for details.
 */

'

# Function to add header to Python files
add_python_header() {
    local file=$1
    echo "Processing Python file: $file"
    
    # Check if file already has the header
    if grep -q "Mail-Rulez - Intelligent Email Management System" "$file"; then
        echo "  - Already has header, skipping"
        return
    fi
    
    # Check if file starts with shebang
    if head -n1 "$file" | grep -q "^#!"; then
        # File has shebang, insert header after it
        local shebang=$(head -n1 "$file")
        local rest=$(tail -n +2 "$file")
        echo "$shebang" > "$file.tmp"
        echo "$PYTHON_HEADER" >> "$file.tmp"
        echo "$rest" >> "$file.tmp"
    else
        # No shebang, just prepend header
        echo "$PYTHON_HEADER" > "$file.tmp"
        cat "$file" >> "$file.tmp"
    fi
    
    mv "$file.tmp" "$file"
    echo "  - Header added"
}

# Function to add header to shell scripts
add_shell_header() {
    local file=$1
    echo "Processing shell script: $file"
    
    # Check if file already has the header
    if grep -q "Mail-Rulez - Intelligent Email Management System" "$file"; then
        echo "  - Already has header, skipping"
        return
    fi
    
    # Skip the existing shebang if present
    if head -n1 "$file" | grep -q "^#!"; then
        tail -n +2 "$file" > "$file.tmp"
    else
        cp "$file" "$file.tmp"
    fi
    
    # Add new header
    echo "$SHELL_HEADER" > "$file.new"
    cat "$file.tmp" >> "$file.new"
    mv "$file.new" "$file"
    rm -f "$file.tmp"
    
    echo "  - Header added"
}

# Function to add header to HTML files
add_html_header() {
    local file=$1
    echo "Processing HTML file: $file"
    
    # Check if file already has the header
    if grep -q "Mail-Rulez - Intelligent Email Management System" "$file"; then
        echo "  - Already has header, skipping"
        return
    fi
    
    # Add header at the beginning
    echo "$HTML_HEADER" > "$file.tmp"
    cat "$file" >> "$file.tmp"
    mv "$file.tmp" "$file"
    
    echo "  - Header added"
}

# Function to add header to CSS/JS files
add_css_js_header() {
    local file=$1
    echo "Processing CSS/JS file: $file"
    
    # Check if file already has the header
    if grep -q "Mail-Rulez - Intelligent Email Management System" "$file"; then
        echo "  - Already has header, skipping"
        return
    fi
    
    # Add header at the beginning
    echo "$CSS_JS_HEADER" > "$file.tmp"
    cat "$file" >> "$file.tmp"
    mv "$file.tmp" "$file"
    
    echo "  - Header added"
}

# Main execution
echo "=== Adding License Headers to Source Files ==="
echo

# Process Python files
echo "Processing Python files..."
find . -name "*.py" -type f ! -path "./__pycache__/*" ! -path "./venv/*" ! -path "./env/*" | while read -r file; do
    add_python_header "$file"
done

# Process shell scripts
echo -e "\nProcessing shell scripts..."
find . -name "*.sh" -type f | while read -r file; do
    add_shell_header "$file"
done

# Process HTML files
echo -e "\nProcessing HTML files..."
find . -name "*.html" -type f | while read -r file; do
    add_html_header "$file"
done

# Process CSS files
echo -e "\nProcessing CSS files..."
find . -name "*.css" -type f | while read -r file; do
    add_css_js_header "$file"
done

# Process JavaScript files
echo -e "\nProcessing JavaScript files..."
find . -name "*.js" -type f | while read -r file; do
    add_css_js_header "$file"
done

# Process Dockerfile
if [ -f "docker/Dockerfile" ]; then
    echo -e "\nProcessing Dockerfile..."
    if ! grep -q "Mail-Rulez - Intelligent Email Management System" "docker/Dockerfile"; then
        {
            echo "# Mail-Rulez - Intelligent Email Management System"
            echo "# Copyright (c) 2024 Real Project Management Solutions"
            echo "# Dual-licensed: AGPL v3 / Commercial. See LICENSE-DUAL"
            echo ""
            cat "docker/Dockerfile"
        } > "docker/Dockerfile.tmp"
        mv "docker/Dockerfile.tmp" "docker/Dockerfile"
        echo "  - Header added to Dockerfile"
    fi
fi

echo -e "\n=== License headers added successfully! ==="
echo
echo "Please review the changes before committing."
echo "You may want to run 'git diff' to see all modifications."